import json, csv
cards=[json.loads(l) for l in open('catalog/cards.jsonl')]
maincomps=json.load(open('catalog/comps.json'))
fbcomps=json.load(open('football/football_comps.json'))
refined=json.load(open('football/football_refined.json'))
ns={}; exec(open('catalog/build_inventory.py').read().split('for c in cards:')[0], ns); est=ns['est']
FB={"49ers","Bears","Bengals","Bills","Broncos","Browns","Buccaneers","Chargers","Chiefs","Colts","Commanders","Cowboys","Dolphins","Eagles","Falcons","Jaguars","Jets","Lions","Packers","Panthers","Patriots","Raiders","Rams","Ravens","Saints","Seahawks","Steelers","Texans","Titans","Vikings","Oilers","Florida State","Penn State","South Carolina","Texas A&M","Indiana"}
CARD_FB={"Larry Fitzgerald","Kyler Murray","Trey McBride","Anquan Boldin"}
GIA_FB={"Malik Nabers","Jaxson Dart","Abdul Carter","Cam Skattebo","Micah McFadden"}
def is_fb(c):
    t=c.get('team',''); p=c.get('player','')
    if t in FB: return True
    if t=="Cardinals": return p in CARD_FB
    if t=="Giants": return p in GIA_FB
    if t=="Multi": return True
    return False
fb=[c for c in cards if is_fb(c)]
for c in fb:
    k=f"{c['photo']}:{c['slot']}"
    if k in fbcomps:
        e=fbcomps[k]; c['_val']=float(e['comp']); c['_basis']='comp'; c['_src']=e['source']; c['_date']=e.get('date',''); c['_conf']=e['conf']; c['_note']=e['note']
    elif k in maincomps:
        e=maincomps[k]; c['_val']=float(e['comp']); c['_basis']='comp'; c['_src']=e['source']; c['_date']=e.get('date',''); c['_conf']='high'; c['_note']=e['note']
    elif k in refined:
        v,note=refined[k]; c['_val']=float(v); c['_basis']='est'; c['_src']=''; c['_date']=''; c['_conf']='knowledge-est'; c['_note']=note
    else:
        v,b=est(c); c['_val']=v; c['_basis']=b; c['_src']=''; c['_date']=''; c['_conf']=('your price' if b=='sticker' else 'est'); c['_note']=''
fb.sort(key=lambda c:c['_val'], reverse=True)
cols=["rank","value_usd","basis","confidence","comp_date","comp_source","player","year","brand","set","parallel","serial","graded","cert","auto","team","card_no","sticker_price","photo","slot","comp_note","notes"]
with open('football/football_inventory.csv','w',newline='') as f:
    w=csv.writer(f); w.writerow(cols)
    for i,c in enumerate(fb,1):
        w.writerow([i,f"{c['_val']:.2f}",c['_basis'],c['_conf'],c.get('_date',''),c.get('_src',''),c.get('player',''),c.get('year',''),c.get('brand',''),c.get('set',''),c.get('parallel',''),c.get('serial',''),c.get('graded','raw'),c.get('cert',''),'Y' if c.get('auto') else '',c.get('team',''),c.get('card_no',''),c.get('sticker_price',''),c['photo'],c['slot'],c.get('_note',''),c.get('notes','')])
def sg(g):
    if not g or g=='raw': return('','')
    p=g.split(); return(p[0],' '.join(p[1:]))
with open('football/football_card_dealer_pro_import.csv','w',newline='') as f:
    w=csv.writer(f); w.writerow(["Sport","Year","Brand","Set","CardNumber","Player","Team","Parallel_Attributes","Serial","GradingCompany","Grade","CertNumber","IsAuto","Quantity","ListPrice","PricingBasis","Confidence","CompDate","CompSource","ConditionNotes","SourcePhoto","ImageURL_pro","MarketplaceStatus"])
    for c in fb:
        gc,gr=sg(c.get('graded','raw'))
        w.writerow(["Football",c.get('year',''),c.get('brand',''),c.get('set',''),c.get('card_no',''),c.get('player',''),c.get('team',''),c.get('parallel',''),c.get('serial',''),gc,gr,c.get('cert',''),'Y' if c.get('auto') else '',1,f"{c['_val']:.2f}",c['_basis'],c['_conf'],c.get('_date',''),c.get('_src',''),c.get('notes','')[:120],c['photo'],"","UNLISTED"])
data=[{"r":i,"v":c['_val'],"b":c['_basis'],"cf":c['_conf'],"dt":c.get('_date',''),"cs":c.get('_src',''),"p":c.get('player',''),"yr":c.get('year',''),"br":c.get('brand',''),"s":c.get('set',''),"pa":c.get('parallel',''),"sn":c.get('serial',''),"g":c.get('graded','') if c.get('graded')!='raw' else "","au":'Y' if c.get('auto') else '',"tm":c.get('team',''),"cn":c.get('card_no',''),"st":c.get('sticker_price',''),"ph":c['photo'],"nm":'Y' if c.get('needs_more') else '',"nt":c.get('notes',''),"cnote":c.get('_note','')} for i,c in enumerate(fb,1)]
tot=sum(c['_val'] for c in fb)
stats={"total":len(fb),"value":round(tot),"comped":sum(1 for c in fb if c['_basis']=='comp'),"stickered":sum(1 for c in fb if c['_basis']=='sticker'),"autos":sum(1 for c in fb if c.get('auto')),"graded":sum(1 for c in fb if c.get('graded','raw') not in('raw','')),"serial":sum(1 for c in fb if c.get('serial')),"flags":sum(1 for c in fb if 'FLAG' in c.get('notes','')),"needs":sum(1 for c in fb if c.get('needs_more'))}
json.dump({"stats":stats,"cards":data},open('football/_ad.json','w'))
print(f"Football: {len(fb)} cards, {stats['comped']} comped, ${tot:,.0f}")
