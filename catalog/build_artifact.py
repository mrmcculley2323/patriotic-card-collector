import json,sys
INP=sys.argv[1] if len(sys.argv)>1 else 'catalog/_artifact_data.json'
OUT=sys.argv[2] if len(sys.argv)>2 else 'catalog/inventory.html'
TITLE=sys.argv[3] if len(sys.argv)>3 else 'Sport Card Entire Lot'
d=json.load(open(INP))
DATA=json.dumps(d, separators=(',',':'))
head='''<div class="wrap">
<header class="masthead"><div class="crest">LOT&nbsp;01</div>
<div class="mh-title"><h1>'''+TITLE+'''</h1>
<p class="sub">'''+str(d['stats']['total'])+''' cards &middot; ranked by value &middot; top tier priced on real sold comps</p></div></header>
<section class="tiles" id="tiles"></section><div class="flagbar" id="flagbar"></div>
<section class="panel"><div class="controls"><input id="q" type="search" placeholder="Search player, set, team, brand&hellip;" autocomplete="off" />
<div class="chips" id="filters"></div></div><div class="tablewrap"><table id="tbl"><thead><tr>
<th data-k="r" class="num">#</th><th data-k="v" class="num">Value&nbsp;$</th><th data-k="p">Player</th>
<th data-k="yr">Year</th><th data-k="br">Brand / Set</th><th data-k="pa">Parallel / #</th>
<th data-k="g">Grade</th><th data-k="tm">Team</th><th data-k="ph" class="num">Photo</th></tr></thead>
<tbody id="rows"></tbody></table></div><p class="count" id="count"></p></section>
<footer class="foot"><p><strong>Pricing basis:</strong> <span class="bdot comp"></span> real sold comp &middot;
<span class="bdot sticker"></span> your sticker &middot; <span class="bdot est"></span> estimate.
Hover a <span class="bdot comp"></span> value for the comp note. True 1/1s have no direct comp &mdash; auction-dependent.</p>
<p class="files">Files in <code>catalog/</code>: <code>master_inventory.csv</code> &middot; <code>card_dealer_pro_import.csv</code> &middot; <code>comps.json</code> &middot; <code>needs_more_info.md</code></p></footer></div>'''
css='''
:root{--bg:#eceef2;--panel:#fff;--ink:#171a21;--ink2:#535b6b;--line:#d6dae2;--felt:#0f2e3d;--chrome:#3a6ea5;
--gold:#b8892b;--gold-ink:#7a5a12;--auto:#1f7a4d;--flag:#c0362c;--flag-bg:#fbeae8;--comp:#b8892b;--sticker:#1f7a4d;--est:#8a93a5;
--shadow:0 1px 2px rgba(20,30,50,.06),0 6px 20px rgba(20,30,50,.06);
--font:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;--mono:"SF Mono",ui-monospace,Menlo,Consolas,monospace;}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0c0f14;--panel:#151a22;--ink:#e9edf4;--ink2:#97a1b3;--line:#28303c;
--felt:#0a2430;--chrome:#6fa8dc;--gold:#d6a441;--gold-ink:#d6a441;--auto:#4fc588;--flag:#ef6a5f;--flag-bg:#2a1512;--comp:#d6a441;--sticker:#4fc588;--est:#6b7688;
--shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35);}}
:root[data-theme=dark]{--bg:#0c0f14;--panel:#151a22;--ink:#e9edf4;--ink2:#97a1b3;--line:#28303c;--felt:#0a2430;--chrome:#6fa8dc;
--gold:#d6a441;--gold-ink:#d6a441;--auto:#4fc588;--flag:#ef6a5f;--flag-bg:#2a1512;--comp:#d6a441;--sticker:#4fc588;--est:#6b7688;
--shadow:0 1px 2px rgba(0,0,0,.4),0 8px 24px rgba(0,0,0,.35);}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font);font-size:15px;line-height:1.5;-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 64px}
.masthead{display:flex;align-items:center;gap:20px;margin-bottom:26px}
.crest{flex:none;font-family:var(--mono);font-weight:700;letter-spacing:.06em;font-size:13px;color:#fff;background:linear-gradient(160deg,var(--felt),var(--chrome));padding:14px 12px;border-radius:10px;box-shadow:var(--shadow);text-align:center;line-height:1.2}
.mh-title h1{margin:0;font-size:26px;line-height:1.15;letter-spacing:-.01em;text-wrap:balance}.sub{margin:4px 0 0;color:var(--ink2);font-size:14px}
.tiles{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:18px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 14px 12px;box-shadow:var(--shadow)}
.tile .n{font-size:23px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-.02em}.tile .l{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--ink2);margin-top:3px}
.tile.hero .n{color:var(--gold-ink)}@media(max-width:820px){.tiles{grid-template-columns:repeat(3,1fr)}}@media(max-width:520px){.tiles{grid-template-columns:repeat(2,1fr)}.masthead{flex-wrap:wrap}}
.flagbar{margin:0 0 18px}.flagbar .fb{background:var(--flag-bg);border:1px solid var(--flag);border-radius:12px;padding:12px 16px;color:var(--flag);font-size:13.5px}.flagbar b{color:var(--flag)}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);overflow:hidden}
.controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:16px 16px 12px;border-bottom:1px solid var(--line)}
#q{flex:1;min-width:200px;font:inherit;padding:9px 12px;border:1px solid var(--line);border-radius:9px;background:var(--bg);color:var(--ink)}#q:focus{outline:2px solid var(--chrome);outline-offset:1px}
.chips{display:flex;gap:7px;flex-wrap:wrap}.chip{font:inherit;font-size:12.5px;padding:6px 11px;border:1px solid var(--line);border-radius:999px;background:transparent;color:var(--ink2);cursor:pointer}
.chip[aria-pressed=true]{background:var(--chrome);border-color:var(--chrome);color:#fff}
.tablewrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);white-space:nowrap}
th{position:sticky;top:0;background:var(--panel);cursor:pointer;user-select:none;font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink2);z-index:1}th:hover{color:var(--ink)}
th.num,td.num{text-align:right;font-variant-numeric:tabular-nums}tbody tr:hover{background:color-mix(in srgb,var(--chrome) 7%,transparent)}
td.val{font-weight:700;font-variant-numeric:tabular-nums;cursor:help}
.pill{display:inline-block;font-size:10.5px;font-weight:600;padding:1px 6px;border-radius:5px;vertical-align:middle;margin-left:5px;letter-spacing:.02em}
.pill.au{background:color-mix(in srgb,var(--auto) 16%,transparent);color:var(--auto)}.pill.fl{background:var(--flag-bg);color:var(--flag)}.pill.nm{background:color-mix(in srgb,var(--gold) 18%,transparent);color:var(--gold-ink)}
.bdot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-left:6px;vertical-align:middle}.bdot.comp{background:var(--comp)}.bdot.sticker{background:var(--sticker)}.bdot.est{background:var(--est)}
.foot .bdot{margin-left:0;margin-right:4px;width:9px;height:9px}
.player{font-weight:600;color:var(--ink);white-space:normal;min-width:150px}.setcell{white-space:normal;min-width:150px;color:var(--ink2)}.setcell b{color:var(--ink);font-weight:600}
.count{padding:12px 16px;margin:0;color:var(--ink2);font-size:12.5px}.foot{margin-top:20px;color:var(--ink2);font-size:12.5px;line-height:1.7}
.foot code{font-family:var(--mono);font-size:11.5px;background:var(--panel);padding:1px 5px;border-radius:4px;border:1px solid var(--line)}
'''
js='''
const D=__DATA__;const C=D.cards,S=D.stats;const money=n=>"$"+Math.round(n).toLocaleString();
document.getElementById("tiles").innerHTML=[["hero",money(S.value),"Est. total value"],["",S.total,"Cards"],["",S.comped,"Real comps"],["",S.autos,"Autographs"],["",S.graded,"Graded slabs"],["",S.needs+S.flags,"Need review"]].map(t=>`<div class="tile ${t[0]}"><div class="n">${t[1]}</div><div class="l">${t[2]}</div></div>`).join("");
document.getElementById("flagbar").innerHTML=`<div class="fb"><b>&#9873; ${S.flags} custom / counterfeit-labeled slabs</b> (Kaboom / Booom customs &mdash; auto authentic, card is not). Most marketplaces ban these. Filter <b>Need review</b> for these plus IDs to confirm.</div>`;
const F=[["all","All"],["comp","Real comp"],["sticker","Priced by you"],["auto","Autos"],["graded","Graded"],["serial","Numbered"],["review","Need review"]];
let filt="all",q="",sortK="r",sortDir=1;
document.getElementById("filters").innerHTML=F.map(f=>`<button class="chip" data-f="${f[0]}" aria-pressed="${f[0]==='all'}">${f[1]}</button>`).join("");
document.querySelectorAll(".chip").forEach(c=>c.onclick=()=>{filt=c.dataset.f;document.querySelectorAll(".chip").forEach(x=>x.setAttribute("aria-pressed",x===c));render()});
document.getElementById("q").oninput=e=>{q=e.target.value.toLowerCase();render()};
document.querySelectorAll("th").forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(k===sortK)sortDir*=-1;else{sortK=k;sortDir=(k==="v")?-1:1;}render()});
function pass(c){if(filt==="comp"&&c.b!=="comp")return false;if(filt==="sticker"&&c.b!=="sticker")return false;if(filt==="auto"&&c.au!=="Y")return false;if(filt==="graded"&&!c.g)return false;if(filt==="serial"&&!c.sn)return false;if(filt==="review"&&!(c.nm==="Y"||c.nt.includes("FLAG")))return false;if(q){const h=(c.p+" "+c.br+" "+c.s+" "+c.tm+" "+c.pa+" "+c.g+" "+c.yr).toLowerCase();if(!h.includes(q))return false;}return true;}
function render(){let rows=C.filter(pass);rows.sort((a,b)=>{let x=a[sortK],y=b[sortK];if(sortK==="v"||sortK==="r"){x=+x;y=+y}else{x=(""+x).toLowerCase();y=(""+y).toLowerCase()}return x<y?-1*sortDir:x>y?1*sortDir:0;});
document.getElementById("rows").innerHTML=rows.map(c=>{const pills=(c.au==="Y"?'<span class="pill au">AUTO</span>':'')+(c.nt.includes("FLAG")?'<span class="pill fl">CUSTOM</span>':(c.nm==="Y"?'<span class="pill nm">CHECK</span>':''));
const setc=`<b>${esc(c.br)}</b>${c.s?" &middot; "+esc(c.s):""}`;const par=[c.pa,c.sn?("#"+c.sn):"",c.cn?("No."+c.cn):""].filter(Boolean).join(" &middot; ");
const tip=c.b==="comp"?` title="Comp $${Math.round(c.v)} (${esc(c.dt||'')}, conf: ${esc(c.cf||'')}) — ${esc(c.cnote)}"`:(c.b==="sticker"?' title="Your sticker price"':' title="Estimate (not yet comped)"');
return `<tr><td class="num">${c.r}</td><td class="num val"${tip}>$${Math.round(c.v)}<span class="bdot ${c.b}"></span></td><td class="player">${esc(c.p)}${pills}</td><td>${esc(c.yr)}</td><td class="setcell">${setc}</td><td>${par||"&mdash;"}</td><td>${c.g?esc(c.g):"&mdash;"}</td><td>${esc(c.tm)}</td><td class="num">${c.ph.replace("IMG_","")}</td></tr>`}).join("");
const sv=rows.reduce((s,c)=>s+c.v,0);document.getElementById("count").innerHTML=`Showing <b>${rows.length}</b> of ${C.length} &middot; subtotal <b>${money(sv)}</b>`;}
function esc(s){return(""+s).replace(/[&<>"]/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[m]))}render();
'''
open(OUT,'w').write(head+"\n<style>"+css+"</style>\n<script>"+js.replace("__DATA__",DATA)+"</script>")
print("inventory.html rebuilt")
