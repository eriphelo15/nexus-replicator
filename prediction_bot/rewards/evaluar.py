"""Evalúa el historial de fotos SIN mirar el futuro.

En cada foto t, el "bot" elige los N mejores candidatos según lo que sabe en t (premio × cuota +
resultado reciente de los makers). Lo que gana en el periodo (t, t+1] se mide con la foto t+1:
  premio = tasa diaria × cuota en t+1 × horas transcurridas / 24 × tiempo activo
  ejecuciones = cuota en t+1 × resultado de los makers en la ventana de t+1 (repartido por horas)
Así se ve si la poca competencia se mantiene y cuánto quedaría de verdad.

    python evaluar.py
"""
import gzip
import json
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HIST = Path(__file__).parent / "historial"
N = 30
ACTIVO = 0.8   # fracción del tiempo con órdenes puestas (se retiran ante noticias)


def cargar():
    fotos = defaultdict(dict)
    resumen = {}
    for p in sorted(HIST.glob("*.jsonl.gz")):
        with gzip.open(p, "rt") as fh:
            for line in fh:
                f = json.loads(line)
                if f.get("resumen"):
                    resumen[f["t"]] = f
                else:
                    fotos[f["t"]][f["cid"]] = f
    return dict(sorted(fotos.items())), resumen


def puntuacion(f):
    perdida = min(f.get("maker_1h", 0), f.get("maker_ahora", 0)) * f["cuota"] * 24 / 6
    return f["rate"] * f["cuota"] * ACTIVO + perdida


def main():
    fotos, resumen = cargar()
    ts = list(fotos)
    print(f"Fotos: {len(ts)}  ({ts[0] if ts else '-'} → {ts[-1] if ts else '-'})")
    for t in ts:
        r = resumen.get(t, {})
        c = [f for f in fotos[t].values() if f.get("candidato")]
        cu = [f["cuota"] for f in c]
        print(f"  {t}  premio total {r.get('premio_total_diario', 0):>9,.0f} $/día  candidatos {len(c):>4}  "
              f"cuota mediana {statistics.median(cu) if cu else 0:.0%}")
    if len(ts) < 2:
        print("Hace falta al menos 2 fotos para evaluar.")
        return

    total_premio = total_ejec = total_horas = 0.0
    capital = 0.0
    print(f"\nCartera de {N} mercados elegida en cada foto y medida en la siguiente:")
    for t0, t1 in zip(ts, ts[1:]):
        horas = (datetime.fromisoformat(t1) - datetime.fromisoformat(t0)).total_seconds() / 3600
        elegidos = sorted((f for f in fotos[t0].values() if f.get("candidato")), key=puntuacion, reverse=True)[:N]
        premio = ejec = cap = 0.0
        vivos = 0
        for f in elegidos:
            g = fotos[t1].get(f["cid"])
            cap += f["capital"]
            if not g:
                continue  # el mercado dejó de tener premio o cerró: no cobra nada
            vivos += 1
            premio += g["rate"] * g["cuota"] * horas / 24 * ACTIVO
            if "maker_1h" in g:
                frac = min(horas, 6) / 6
                ejec += g["cuota"] * min(g["maker_1h"], g["maker_ahora"]) * frac
        total_premio += premio
        total_ejec += ejec
        total_horas += horas
        capital = max(capital, cap)
        print(f"  {t0[5:16]}→{t1[5:16]} ({horas:4.1f} h) siguen {vivos:>2}/{len(elegidos)}  "
              f"premio {premio:>8.2f} $  ejecuciones {ejec:>+8.2f} $  neto {premio + ejec:>+8.2f} $")

    dias = total_horas / 24
    neto = total_premio + total_ejec
    print(f"\nTOTAL {dias:.1f} días: premio {total_premio:,.2f} $  ejecuciones {total_ejec:+,.2f} $  "
          f"neto {neto:+,.2f} $  → {neto / dias if dias else 0:+,.2f} $/día con ~{capital:,.0f} $ de capital")


if __name__ == "__main__":
    main()
