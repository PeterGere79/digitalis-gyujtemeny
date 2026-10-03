import base64
import json
import os
import random
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

OWNER = "PeterGere79"
REPO = "digitalis-gyujtemeny"
BRANCH = "main"

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "generated-instagram"
STATE = ROOT / "automation" / "instagram_state.json"
PENDING = ROOT / "automation" / "pending_post.json"

COLLECTION_URL = (
    f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/"
    "data/gyujtemeny.json"
)
RAW_ROOT = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/"

client = OpenAI()
TEXT_MODEL = os.getenv("OPENAI_TEXT_MODEL", "gpt-5-mini")
IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2.5-flare")
IG_API = os.getenv("INSTAGRAM_API_VERSION", "v25.0")


def http_json(url, params=None, method="GET", data=None):
    if params:
        url += "?" + urlencode(params)
    req = Request(
        url,
        method=method,
        data=data,
        headers={"User-Agent": "MuzeumiTartalomkeszito/1.0"},
    )
    with urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def get_bytes(url):
    req = Request(url, headers={"User-Agent": "MuzeumiTartalomkeszito/1.0"})
    with urlopen(req, timeout=120) as r:
        return r.read()


def post_form(url, values):
    return http_json(
        url,
        method="POST",
        data=urlencode(values).encode("utf-8"),
    )


def key(item):
    return str(item.get("id") or item.get("file") or item.get("image") or "").strip()


def title(item):
    return str(
        item.get("short")
        or item.get("full")
        or item.get("fantasy")
        or item.get("id")
        or "Múzeumi tárgy"
    ).strip()


def object_url(item):
    path = str(item.get("image") or "").lstrip("/")
    if not path:
        raise RuntimeError("A tárgynak nincs képe.")
    return RAW_ROOT + quote(path, safe="/,._-()")


def load_state():
    if not STATE.exists():
        return {"published_ids": [], "last_published_at": None, "history": []}
    return json.loads(STATE.read_text(encoding="utf-8"))


def save_state(data):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def caption(item):
    prompt = f"""
Készíts természetes, közérthető magyar Instagram-posztot egy múzeumi
gyűjteményi tárgyhoz.

Csak a megadott rekord adatait használd. Ne találj ki történelmi tényt,
dátumot, személyt, helyet, anyagot vagy használati módot.
A hiányzó adatokat hagyd el. A leltári azonosítót pontosan őrizd meg.
Legyen érdekes, de ne reklámszagú. Legfeljebb 4 releváns hashtag.
Ne említsd az AI-t.

Rekord:
{json.dumps(item, ensure_ascii=False, indent=2)}

Csak a kész poszt szövegét add vissza.
"""
    r = client.responses.create(model=TEXT_MODEL, input=prompt)
    return r.output_text.strip()


