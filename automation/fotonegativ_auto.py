import base64
import json
import math
import os
import random
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[1]

DATA = ROOT / "automation" / "fotonegativ_adatok.json"
STATE = ROOT / "automation" / "fotonegativ_state.json"
PENDING = ROOT / "automation" / "pending_fotonegativ.json"
OUT = ROOT / "generated-instagram"
LOGO = ROOT / "automation" / "muzeum_logo.png"

OWNER = "PeterGere79"
REPO = "digitalis-gyujtemeny"
BRANCH = "main"

RAW_ROOT = (
    f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/"
)

IG_API = os.getenv(
    "INSTAGRAM_API_VERSION",
    "v25.0"
)

TEXT_MODEL = os.getenv(
    "OPENAI_TEXT_MODEL",
    "gpt-5-mini"
)


def get_openai():
    return OpenAI()


def http_json(url, params=None, method="GET", data=None):
    if params:
        url += "?" + urlencode(params)

    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "User-Agent":
                "MuzeumiTartalomkeszito/1.0"
        },
    )

    with urlopen(
        request,
        timeout=120
    ) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


def get_bytes(url):
    request = Request(
        url,
        headers={
            "User-Agent":
                "MuzeumiTartalomkeszito/1.0"
        },
    )

    with urlopen(
        request,
        timeout=120
    ) as response:
        return response.read()


def post_form(url, values):
    return http_json(
        url,
        method="POST",
        data=urlencode(values).encode("utf-8"),
    )


def load_json(path, default):
    if not path.exists():
        return default

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def save_json(path, value):
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


class MissingPhotoError(Exception):
    """A leltári rekordhoz tartozó kép biztosan hiányzik vagy nem képfájl."""


# A múzeumi weboldal a hiányzó fényképek helyén egy kamerát ábrázoló,
# átlós „HIÁNYZÓ FOTÓ” feliratú helyettesítő képet jelenít meg.
# A képernyőképből számolt perceptuális hash: stabil marad átméretezéskor.
MISSING_PHOTO_PHASH = int("6c69c396b4831d78", 16)
MISSING_PHOTO_PHASH_MAX_DISTANCE = 8


