const state={items:[],category:"Összes",letter:"",query:""};

const grid=document.getElementById("grid");
const count=document.getElementById("count");
const search=document.getElementById("search");
const categories=document.getElementById("categories");
const letters=document.getElementById("letters");
const modal=document.getElementById("modal");
const detail=document.getElementById("detail");

async function init(){
  const response=await fetch("data/gyujtemeny.json");
  state.items=await response.json();
  buildCategories();
  buildLetters();
  render();
}
function buildCategories(){
  const cats=["Összes",...new Set(state.items.map(x=>x.category))];
  categories.innerHTML=cats.map(c=>`<button class="cat ${c==="Összes"?"active":""}" data-cat="${esc(c)}">${esc(c)}</button>`).join("");
  categories.querySelectorAll("[data-cat]").forEach(b=>b.onclick=()=>{
    state.category=b.dataset.cat;
    categories.querySelectorAll(".cat").forEach(x=>x.classList.remove("active"));
    b.classList.add("active"); render();
  });
}
function buildLetters(){
  const lettersArr=[...new Set(state.items.map(x=>x.name.trim().charAt(0).toUpperCase()))].sort((a,b)=>a.localeCompare(b,"hu"));
  letters.innerHTML=lettersArr.map(l=>`<button class="letter" data-letter="${esc(l)}">${esc(l)}</button>`).join("");
  document.querySelector('[data-letter=""]').onclick=()=>{state.letter="";render()};
  letters.querySelectorAll(".letter").forEach(b=>b.onclick=()=>{state.letter=b.dataset.letter;render()});
}
function render(){
  const q=state.query.toLocaleLowerCase("hu-HU");
  const results=state.items.filter(x=>{
    const text=[x.name,x.category,x.year,x.place,x.inventory,x.material,x.type,...(x.keywords||[])].join(" ").toLocaleLowerCase("hu-HU");
    return (state.category==="Összes"||x.category===state.category)
      &&(!state.letter||x.name.trim().charAt(0).toUpperCase()===state.letter)
      &&(!q||text.includes(q));
  });
  count.textContent=`${results.length} találat`;
  grid.innerHTML=results.length?results.map((x,i)=>card(x,i)).join(""):`<div class="no-result">Nincs a keresésnek megfelelő tárgy.</div>`;
  grid.querySelectorAll(".card").forEach((c,i)=>c.onclick=()=>openDetail(results[i]));
}
function card(x,i){
  const image=x.image?`<img src="${escAttr(x.image)}" alt="${escAttr(x.name)}">`:`<div class="placeholder">${esc(x.category)}</div>`;
  return `<article class="card" tabindex="0"><div class="card-image">${image}</div><div class="card-body"><div class="tag">${esc(x.category)}</div><h3>${esc(x.name)}</h3><div class="meta">${esc(x.year||"")} ${x.place?"· "+esc(x.place):""}</div></div></article>`;
}
function openDetail(x){
  const image=x.image?`<img class="detail-main-image" src="${escAttr(x.image)}" alt="${escAttr(x.name)}">`:`<div class="detail-main-image placeholder">${esc(x.category)}</div>`;
  const fact=(label,value)=>value?`<div class="fact"><strong>${label}:</strong>${esc(value)}</div>`:"";
  detail.innerHTML=`<div class="detail-grid"><div>${image}</div><div class="detail"><div class="tag">${esc(x.category)}</div><h2 id="detail-title">${esc(x.name)}</h2>${fact("Leltári szám",x.inventory)}${fact("Gyűjtemény",x.collection)}${fact("Tárgytípus",x.type)}${fact("Készítés / kor",x.year)}${fact("Származási hely",x.place)}${fact("Anyag",x.material)}</div></div><div class="description"><strong>Leírás</strong><p>${esc(x.description||"")}</p>${x.keywords?.length?`<p><strong>Kulcsszavak:</strong> ${x.keywords.map(esc).join(", ")}</p>`:""}</div>`;
  modal.classList.add("show"); modal.setAttribute("aria-hidden","false");
}
function closeModal(){modal.classList.remove("show");modal.setAttribute("aria-hidden","true")}
document.querySelectorAll("[data-close]").forEach(x=>x.onclick=closeModal);
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeModal()});
search.oninput=()=>{state.query=search.value.trim();render()};
function esc(v){return String(v??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]))}
function escAttr(v){return esc(v)}
init().catch(e=>{grid.innerHTML='<div class="no-result">A gyűjtemény adatai jelenleg nem tölthetők be.</div>';console.error(e)});
