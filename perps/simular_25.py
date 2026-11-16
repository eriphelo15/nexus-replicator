import json, os, sys
sys.path.insert(0, ".")
import simular_copia as S
ops = json.load(open("operativa.json")); out = []
for x in ops:
    f = f"fills_{x['dir'][:10]}.json"
    if not os.path.exists(f): continue
    r = S.simular(x["dir"], json.load(open(f)), reglas=False)
    if not r: continue
    out.append((x["dir"], r, x)); print(x["dir"][:10], f"{r['ret']:+.1%} dd {r['peor_dd']:.0%}", flush=True)
json.dump([{"dir": d, **r} for d, r, _ in out], open("copia_25.json", "w"), indent=1)
print("\nRANKING")
for d, r, x in sorted(out, key=lambda z: -z[1]["ret"]):
    print(f"{d} | {r['ret']:+.1%} | caída {r['peor_dd']:.0%} | meses {x['meses_pos']}/{x['meses']} | acierto {x['acierto']:.0%} | dur {x['dur_med_min']/60:.1f} h | pnl90 ${x['pnl_90d']:,.0f} | {[m[0] for m in x['monedas'][:3]]}")