def perceptual_hash(image_data):
    """64 bites pHash kizárólag Pillow + Python használatával."""
    with Image.open(BytesIO(image_data)) as source:
        gray = ImageOps.fit(
            source.convert("L"),
            (32, 32),
            method=Image.Resampling.LANCZOS,
        )
    pixels = list(gray.getdata())
    size = 32
    coefficients = {}

    # A 8x8-as alacsony frekvenciájú DCT-együtthatók elegendők a mintához.
    cos_x = [
        [math.cos((2 * x + 1) * u * math.pi / (2 * size)) for x in range(size)]
        for u in range(8)
    ]
    cos_y = [
        [math.cos((2 * y + 1) * v * math.pi / (2 * size)) for y in range(size)]
        for v in range(8)
    ]

    for u in range(8):
        au = 1 / math.sqrt(size) if u == 0 else math.sqrt(2 / size)
        for v in range(8):
            av = 1 / math.sqrt(size) if v == 0 else math.sqrt(2 / size)
            total = 0.0
            for x in range(size):
                cx = cos_x[u][x]
                base = x * size
                for y in range(size):
                    total += pixels[base + y] * cx * cos_y[v][y]
            coefficients[(u, v)] = total * au * av

    values = [
        coefficients[(u, v)]
        for u in range(8)
        for v in range(8)
        if (u, v) != (0, 0)
    ]
    median = sorted(values)[len(values) // 2]
    result = 0
    for u in range(8):
        for v in range(8):
            if (u, v) == (0, 0):
                continue
            result = (result << 1) | int(coefficients[(u, v)] > median)
    return result


def is_missing_photo_placeholder(image_data):
    """Felisméri a weboldal „HIÁNYZÓ FOTÓ” helyettesítő képét."""
    candidate_hash = perceptual_hash(image_data)
    distance = (candidate_hash ^ MISSING_PHOTO_PHASH).bit_count()
    return distance <= MISSING_PHOTO_PHASH_MAX_DISTANCE


def get_verified_image_bytes(url):
    """Letölti és ellenőrzi a fotót; a valóban hiányzó képet külön jelzi."""
    request = Request(
        url,
        headers={
            "User-Agent": "MuzeumiTartalomkeszito/1.0"
        },
    )

    try:
        with urlopen(request, timeout=25) as response:
            image_data = response.read()
    except HTTPError as exc:
        if exc.code in (404, 410):
            raise MissingPhotoError(f"HTTP {exc.code}") from exc
        # Az 5xx, 403 és más szerverhibákat nem jelöljük végleg hiányzó képnek.
        raise

    if not image_data:
        raise MissingPhotoError("üres válasz")

    try:
        with Image.open(BytesIO(image_data)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        # Például a szerver 200-as státusszal hibaoldalt küld kép helyett.
        raise MissingPhotoError("a letöltött fájl nem érvényes kép") from exc

    if is_missing_photo_placeholder(image_data):
        raise MissingPhotoError(
            'a weboldal a „HIÁNYZÓ FOTÓ” helyettesítő képet adja vissza'
        )

    return image_data


def choose_photo():
    data = load_json(
        DATA,
        []
    )

    state = load_json(
        STATE,
        {
            "published_ids": [],
            "last_published_at": None,
            "history": []
        }
    )

    published = set(
        str(x)
        for x in state.get(
            "published_ids",
            []
        )
    )
    missing_images = set(
        str(x)
        for x in state.get(
            "missing_image_ids",
            []
        )
    )

    candidates = [
        item
        for item in data
        if item.get("automatizalhato")
        and item.get("kep_url")
        and item.get("leiras")
        and str(item.get("leltari_szam")) not in published
        and str(item.get("leltari_szam")) not in missing_images
    ]

    if not candidates:
        print("Nincs több ellenőrizhető, nem publikált fotónegatív.")
        return None

    random.shuffle(candidates)
    newly_missing = []
    transient_errors = 0

    for item in candidates:
        inventory_number = str(item.get("leltari_szam"))
        try:
            image_data = get_verified_image_bytes(item["kep_url"])
        except MissingPhotoError as exc:
            print(
                f"Hiányzó vagy hibás kép, kihagyás: "
                f"{inventory_number} ({exc})"
            )
            missing_images.add(inventory_number)
            newly_missing.append(inventory_number)
            continue
        except Exception as exc:
            # Átmeneti hálózati hiba esetén nem jegyezzük fel véglegesen hiányzóként.
            transient_errors += 1
            print(
                f"A kép most nem ellenőrizhető: {inventory_number} "
                f"({type(exc).__name__}: {exc})"
            )
            continue

        item["_image_bytes"] = image_data
        if newly_missing:
            state["missing_image_ids"] = sorted(missing_images)
            save_json(STATE, state)
            print(
                f"Kihagyott hiányzó képek száma ebben a futásban: "
                f"{len(newly_missing)}"
            )
        print(f"A kép elérhető és ellenőrizve: {inventory_number}")
        return item

    if newly_missing:
        state["missing_image_ids"] = sorted(missing_images)
        save_json(STATE, state)
        print(
            f"A hiányzó képek leltári számait elmentettem: "
            f"{len(newly_missing)} új rekord."
        )

    if transient_errors:
        print(
            "Most nem sikerült elérhető fotót ellenőrizni. "
            "Nem készül poszt; a következő futás újrapróbálja az "
            "átmeneti hibák miatt kihagyott rekordokat."
        )
    else:
        print("A fennmaradó rekordokhoz nem található érvényes fotó.")
    return None


def caption_for_photo(item):
    prompt = f"""
Írj egy természetes, érdekes magyar Instagram-posztot
egy múzeumi fotónegatívhoz.

A bemeneti rekord egy múzeumi leíró kartonból származik.

SZIGORÚ SZABÁLYOK:
- kizárólag a megadott adatokból dolgozz;
- ne találj ki tényt, személyt, dátumot, helyszínt vagy történetet;
- a hosszú leírást foglald össze, ne másold egyben;
- a bizonytalan megfogalmazásokat ("feltehetően", "valószínűleg",
  stb.) tartsd meg;
- a leírásban szereplő, dokumentált neveket és eseményeket őrizd meg;
- a leltári szám pontosan maradjon meg;
- legyen körülbelül 700–1100 karakter;
- legyen olvasmányos és természetes, ne tudományos katalógusszöveg;
- ne legyen reklámízű;
- a végén legfeljebb 4 releváns hashtag legyen;
- ne említsd az AI-t.

Használd fel a rövid metaadatokat is, de a H oszlop hosszú leírása
legyen a poszt tartalmi alapja.

LELTÁRI SZÁM:
{item["leltari_szam"]}

A FELVÉTEL TÉMÁJA:
{item["tema"]}

A KÉSZÍTŐ:
{item["keszito"]}

A FELVÉTEL IDEJE:
{item["felvetel_ideje"]}

A FELVÉTEL HELYE:
{item["felvetel_helye"]}

A LEÍRÓ:
{item["meghatarozta"]}

H OSZLOP / RÉSZLETES LEÍRÁS:
{item["leiras"]}

Csak a kész Instagram-posztot add vissza.
"""

    client = get_openai()

    response = client.responses.create(
        model=TEXT_MODEL,
        input=prompt
    )

    return response.output_text.strip()


def load_font(size, bold=False):
    candidates = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/Library/Fonts/Arial.ttf",
        ]
    )

    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(
                path,
                size
            )

    return ImageFont.load_default()


