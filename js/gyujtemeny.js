const types=[["1","metal sign","Fémtábla / metal cover"],["2","engraving","Gravírozott jelzés"],["3","trademark","Trademark / védjegy"],["4","decal","Lehúzó matrica"],["5","face plate","Homlokfelületi lemez"],["6","stand crest","Gépállvány jelzése"],["7","treadle","Öntött taposópedál"],["8","casting","Öntött jelzés"],["9","advertising graphics","Hirdetési grafika"],["10","award","Díj / kitüntetés"],["11","badge","Jelvény"],["12","hand wheel","Kézikerék különleges kialakítása"],["13","text","A hordozón található szöveg"]];
let items=[],activeType="",activeInitial="",wizardText="";
const $=s=>document.querySelector(s),esc=v=>String(v??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[m]));
const typeLabel=t=>types.find(x=>x[1]===t)?.[2]||t;
const searchText=x=>[x.file,x.short,x.full,x.fantasy,x.city,x.country,(x.codes||[]).join(" "),x.source,x.text,(x.roles||[]).join(" ")].join(" ").toLocaleLowerCase("hu-HU");
function buildTypes(){
 $("#typeChoices").innerHTML=types.map(t=>`<button class="type-btn ${activeType===t[1]?"active":""}" data-type="${esc(t[1])}"><b>${t[0]}. ${esc(t[1])}</b><small>${esc(t[2])}</small></button>`).join("");
 $("#aType").innerHTML='<option value="">Bármely jelzéstípus</option>'+types.map(t=>`<option value="${esc(t[1])}">${t[0]}. ${esc(t[1])}</option>`).join("");
 document.querySelectorAll(".type-btn").forEach(b=>b.onclick=()=>{activeType=b.dataset.type;buildTypes();renderWizard()});
}
function filterWizard(){
 const q=wizardText.toLocaleLowerCase("hu-HU");
 return items.filter(x=>(!activeType||x.type===activeType||((x.codes||[]).map(v=>v==="centre decal"||v==="center decal"||v==="box decal"||v==="motor decal"?"decal":v).includes(activeType)))&&(!activeInitial||x.initial===activeInitial)&&(!q||searchText(x).includes(q)));
}
function filterAdvanced(){
 const map=[["aShort","short"],["aFull","full"],["aFantasy","fantasy"],["aCity","city"],["aCountry","country"],["aSource","source"]];
 return items.filter(x=>map.every(([id,k])=>{const q=$("#"+id).value.trim().toLocaleLowerCase("hu-HU");return !q||String(x[k]).toLocaleLowerCase("hu-HU").includes(q)})
 &&(!$("#aText").value.trim()||searchText(x).includes($("#aText").value.trim().toLocaleLowerCase("hu-HU")))
 &&(!$("#aType").value||x.type===$("#aType").value||((x.codes||[]).map(v=>["centre decal","center decal","box decal","motor decal"].includes(v)?"decal":v).includes($("#aType").value)))
 &&(!$("#aInitial").value||x.initial===$("#aInitial").value));
}
function card(x,i){const img=x.image?`<img loading="lazy" src="${esc(x.image)}" alt="${esc(x.full||x.short||x.file)}">`:`<div class="placeholder">${esc(typeLabel(x.type))}</div>`;
 return `<article class="card" data-i="${i}"><div class="card-img">${img}</div><div class="card-body"><div class="tag">${esc(typeLabel(x.type)||"Adatlap")}</div><h3>${esc(x.full||x.short||x.file)}</h3><div class="card-meta"><b>${esc(x.city)}</b>${x.city&&x.country?" · ":""}${esc(x.country)}<br>Iniciálé: ${x.initial==="yes"?"igen":"nem"} · ${esc(x.size)}</div><div class="filename">${esc(x.file)}</div></div></article>`}
