import json, csv, re

cards=[json.loads(l) for l in open('catalog/cards.jsonl')]

def money(s):
    if not s: return None
    try: return float(str(s).replace('$','').replace(',','').strip())
    except: return None

# Manual estimated market values (USD) for notable cards, keyed "photo:slot".
# These are rough ballpark estimates from general market knowledge — NOT live comps.
OV={
"IMG_4824:1":380,  # Puka Nacua Downtown (sticker)
"IMG_4826:6":300,  # Brock Purdy Airborne auto RC
"IMG_4826:3":220,  # Quad HOF QB auto /10
"IMG_4827:6":180,  # Ja Morant Hoops RC auto PSA
"IMG_4827:5":160,  # Ja Morant Kaboom Gold /10 PSA8
"IMG_4827:4":150,  # Wemby Thrillers BGS8.5
"IMG_4824:6":220,  # Walter Payton 1976 rookie SGC8
"IMG_4818:2":180,  # Tatis Chrome Update RC auto PSA10
"IMG_4818:3":170,  # 1968 Bench RC SGC1
"IMG_4850:1":140,  # Crosby 2005 ITG PSA10
"IMG_4822:1":150,  # Mahomes 2017 Sage PSA10
"IMG_4828:4":175,  # Skenes Immaculate (sticker)
"IMG_4814:1":95,
"IMG_4901:3":120,  # Trout Bowman Platinum SGC9
"IMG_4901:2":70,   # Judge Cosmic SGC9
"IMG_4924:2":120,  # Duncan 97-98 Chrome RC raw
"IMG_4851:2":90,   # Tatum Go Time PSA9
"IMG_4851:3":80,   # Anthony Edwards Prizm RC PSA9
"IMG_4851:6":60,"IMG_4851:8":60, # KD McDonald's PSA9 x2
"IMG_4826:5":90,   # 1969 Sayers PSA8
"IMG_4817:1":80,   # 1961 Santo RC PSA4
"IMG_4818:4":90,   # T205 Doolan PSA1
"IMG_4853:1":45,   # 77 Ryan PSA4 (sticker 25)
"IMG_4817:5":120,  # Pete Rose Leaf 1/1 auto
"IMG_4828:2":120,  # Kobe 96-97 Stadium Club RC raw
"IMG_4795:0":0,
}

STARS={"Michael Jordan","Kobe Bryant","LeBron James","Stephen Curry","Victor Wembanyama",
"Shohei Ohtani","Mike Trout","Aaron Judge","Ja Morant","Anthony Edwards","Luka Doncic",
"Patrick Mahomes II","Josh Allen","Joe Burrow","Ja'Marr Chase","Tom Brady","Nikola Jokic",
"Shai Gilgeous-Alexander","Jayson Tatum","Paul Skenes","Bobby Witt Jr.","Giannis Antetokounmpo"}

def est(c):
    m=money(c.get('sticker_price'))
    if m is not None: return m,'sticker'
    k=f"{c['photo']}:{c['slot']}"
    if k in OV: return OV[k],'est'
    v=3.0  # base default
    graded=c.get('graded','raw')
    grn=graded not in ('raw','')
    auto=c.get('auto')
    serial=c.get('serial')
    year=c.get('year','')
    notes=c.get('notes','')
    player=c.get('player','')
    vint = year and year[:4].isdigit() and int(year[:4])<1990
    if 'FLAG' in notes: return 25.0,'est'  # custom/counterfeit auto - niche
    if grn: v=max(v,25)
    if auto: v=max(v,20)
    if serial:
        mnum=re.search(r'/(\d+)',serial)
        if mnum:
            d=int(mnum.group(1))
            if d<=10: v=max(v,50)
            elif d<=25: v=max(v,35)
            elif d<=99: v=max(v,20)
            else: v=max(v,10)
    if vint: v=max(v,12)
    if any(s in player for s in STARS): v=max(v,15)
    if 'RC' in notes or 'Rookie' in notes or 'rookie' in notes: v=max(v,6)
    if 'patch' in notes.lower() or 'jersey' in notes.lower(): v=max(v,15)
    return v,'est'

for c in cards:
    v,basis=est(c)
    c['_val']=v; c['_basis']=basis

cards.sort(key=lambda c:c['_val'], reverse=True)

cols=["rank","est_value_usd","pricing_basis","player","year","brand","set","parallel",
"serial","graded","cert","auto","team","card_no","sticker_price","photo","slot","needs_more","notes"]
with open('catalog/master_inventory.csv','w',newline='') as f:
    w=csv.writer(f); w.writerow(cols)
    for i,c in enumerate(cards,1):
        w.writerow([i,f"{c['_val']:.2f}",c['_basis'],c.get('player',''),c.get('year',''),
        c.get('brand',''),c.get('set',''),c.get('parallel',''),c.get('serial',''),
        c.get('graded','raw'),c.get('cert',''),'Y' if c.get('auto') else '',
        c.get('team',''),c.get('card_no',''),c.get('sticker_price',''),
        c['photo'],c['slot'],'Y' if c.get('needs_more') else '',c.get('notes','')])

total=sum(c['_val'] for c in cards)
print(f"Master inventory: {len(cards)} cards, est total ${total:,.0f}")
print("\nTOP 25 (est most valuable):")
for c in cards[:25]:
    print(f"  ${c['_val']:>6.0f} {c['_basis']:>7} | {c.get('player','')[:26]:26} {c.get('year','')} {c.get('brand','')} {c.get('set','')[:22]:22} {c.get('graded','') if c.get('graded')!='raw' else ''}")
