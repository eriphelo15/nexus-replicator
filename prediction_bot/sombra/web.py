"""Página de resultados del bot en sombra (HTML estático, se regenera cada hora)."""
import html, os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

WEB = Path(os.environ.get("BOT_WEB", Path(__file__).parent / "web"))


def _fila(nombre, xs):
    res = [x for x in xs if "resultado" in x]
    g = sum(x["resultado"] for x in res)
    gs = sum(x["resultado_sim"] for x in res)
    gan = sum(x["gana"] for x in res)
    color = "pos" if g > 0 else "neg" if g < 0 else ""
    return (f"<tr><td>{nombre}</td><td>{len(xs)}</td><td>{len(res)}</td>"
            f"<td>{(100 * gan / len(res)) if res else 0:.0f}%</td>"
            f"<td class='{color}'>{g:+,.0f} $</td><td>{(100 * g / (25 * len(res))) if res else 0:+.1f}%</td>"
            f"<td>{gs:+,.0f} $</td></tr>")


def generar(data, ops):
    secreto = (Path(data) / "web_secreto").read_text().strip() if (Path(data) / "web_secreto").exists() else "panel"
    dest = WEB / secreto
    dest.mkdir(parents=True, exist_ok=True)
    ahora = datetime.now(timezone.utc)
    filas = "".join(_fila(f"Cambio ≥ {u:.2f}", [o for o in ops if o["umbral"] == u]) for u in (0.15, 0.20, 0.30))
    pordia = defaultdict(list)
    for o in ops:
        if o["umbral"] == 0.20:
            pordia[o["d"]].append(o)
    dias = "".join(_fila(d, v) for d, v in sorted(pordia.items(), reverse=True))
    ult = "".join(
        f"<tr><td>{datetime.fromtimestamp(o['t'], timezone.utc):%d/%m %H:%M}</td><td>{html.escape(o['c'])}</td>"
        f"<td>{html.escape(o['q'].split(' be ')[-1][:28])}</td><td>{o['lado']}</td><td>{o['dp']:+.2f}</td>"
        f"<td>{o['precio']:.2f}</td><td>{o.get('disponible', 0):.0f} $</td>"
        f"<td class='{'pos' if o.get('resultado', 0) > 0 else 'neg' if o.get('resultado', 0) < 0 else ''}'>"
        f"{('%+.0f $' % o['resultado']) if 'resultado' in o else 'pendiente'}</td></tr>"
        for o in sorted([o for o in ops if o["umbral"] == 0.20], key=lambda o: -o["t"])[:40])
    pagina = f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="300">
<title>Bot temperatura</title><style>
:root{{--bg:#fff;--fg:#1a1a1a;--mu:#666;--li:#e5e5e5;--pos:#0a7d32;--neg:#c0262d}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111;--fg:#eee;--mu:#999;--li:#333;--pos:#4cc76f;--neg:#ff6b6b}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.4 -apple-system,system-ui,sans-serif;margin:0;padding:16px;max-width:900px}}
h1{{font-size:20px;margin:0 0 4px}} h2{{font-size:16px;margin:24px 0 8px}} .mu{{color:var(--mu);font-size:13px}}
.tw{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{padding:6px 8px;border-bottom:1px solid var(--li);text-align:right;white-space:nowrap}}
td:first-child,th:first-child{{text-align:left}} .pos{{color:var(--pos)}} .neg{{color:var(--neg)}}
</style></head><body>
<h1>Bot de temperatura — modo sombra (sin dinero)</h1>
<div class="mu">Actualizado {ahora:%d/%m/%Y %H:%M} UTC · apuestas en papel de 25 $ al precio real de venta + 1,7 % comisión</div>
<h2>Resumen por regla</h2><div class="tw"><table>
<tr><th>Regla</th><th>Señales</th><th>Resueltas</th><th>Aciertos</th><th>Resultado real</th><th>Por apuesta</th><th>Según simulación</th></tr>
{filas}</table></div>
<div class="mu">"Resultado real" usa el precio de venta del libro en ese instante. "Según simulación" usa el precio medio + 2 c,
como en la prueba histórica: si los dos se parecen, la simulación era fiable.</div>
<h2>Por día (regla 0,20)</h2><div class="tw"><table>
<tr><th>Día</th><th>Señales</th><th>Resueltas</th><th>Aciertos</th><th>Resultado real</th><th>Por apuesta</th><th>Según simulación</th></tr>
{dias}</table></div>
<h2>Últimas señales (regla 0,20)</h2><div class="tw"><table>
<tr><th>Hora UTC</th><th>Ciudad</th><th>Tramo</th><th>Lado</th><th>Cambio</th><th>Precio</th><th>Disponible</th><th>Resultado</th></tr>
{ult}</table></div></body></html>"""
    (dest / "index.html").write_text(pagina)
    (WEB / "index.html").write_text("<!doctype html><title>ok</title>")
