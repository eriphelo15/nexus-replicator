"""Trayectoria diaria (CoinGecko, 365 d) de memecoins que superaron $5M: subida, techo, caída y salidas."""
import json, os, statistics as st
DIA=86400000
meta={x['id']:x for x in json.load(open('cg_solana_memes.json'))}
filas=[]
for f in sorted(os.listdir('cg')):
    i=f[:-5]
    if i=='solana' or i not in meta: continue
    d=json.load(open('cg/'+f))
    pr=[p for p in d.get('prices',[]) if p[1]]
    mc=dict((int(t//DIA),v) for t,v in d.get('market_caps',[]))
    vol=dict((int(t//DIA),v) for t,v in d.get('total_volumes',[]))
    if len(pr)<10: continue
    dias=[int(t//DIA) for t,_ in pr]; px=[p for _,p in pr]
    ip=max(range(len(px)),key=lambda k:px[k])
    if ip==len(px)-1 or ip<2: continue   # techo hoy o sin historia previa
    x0=px[0]; pico=px[ip]
    r={'id':i,'sim':meta[i]['symbol'],'lista':dias[0],'dias_a_pico':dias[ip]-dias[0],
       'x_desde_lista':pico/x0,'mc_pico_m':(mc.get(dias[ip]) or 0)/1e6,
       'hoy_vs_pico':px[-1]/pico,'nace_en_ventana':dias[0]>dias[-1]-360}
    for n in (0.5,0.2,0.1):
        k=next((k for k in range(ip,len(px)) if px[k]<=pico*n),None)
        r[f'dias_a_{int((1-n)*100)}']=dias[k]-dias[ip] if k is not None else None
    iv=max(range(len(px)),key=lambda k:vol.get(dias[k],0))
    r['vol_max_vs_pico_dias']=dias[iv]-dias[ip]
    # ¿Volvió a un nuevo máximo tras caer 50% antes del pico? (muertes y regresos)
    m,cae,vueltas=0,False,0
    for p in px[:ip+1]:
        if p>m:
            if cae: vueltas+=1; cae=False
            m=p
        if p<=m*0.5: cae=True
    r['regresos_antes_pico']=vueltas
    # ¿Tras caer 50% desde el pico, recuperó el pico?
    k50=next((k for k in range(ip,len(px)) if px[k]<=pico*0.5),None)
    r['rebote_tras_50']=max(px[k50:])/pico if k50 is not None else None
    # Salidas con stop móvil diario (desde el primer 3x sobre el precio de listado)
    for sm in (0.3,0.4,0.5,0.6):
        mx,act,sal=0,False,None
        for p in px:
            if not act and p>=3*x0: act=True
            mx=max(mx,p)
            if act and p<=mx*(1-sm): sal=p; break
        r[f'stop{int(sm*100)}_captura']=(sal/pico) if sal else (px[-1]/pico if act else None)
    filas.append(r)
json.dump(filas,open('diario.json','w'))
def med(k,fs): 
    v=[f[k] for f in fs if f[k] is not None]; return (round(st.median(v),2),len(v)) if v else None
print('tokens',len(filas))
for k in ['dias_a_pico','x_desde_lista','hoy_vs_pico','dias_a_50','dias_a_80','dias_a_90','vol_max_vs_pico_dias','regresos_antes_pico','rebote_tras_50','stop30_captura','stop40_captura','stop50_captura','stop60_captura']:
    print(k,med(k,filas))
nv=[f for f in filas if f['nace_en_ventana']]
print('nacidos en ventana',len(nv))
for k in ['dias_a_pico','x_desde_lista','dias_a_50','dias_a_80','dias_a_90','stop40_captura','stop50_captura']:
    print(' ',k,med(k,nv))
import collections
print('vol max vs pico:',sorted(collections.Counter(max(-5,min(5,f['vol_max_vs_pico_dias'])) for f in filas).items()))
print('rebote tras 50%: recupera pico',sum(1 for f in filas if f['rebote_tras_50'] and f['rebote_tras_50']>=1),'de',sum(1 for f in filas if f['rebote_tras_50']))
