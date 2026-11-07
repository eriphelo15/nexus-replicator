"""Backtest de 'despertares' en velas de 1 h. Entrada en la apertura de la hora siguiente.

Señal: volumen de la hora >= vol_x veces la mediana de las 168 h previas, subida >= 'sube'
en la hora, volumen >= vol_min y no ser un gigante caído (cierre >= 50% del máximo de 30 días).
Salida: stop móvil del 30% (también como stop inicial) o a las 72 h. Costes: 3% por lado.
Primer resultado (226 tokens grandes, 27-oct-2026): todas las variantes pierden ($4-8 por $50),
ganan el 16-23% y al entrar solo quedaba ~40% de la subida.
"""
import json, os, statistics as st
COSTE=0.03
def cargar():
    for f in os.listdir("velas"):
        v=sorted(tuple(x) for x in json.load(open("velas/"+f)) if x[4]>0)
        if len(v)>=100: yield f[:-5], v
def simular(v, i, stop=0.30, horas=72):
    e=v[i][1]; mx=e
    for k in range(i, min(i+horas, len(v))):
        o,h,l,c=v[k][1:5]; nivel=max(e,mx)*(1-stop)
        if l<=nivel: return min(nivel,o)/e, k-i
        mx=max(mx,h)
    return v[min(i+horas,len(v))-1][4]/e, horas
def señales(v, vmult, ret, vmin):
    out=[]; libre=0
    for t in range(170, len(v)-1):
        if t<libre: continue
        o,h,l,c,vol=v[t][1:6]
        base=st.median(x[5] for x in v[t-168:t])
        if vol<vmin or c/o-1<ret or vol<vmult*max(base,1): continue
        if c < 0.5*max(x[4] for x in v[max(0,t-720):t]): continue
        x,horas=simular(v,t+1); libre=t+1+horas
        fut=v[t+1:t+73]; maxx=max(x[2] for x in fut)/v[t+1][1]
        bajo=min(x[3] for x in v[t-24:t+1]); pico=max(x[2] for x in v[t-24:t+73])
        quedaba=(pico-v[t+1][1])/(pico-bajo) if pico>bajo else 0
        out.append((x*(1-COSTE)**2, maxx, quedaba))
    return out
datos=list(cargar()); print("tokens con velas:",len(datos))
print("vol_x  sube  vol_min |  n   ganan  media_$50  mediana  10x_72h  quedaba_med")
for vm in (3,5,10):
    for r in (0.10,0.20,0.40):
        for vmin in (20_000,100_000):
            s=[x for _,v in datos for x in señales(v,vm,r,vmin)]
            if len(s)<10: continue
            res=[a for a,_,_ in s]
            print(f"{vm:>4}x {r:>5.0%} {vmin:>8} | {len(s):>4} {sum(a>1 for a in res)/len(s):>6.0%} {(st.mean(res)-1)*50:>+9.2f} {st.median(res)-1:>+8.0%} {sum(m>=10 for _,m,_ in s)/len(s):>7.1%} {st.median(q for _,_,q in s):>9.0%}")