def font(size, bold=False):
    names = (
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
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def background(item):
    prompt = f"""
Create a refined vertical 4:5 background for a contemporary regional
Hungarian museum Instagram post.

Tiszazug, Tisza region, subtle topographic/map lines, archival catalogue
paper, local history and natural-history atmosphere. Muted river blue,
deep green, earth brown, warm off-white. Calm central space for a real
museum object photo.

Category: {item.get("type", "museum collection")}

No text, no logos, no people, no fake museum building, no gold frames,
no random historical objects, no luxury-museum styling.
"""
    r = client.images.generate(
        model=IMAGE_MODEL,
        prompt=prompt,
        size="1024x1280",
        quality="medium",
        output_format="png",
        background="opaque",
    )
    return Image.open(
        BytesIO(base64.b64decode(r.data[0].b64_json))
    ).convert("RGBA")


def graphic(item, path):
    canvas = background(item)
    obj = Image.open(BytesIO(get_bytes(object_url(item)))).convert("RGBA")
    obj.thumbnail((760, 760), Image.Resampling.LANCZOS)

    canvas.alpha_composite(
        obj,
        ((1024 - obj.width) // 2, 135),
    )

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (65, 935, 959, 1218),
        radius=24,
        fill=(255, 255, 255, 220),
    )

    draw.text(
        (100, 975),
        title(item)[:70],
        fill=(43, 40, 36, 255),
        font=font(40, True),
    )

    meta = "Tiszazugi Földrajzi Múzeum"
    if item.get("id"):
        meta += f"  •  {item['id']}"

    draw.text(
        (100, 1055),
        meta,
        fill=(78, 73, 67, 255),
        font=font(24),
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(
        path,
        "PNG",
        optimize=True,
    )


def prepare(force=False):
    if PENDING.exists():
        print("Már van függőben lévő poszt.")
        return

    state = load_state()
    last = state.get("last_published_at")

    if last and not force:
        age = (
            datetime.now(timezone.utc)
            - datetime.fromisoformat(last)
        ).total_seconds()

        if age < 2 * 86400:
            print("Még nem telt el két nap az előző publikálás óta.")
            return

    items = http_json(COLLECTION_URL)
    used = set(state.get("published_ids", []))

    choices = [
        x for x in items
        if key(x) and x.get("image") and key(x) not in used
    ]

    if not choices:
        raise RuntimeError("Nincs több nem publikált, képpel rendelkező tárgy.")

    item = random.choice(choices)
    print("Kiválasztott tárgy:", title(item))

    safe_title = "".join(
        c if c.isalnum() else "_"
        for c in title(item)
    ).strip("_")[:60]

    safe_key = "".join(
        c if c.isalnum() else "_"
        for c in key(item)
    ).strip("_")[:30]

    image_path = OUT / f"{safe_title}_{safe_key}_Instagram.png"

    print("Szöveg készítése...")
    text = caption(item)

    print("Grafika készítése...")
    graphic(item, image_path)

    PENDING.parent.mkdir(parents=True, exist_ok=True)
    PENDING.write_text(
        json.dumps(
            {
                "key": key(item),
                "title": title(item),
                "caption": text,
                "image_path": str(image_path.relative_to(ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("Előkészítés kész.")


def publish():
    if not PENDING.exists():
        print("Nincs publikálásra váró poszt.")
        return

    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    user_id = os.getenv("INSTAGRAM_USER_ID")

    if not token or not user_id:
        raise RuntimeError("Hiányzik az Instagram token vagy user ID.")

    pending = json.loads(PENDING.read_text(encoding="utf-8"))
    image_url = RAW_ROOT + quote(
        pending["image_path"],
        safe="/,._-()",
    )

    api = f"https://graph.instagram.com/{IG_API}"

    print("Instagram-kép:", image_url)

    container = post_form(
        f"{api}/{user_id}/media",
        {
            "image_url": image_url,
            "caption": pending["caption"],
            "access_token": token,
        },
    )

    cid = container.get("id")
    if not cid:
        raise RuntimeError(json.dumps(container, ensure_ascii=False))

    for _ in range(30):
        status = http_json(
            f"{api}/{cid}",
            {
                "fields": "status_code,status",
                "access_token": token,
            },
        )
        code = status.get("status_code")
        print("Meta:", code)

        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(json.dumps(status, ensure_ascii=False))
        time.sleep(2)
    else:
        raise RuntimeError("A Meta médiafeldolgozása nem fejeződött be.")

    published = post_form(
        f"{api}/{user_id}/media_publish",
        {
            "creation_id": cid,
            "access_token": token,
        },
    )

    media_id = published.get("id")
    if not media_id:
        raise RuntimeError(json.dumps(published, ensure_ascii=False))

    state = load_state()
    state.setdefault("published_ids", []).append(pending["key"])
    state["last_published_at"] = datetime.now(timezone.utc).isoformat()
    state.setdefault("history", []).append(
        {
            "key": pending["key"],
            "title": pending["title"],
            "media_id": media_id,
            "image_path": pending["image_path"],
        }
    )
    save_state(state)
    PENDING.unlink()

    print("Sikeres Instagram-közzététel:", media_id)


if __name__ == "__main__":
    mode = os.getenv("INSTAGRAM_AUTOMATION_MODE", "prepare")
    force = os.getenv("FORCE_POST", "false").lower() == "true"

    if mode == "prepare":
        prepare(force)
    elif mode == "publish":
        publish()
    else:
        raise SystemExit("Ismeretlen INSTAGRAM_AUTOMATION_MODE.")