def make_photo_graphic(item, output_path):
    image_data = item.get("_image_bytes")
    if image_data is None:
        image_data = get_bytes(item["kep_url"])

    original = Image.open(
        BytesIO(image_data)
    ).convert("RGB")

    canvas = Image.new(
        "RGB",
        (1024, 1280),
        (244, 240, 232)
    )

    # Vékony, világos keret.
    outer = (
        34,
        34,
        990,
        1246
    )

    draw = ImageDraw.Draw(
        canvas
    )

    draw.rectangle(
        outer,
        outline=(92, 84, 72),
        width=3
    )

    draw.rectangle(
        (
            49,
            49,
            975,
            1145
        ),
        outline=(194, 184, 168),
        width=1
    )

    # Az eredeti fénykép változatlan tartalommal,
    # aránytartóan kerül a keretbe.
    max_size = (
        882,
        1030
    )

    image = ImageOps.contain(
        original,
        max_size,
        Image.Resampling.LANCZOS
    )

    x = (
        512 - image.width // 2
    )

    y = (
        80
        + (
            1000 - image.height
        ) // 2
    )

    canvas.paste(
        image,
        (
            x,
            y
        )
    )

    # Finom alsó információsáv.
    line_y = 1160

    draw.line(
        (
            92,
            line_y,
            932,
            line_y
        ),
        fill=(174, 163, 145),
        width=1
    )

    title = (
        item.get("tema")
        or "Régi fénykép"
    ).strip()

    if len(title) > 68:
        title = title[:65] + "..."

    draw.text(
        (
            92,
            1175
        ),
        title,
        fill=(55, 50, 44),
        font=load_font(
            22,
            bold=True
        )
    )

    meta = (
        "Tiszazugi Földrajzi Múzeum  •  "
        "Leltári szám: "
        + str(item["leltari_szam"])
    )

    draw.text(
        (
            92,
            1212
        ),
        meta,
        fill=(92, 84, 72),
        font=load_font(
            18
        )
    )

    # A múzeum 70 éves jubileumi logója a keret jobb alsó részén.
    # A fotóterületet nem takarja, csak az alsó keretsávba kerül.
    if LOGO.exists():
        logo = Image.open(LOGO).convert("RGBA")
        logo.thumbnail((105, 105), Image.Resampling.LANCZOS)
        logo_x = 885
        logo_y = 1140
        canvas.paste(
            logo,
            (logo_x, logo_y),
            logo
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    canvas.save(
        output_path,
        "PNG",
        optimize=True
    )


def prepare(force=False):
    if PENDING.exists():
        print(
            "Már van függőben lévő fotónegatív-poszt."
        )
        return

    state = load_json(
        STATE,
        {
            "published_ids": [],
            "last_published_at": None,
            "history": []
        }
    )

    last = state.get(
        "last_published_at"
    )

    if last and not force:
        last_dt = datetime.fromisoformat(
            last
        )

        elapsed = (
            datetime.now(timezone.utc)
            - last_dt
        ).total_seconds()

        if elapsed < 2 * 86400:
            print(
                "Még nem esedékes: az előző "
                "publikálás óta nem telt el két nap."
            )
            return

    item = choose_photo()
    if item is None:
        print("Nem készült új bejegyzés, mert nem találtam ellenőrzött fotót.")
        return

    print(
        "Kiválasztott fotónegatív:",
        item["leltari_szam"]
    )

    print(
        "Téma:",
        item["tema"]
    )

    text = caption_for_photo(
        item
    )

    filename = (
        "fotonegativ_"
        + str(
            item["leltari_szam"]
        ).replace(
            "/",
            "_"
        )
        + "_Instagram.png"
    )

    output_path = (
        OUT / filename
    )

    print(
        "Vékony keretes grafika készítése..."
    )

    make_photo_graphic(
        item,
        output_path
    )

    save_json(
        PENDING,
        {
            "leltari_szam":
                item["leltari_szam"],
            "tema":
                item["tema"],
            "caption":
                text,
            "image_path":
                str(
                    output_path.relative_to(
                        ROOT
                    )
                )
        }
    )

    print(
        "Fotónegatív-poszt előkészítve."
    )


def publish():
    if not PENDING.exists():
        print(
            "Nincs publikálásra váró fotó."
        )
        return

    token = os.getenv(
        "INSTAGRAM_ACCESS_TOKEN"
    )

    user_id = os.getenv(
        "INSTAGRAM_USER_ID"
    )

    if not token or not user_id:
        raise RuntimeError(
            "Hiányzik az Instagram access token vagy user ID."
        )

    pending = load_json(
        PENDING,
        {}
    )

    image_path = (
        ROOT / pending["image_path"]
    )

    if not image_path.exists():
        raise RuntimeError(
            "A generált grafika nem található: "
            + str(image_path)
        )

    raw_url = (
        RAW_ROOT
        + quote(
            pending["image_path"],
            safe="/,._-()"
        )
    )

    print(
        "Instagram kép URL:",
        raw_url
    )

    api = (
        "https://graph.instagram.com/"
        + IG_API
    )

    container = post_form(
        api
        + "/"
        + user_id
        + "/media",
        {
            "image_url":
                raw_url,
            "caption":
                pending["caption"],
            "access_token":
                token
        }
    )

    container_id = container.get(
        "id"
    )

    if not container_id:
        raise RuntimeError(
            json.dumps(
                container,
                ensure_ascii=False
            )
        )

    for _ in range(30):
        status = http_json(
            api
            + "/"
            + container_id,
            {
                "fields":
                    "status_code,status",
                "access_token":
                    token
            }
        )

        code = status.get(
            "status_code"
        )

        print(
            "Meta:",
            code
        )

        if code == "FINISHED":
            break

        if code in (
            "ERROR",
            "EXPIRED"
        ):
            raise RuntimeError(
                json.dumps(
                    status,
                    ensure_ascii=False
                )
            )

        time.sleep(2)

    else:
        raise RuntimeError(
            "A Meta médiafeldolgozása nem fejeződött be."
        )

    published = post_form(
        api
        + "/"
        + user_id
        + "/media_publish",
        {
            "creation_id":
                container_id,
            "access_token":
                token
        }
    )

    media_id = published.get(
        "id"
    )

    if not media_id:
        raise RuntimeError(
            json.dumps(
                published,
                ensure_ascii=False
            )
        )

    state = load_json(
        STATE,
        {
            "published_ids": [],
            "last_published_at": None,
            "history": []
        }
    )

    state.setdefault(
        "published_ids",
        []
    ).append(
        str(
            pending["leltari_szam"]
        )
    )

    state["last_published_at"] = (
        datetime.now(timezone.utc)
        .isoformat()
    )

    state.setdefault(
        "history",
        []
    ).append(
        {
            "leltari_szam":
                pending["leltari_szam"],
            "tema":
                pending["tema"],
            "media_id":
                media_id,
            "image_path":
                pending["image_path"],
            "published_at":
                state["last_published_at"]
        }
    )

    save_json(
        STATE,
        state
    )

    PENDING.unlink()

    print(
        "Sikeres Instagram-közzététel:",
        media_id
    )


if __name__ == "__main__":
    mode = os.getenv(
        "INSTAGRAM_AUTOMATION_MODE",
        "prepare"
    )

    force = (
        os.getenv(
            "FORCE_POST",
            "false"
        ).lower()
        == "true"
    )

    if mode == "prepare":
        prepare(
            force=force
        )
    elif mode == "publish":
        publish()
    else:
        raise SystemExit(
            "Ismeretlen INSTAGRAM_AUTOMATION_MODE."
        )