function renderResults(container,list){container.innerHTML=`<div class="results-head"><span>${list.length} találat</span><span>Az eredeti fájlnév minden találatnál megmarad.</span></div>`+(list.length?`<div class="result-grid">${list.map(card).join("")}</div>`:`<div class="no-result">Nincs a feltételeknek megfelelő kép.</div>`);
 container.querySelectorAll(".card").forEach((c,i)=>c.onclick=()=>openDetail(list[i]));}
function renderWizard(){ $("#wizardFilters").innerHTML=[activeType?`Jelzéstípus: ${typeLabel(activeType)}`:"Jelzéstípus: mindegy",activeInitial?`Iniciálé: ${activeInitial==="yes"?"igen":"nem"}`:"Iniciálé: mindegy",wizardText?`Szöveg: ${esc(wizardText)}`:""].map(x=>`<span class="chip">${x}</span>`).join("");renderResults($("#wizardResults"),filterWizard())}
function renderAdvanced(){renderResults($("#advancedResults"),filterAdvanced())}
function openDetail(x){const img=x.image?`<img class="detail-image" loading="lazy" src="${esc(x.image)}" alt="${esc(x.full||x.short||x.file)}">`:`<div class="detail-image placeholder">${esc(typeLabel(x.type))}</div>`;
 const fact=(l,v)=>v!==undefined&&v!==""?`<div class="fact"><strong>${l}:</strong> ${esc(v)}</div>`:"";
 $("#detail").innerHTML=`<div class="detail-grid"><div>${img}</div><div class="detail"><div class="tag">${esc(typeLabel(x.type)||"Adatlap")}</div><h2>${esc(x.full||x.short||"Cégjelzés")}</h2>${fact("Rövid név",x.short)}${fact("Fantázianév",x.fantasy)}${fact("Szerep",(x.roles||[]).join(", "))}${fact("Város",x.city)}${fact("Ország",x.country)}${fact("Kódnevek",(x.codes||[]).join(", "))}${fact("Méret",x.size)}${fact("Quelle",x.source)}${fact("Iniciálé",x.initial==="yes"?"igen":"nem")}${fact("Azonosító",x.id)}</div></div><div class="detail-description"><strong>Azonosításhoz használható keresési szöveg</strong><p>${esc(x.file)}</p><div class="raw-file"><b>Eredeti fájlnév:</b><br>${esc(x.file)}</div></div>`;
 $("#modal").classList.add("show");$("#modal").setAttribute("aria-hidden","false")}
document.querySelectorAll(".tab").forEach(t=>t.onclick=()=>{document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));document.querySelectorAll(".panel").forEach(x=>x.classList.remove("active"));t.classList.add("active");$("#"+t.dataset.tab).classList.add("active")});
document.querySelectorAll("[data-close]").forEach(x=>x.onclick=()=>{$("#modal").classList.remove("show");$("#modal").setAttribute("aria-hidden","true")});
document.addEventListener("keydown",e=>{if(e.key==="Escape"){$("#modal").classList.remove("show");$("#modal").setAttribute("aria-hidden","true")}});
document.querySelectorAll("[data-initial]").forEach(b=>b.onclick=()=>{activeInitial=b.dataset.initial;document.querySelectorAll("[data-initial]").forEach(x=>x.classList.remove("active"));b.classList.add("active");renderWizard()});
$("#wizardText").oninput=e=>{wizardText=e.target.value;renderWizard()};
["aShort","aFull","aFantasy","aCity","aCountry","aSource","aText","aType","aInitial"].forEach(id=>$( "#"+id).addEventListener("input",renderAdvanced));
$("#clearAdvanced").onclick=()=>{["aShort","aFull","aFantasy","aCity","aCountry","aSource","aText"].forEach(id=>$("#"+id).value="");$("#aType").value="";$("#aInitial").value="";renderAdvanced()};
fetch("data/gyujtemeny.json").then(r=>r.json()).then(d=>{items=d;buildTypes();renderWizard();renderAdvanced()}).catch(e=>{console.error(e);$("#wizardResults").innerHTML="<div class='no-result'>Az adatbázis nem tölthető be.</div>"});
