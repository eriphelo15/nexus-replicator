"""Informe: qué señales en la detección anticipan los tokens que se duplican o mueren."""

import bisect
import os
from datetime import datetime, timedelta, timezone

import pandas as pd

from .escaner import _palabras_utiles

APUESTA = 50        # dólares por token en el plan
COSTE_LADO = 0.03   # comisiones + slippage estimados por operación (entrada y salida)
N_MINIMO = 30       # por debajo, la muestra no permite sacar conclusiones

# Cartera "buena": al menos 3 tokens comprados con resultado a 24 h y en al
# menos la mitad de ellos el precio llegó a 2x.
CARTERA_MIN_TOKENS = 3
CARTERA_MIN_ACIERTO = 0.5


def cargar(almacen):
    det = pd.DataFrame(almacen.registros())
    seg = pd.DataFrame(almacen.seguimientos())
    if det.empty:
        return det
    num = ["edad_min", "precio", "mc", "liq", "compradores_h1", "vendedores_h1",
           "vol_h1", "var_m5", "var_h1", "rc_peligros", "clones", "pasa_filtro", "puntuacion",
           "holders", "top10_pct", "gt_score", "calor_narrativa", "puesto_narrativa",
           "calor_palabra", "lp_bloqueado"]
    for c in num:
        det[c] = pd.to_numeric(det[c], errors="coerce") if c in det else float("nan")
    for c in ["narrativa", "catalizador", "motivo_descarte", "dex", "palabra_caliente", "origen",
              "prioridad"]:
        det[c] = det[c].fillna("") if c in det else ""
    det["ts"] = pd.to_datetime(det["ts"], utc=True)
    # Un mismo token puede estar en el escaneo y en las alertas: se queda el primer registro.
    det = det.sort_values("ts").drop_duplicates("mint", keep="first").reset_index(drop=True)

    if seg.empty:
        return det
    extra_24h = ["max_x", "min_x", "min_hasta_max", "toco_2x", "regla_x"]
    extra_7d = ["max_x_7d", "horas_hasta_max_7d", "regla_tendencia_x"]
    for c in ["precio", "vivo"] + extra_24h + extra_7d:
        seg[c] = pd.to_numeric(seg[c], errors="coerce") if c in seg else float("nan")
    for h in ["30m", "1h", "6h", "24h", "3d", "7d"]:
        s = seg[seg["horizonte"] == h].drop_duplicates("mint").set_index("mint")
        det[f"vivo_{h}"] = det["mint"].map(s["vivo"])
        det[f"x_{h}"] = det["mint"].map(s["precio"]) / det["precio"]
        for c in extra_24h if h == "24h" else extra_7d if h == "7d" else []:
            det[c] = det["mint"].map(s[c])
    return det


def _resumen(g):
    g = g[g["x_24h"].notna()]
    n = len(g)
    if n == 0:
        # Mismas columnas que un grupo con datos: si no, la tabla sale deformada.
        return pd.Series({"n": 0, "muertos_24h": "-", "tocaron_2x": "-", "mediana_24h": "-",
                          "regla_$_por_50": "-", "n_7d": 0, "10x_7d": "-", "50x_7d": "-",
                          "tendencia_$_por_50": "-", "aviso": "sin resultados aún"})
    muertos = ((g["vivo_24h"] == 0) | (g["x_24h"] <= 0.1)).mean()
    regla = g["regla_x"].dropna()
    neto = regla * (1 - COSTE_LADO) ** 2
    g7 = g[g["max_x_7d"].notna()]
    tend = g7["regla_tendencia_x"].dropna() * (1 - COSTE_LADO) ** 2
    return pd.Series({
        "n": n,
        "muertos_24h": f"{muertos:.0%}",
        "tocaron_2x": f"{g['toco_2x'].mean():.0%}" if g["toco_2x"].notna().any() else "-",
        "mediana_24h": f"{g['x_24h'].median() - 1:+.0%}",
        "regla_$_por_50": f"{(neto.mean() - 1) * APUESTA:+.2f}" if len(regla) else "-",
        "n_7d": len(g7),
        "10x_7d": f"{(g7['max_x_7d'] >= 10).mean():.1%}" if len(g7) else "-",
        "50x_7d": f"{(g7['max_x_7d'] >= 50).mean():.1%}" if len(g7) else "-",
        "tendencia_$_por_50": f"{(tend.mean() - 1) * APUESTA:+.2f}" if len(tend) else "-",
        "aviso": "muestra pequeña" if n < N_MINIMO else "",
    })


def historial_carteras(df, car):
    """Por cartera: lista ordenada de (momento en que se conoció el resultado, tocó 2x).

    El resultado de un token se conoce 24 h después de detectarlo; usar esa
    fecha evita mirar al futuro al puntuar carteras.
    """
    res = df[df["toco_2x"].notna()][["mint", "ts", "toco_2x"]]
    res = res.assign(resuelto=res["ts"] + pd.Timedelta(hours=24))
    m = car.merge(res, on="mint")
    historial = {}
    for cartera, g in m.groupby("cartera"):
        g = g.sort_values("resuelto")
        historial[cartera] = (list(g["resuelto"]), list(g["toco_2x"].cumsum()))
    return historial


def contar_carteras_buenas(df, car, historial):
    """Para cada token, cuántas de sus carteras compradoras tenían ya buen historial."""
    por_mint = car.groupby("mint")["cartera"].apply(list).to_dict()
    cuentas = []
    for mint, ts in zip(df["mint"], df["ts"]):
        n_buenas = 0
        for cartera in por_mint.get(mint, []):
            fechas, aciertos = historial.get(cartera, ([], []))
            k = bisect.bisect_left(fechas, ts)
            if k >= CARTERA_MIN_TOKENS and aciertos[k - 1] / k >= CARTERA_MIN_ACIERTO:
                n_buenas += 1
        cuentas.append(n_buenas if mint in por_mint else float("nan"))
    return cuentas


def _ranking_carteras(df, car):
    m = car.merge(df[df["toco_2x"].notna()][["mint", "toco_2x", "vivo_24h", "x_24h", "max_x_7d"]],
                  on="mint")
    if m.empty:
        return None
    g = m.groupby("cartera").agg(tokens=("mint", "nunique"), tocaron_2x=("toco_2x", "mean"),
                                 muertos=("x_24h", lambda x: (x <= 0.1).mean()),
                                 llegaron_10x_7d=("max_x_7d", lambda x: (x >= 10).mean()))
    g = g[g["tokens"] >= CARTERA_MIN_TOKENS].sort_values(["tocaron_2x", "tokens"], ascending=False)
    if g.empty:
        return None
    for c in ["tocaron_2x", "muertos", "llegaron_10x_7d"]:
        g[c] = g[c].map(lambda v: "-" if pd.isna(v) else f"{v:.0%}")
    return g.head(15)


def _palabras_calientes(df, ahora):
    reciente = df[df["ts"] >= ahora - timedelta(hours=3)]
    base = df[(df["ts"] < ahora - timedelta(hours=3)) & (df["ts"] >= ahora - timedelta(hours=27))]

    def conteo(d):
        c = {}
        for mint, simbolo in zip(d["mint"], d["simbolo"]):
            for w in _palabras_utiles(str(simbolo)):
                c.setdefault(w, set()).add(mint)
        return c

    rec, bas = conteo(reciente), conteo(base)
    filas = []
    for w, mints in rec.items():
        n, n_base = len(mints), len(bas.get(w, ()))
        subida = (n / 3) / max(n_base / 24, 1 / 24)  # tokens por hora frente a la base
        if n >= 3 and subida >= 3:
            g = reciente[reciente["mint"].isin(mints)].sort_values("mc", ascending=False)
            filas.append({"palabra": w, "tokens_3h": n, "tokens_24h_previas": n_base,
                          "veces_lo_normal": f"x{subida:.0f}", "mayor": g.iloc[0]["simbolo"],
                          "mc_mayor": f"{g.iloc[0]['mc'] / 1e3:.0f}K", "mint_mayor": g.iloc[0]["mint"]})
    return pd.DataFrame(filas).sort_values("tokens_3h", ascending=False).head(10) if filas else None


# Desplome: el precio cae a un 40% o menos del actual dentro de los 30 min siguientes.
DESPLOME_CAIDA = 0.4
DESPLOME_VENTANA = pd.Timedelta(minutes=30)


def _serie_con_senales(serie, df):
    """Serie de 5 min con las posibles señales de salida y si hubo desplome después."""
    s = serie.copy()
    for c in ["precio", "mc", "liq", "compras_m5", "ventas_m5", "compradores_m5",
              "vendedores_m5", "vol_m5", "var_m5", "var_h1"]:
        s[c] = pd.to_numeric(s[c], errors="coerce")
    s["ts"] = pd.to_datetime(s["ts"], utc=True)
    s = s.sort_values(["mint", "ts"])
    s["x_desde_deteccion"] = s["precio"] / s["mint"].map(df.set_index("mint")["precio"])
    s["liq_mc"] = s["liq"] / s["mc"]
    s["ticket_medio"] = s["vol_m5"] / (s["compras_m5"] + s["ventas_m5"]).clip(lower=1)
    s["ratio_cv"] = s["compradores_m5"] / s["vendedores_m5"].clip(lower=1)
    g = s.groupby("mint")["var_m5"]
    # Escalera: 6 fotos seguidas (30 min) subiendo, sin ningún retroceso.
    s["escalera"] = g.transform(lambda v: v.rolling(6).min()) > 0
    # Aceleración final: la última subida de 5 min duplica la media de las 3 anteriores.
    previa = g.transform(lambda v: v.shift(1).rolling(3).mean())
    s["aceleracion"] = (s["var_m5"] > 10) & (s["var_m5"] > 2 * previa.clip(lower=0))
    desplome = []
    for _, t in s.groupby("mint"):
        ts, precio = list(t["ts"]), list(t["precio"])
        for i in range(len(t)):
            futuros = [p for j, p in enumerate(precio[i + 1:], i + 1) if ts[j] - ts[i] <= DESPLOME_VENTANA]
            desplome.append(bool(futuros) and min(futuros) <= DESPLOME_CAIDA * precio[i])
    s["desplome_30m"] = desplome
    return s


def _senales_desplome(serie, df):
    if serie.empty:
        return "Aún no hay serie de 5 min.\n"
    s = _serie_con_senales(serie, df)
    s = s[s["x_desde_deteccion"] >= 1.5]  # solo cuando el token ya ha subido: ahí se decide la salida
    lineas = [f"Fotos de tokens que ya subían un 50% o más: **{len(s)}**; seguidas de un desplome "
              f"(caída a un {DESPLOME_CAIDA:.0%} o menos en 30 min): **{int(s['desplome_30m'].sum())}**. "
              "Cada fila compara cuántas veces llegó un desplome con la señal activa frente a "
              "sin ella: si la señal lo anticipa, el primer % es mucho mayor.\n"]
    if s["desplome_30m"].sum() < 20:
        lineas.append("_Menos de 20 desplomes registrados: todavía no se puede concluir nada._\n")
    senales = {
        "Liquidez < 3% de la capitalización": s["liq_mc"] < 0.03,
        "Ticket medio < $30 (volumen de microcompras)": s["ticket_medio"] < 30,
        "Más de 8 compradores por vendedor (5 min)": s["ratio_cv"] > 8,
        "Subida de más del 100% en 1 h": s["var_h1"] > 100,
        "Escalera: 30 min subiendo sin retrocesos": s["escalera"],
        "Aceleración final": s["aceleracion"],
        "Más vendedores que compradores (5 min)": s["ratio_cv"] < 1,
        "Ya multiplicó x5 o más desde la detección": s["x_desde_deteccion"] >= 5,
    }
    filas = []
    for nombre, activa in senales.items():
        con, sin = s[activa], s[~activa]
        filas.append({"señal": nombre, "fotos_con_señal": len(con),
                      "desplome_con_señal": f"{con['desplome_30m'].mean():.0%}" if len(con) else "-",
                      "desplome_sin_señal": f"{sin['desplome_30m'].mean():.0%}" if len(sin) else "-"})
    lineas.append(pd.DataFrame(filas).to_markdown(index=False) + "\n")
    return "\n".join(lineas)


def _supervivientes(sup):
    if sup.empty:
        return "Aún no hay supervivientes (se buscan una vez por hora).\n"
    lineas = ["Hipótesis del estudio de gigantes: los que conservan valor tardaron semanas en "
              "despegar. Se avisan los que no tienen vetos; los vetados se registran para comparar.\n"]
    if "x_24h" in sup and sup["x_24h"].notna().any():
        grupos = sup.assign(grupo=sup["prioridad"].replace({"alta": "avisados", "vetada": "vetados"}))
        lineas.append(_tabla(grupos, "grupo", "Resultado de los supervivientes"))
    t = sup.sort_values("ts", ascending=False).head(15).copy()
    cols = ["ts", "simbolo", "prioridad", "mc", "dias_vida", "vs_maximo", "resucitado", "vetos"]
    for c in ["x_1h", "x_24h", "x_3d", "x_7d", "max_x_7d"]:
        if c in t and t[c].notna().any():
            t[c] = t[c].round(2)
            cols.append(c)
    t["ts"] = t["ts"].dt.strftime("%m-%d %H:%M")
    t["mc"] = (t["mc"] / 1e6).round(2).astype(str) + "M"
    lineas.append(t[cols + ["mint"]].to_markdown(index=False) + "\n")
    return "\n".join(lineas)


def _tabla(df, columna, titulo):
    t = df.groupby(columna, observed=True).apply(_resumen, include_groups=False)
    return f"### {titulo}\n\n{t.to_markdown()}\n"


def generar(almacen):
    df = cargar(almacen)
    # Los supervivientes son tokens de días o semanas: van en su propia sección
    # para no mezclarlos con los lanzamientos.
    sup = df[df["origen"] == "superviviente"] if not df.empty else df
    if not df.empty:
        df = df[df["origen"] != "superviviente"].reset_index(drop=True)
    car = pd.DataFrame(almacen.carteras())
    if not df.empty:
        if "toco_2x" not in df:
            df["toco_2x"] = float("nan")
        if not car.empty:
            car["ts_deteccion"] = pd.to_datetime(car["ts_deteccion"], utc=True)
            df["carteras_buenas"] = contar_carteras_buenas(df, car, historial_carteras(df, car))
        else:
            df["carteras_buenas"] = float("nan")
    ahora = datetime.now(timezone.utc)
    lineas = [f"# Informe del radar de memecoins\n",
              f"Generado: {ahora:%Y-%m-%d %H:%M} UTC\n"]
    if df.empty:
        return "\n".join(lineas + ["Todavía no hay detecciones.\n",
                                   "## Supervivientes (tokens de 3 a 120 días que despiertan)\n",
                                   _supervivientes(sup)])

    con24 = df[df.get("x_24h", pd.Series(dtype=float)).notna()] if "x_24h" in df else df.iloc[0:0]
    lineas.append(f"- Tokens registrados: **{len(df)}** (desde {df['ts'].min():%Y-%m-%d %H:%M})")
    lineas.append(f"- Con resultado a 24 h: **{len(con24)}**"
                  + ("" if len(con24) else " (el primero llega 24 h después de la primera detección)"))
    lineas.append(f"- Pasan el filtro v1: **{int(df['pasa_filtro'].sum())}**")
    lineas.append(f"- Resultados en dólares por cada apuesta de ${APUESTA}, con {COSTE_LADO:.0%} "
                  "de costes en la entrada y en la salida:")
    lineas.append("  - `regla_$_por_50` (24 h): vender 50% a 2x, 20% a 5x, 20% a 10x; stop a -50%.")
    lineas.append("  - `tendencia_$_por_50` (7 días): vender 1/3 a 3x y el resto con stop móvil "
                  "del 50% desde el máximo. Es la que puede capturar las subidas grandes.")
    lineas.append("  - `10x_7d` / `50x_7d`: % de tokens cuyo máximo en 7 días llegó a 10x / 50x.\n")

    if len(con24):
        df = df.copy()
        df["filtro_v1"] = df["pasa_filtro"].map({1: "pasa", 0: "no pasa"})
        df["edad"] = pd.cut(df["edad_min"], [0, 15, 30, 60, 180, 1440],
                            labels=["<15 min", "15-30 min", "30-60 min", "1-3 h", "3-24 h"])
        df["cap"] = pd.cut(df["mc"], [0, 50e3, 150e3, 500e3, 1.5e6, 1e12],
                           labels=["<50K", "50-150K", "150-500K", "500K-1.5M", ">1.5M"])
        ratio = df["compradores_h1"] / df["vendedores_h1"].clip(lower=1)
        df["compradores_vs_vendedores"] = pd.cut(ratio, [0, 1.2, 3, 8, 1e9],
                                                 labels=["<1.2", "1.2-3", "3-8", ">8"])
        df["volumen_vs_cap"] = pd.cut(df["vol_h1"] / df["mc"], [0, 0.5, 1, 3, 1e9],
                                      labels=["<0.5", "0.5-1", "1-3", ">3"])
        df["liquidez_bloqueada"] = pd.cut(df["lp_bloqueado"], [-1, 0, 99.9, 100],
                                          labels=["0%", "parcial", "100%"]).cat.add_categories(
                                              "sin datos").fillna("sin datos")
        df["peligros_rugcheck"] = df["rc_peligros"].map(
            lambda v: "sin datos" if pd.isna(v) else ("2+" if v >= 2 else str(int(v))))
        df["narrativa_"] = df["narrativa"].replace("", "sin narrativa")
        df["papel_en_narrativa"] = df.apply(
            lambda r: "sin narrativa" if not r["narrativa"]
            else ("líder" if r["puesto_narrativa"] == 1 else "seguidor/clon"), axis=1)
        df["calor"] = pd.cut(df["calor_narrativa"], [0, 1, 3, 8, 1e9],
                             labels=["1 token", "2-3", "4-8", "9+"])
        df["con_catalizador"] = df["catalizador"].map(lambda c: "sí" if c else "no")
        df["calor_palabra_"] = pd.cut(df["calor_palabra"], [0, 1, 2, 4, 1e9],
                                      labels=["única", "2 tokens", "3-4", "5+"])
        df["top10_holders"] = pd.cut(df["top10_pct"], [-1, 15, 25, 35, 50, 101],
                                     labels=["<15%", "15-25%", "25-35%", "35-50%", ">50%"])
        df["num_holders"] = pd.cut(df["holders"], [0, 100, 300, 1000, 3000, 1e9],
                                   labels=["<100", "100-300", "300-1K", "1K-3K", "3K+"])
        df["gt_score_"] = pd.cut(df["gt_score"], [-1, 30, 45, 60, 101],
                                 labels=["<30", "30-45", "45-60", "60+"])
        df["puntuacion_q"] = pd.qcut(df["puntuacion"].rank(method="first"), 5,
                                     labels=["Q1 (baja)", "Q2", "Q3", "Q4", "Q5 (alta)"])

        lineas.append("## ¿Funciona el filtro?\n")
        lineas.append(_tabla(df.assign(todos="todos"), "todos", "Todos los tokens"))
        lineas.append(_tabla(df, "filtro_v1", "Filtro v1"))
        lineas.append(_tabla(df, "origen", "Alertas tempranas del vigía (2-15 min de vida) frente al escaneo"))
        if "prioridad" in df and (df["origen"] == "vigia").any():
            alertas = df[df["origen"] == "vigia"].copy()
            alertas["tema"] = alertas["prioridad"].fillna("").replace(
                {"alta": "con tema relevante (avisadas)", "baja": "sin tema (silenciosas)",
                 "vetada": "vetadas (no avisadas)", "": "antes de separar"})
            lineas.append(_tabla(alertas, "tema", "Alertas con tema, sin tema y vetadas"))
            vetadas = alertas[alertas["prioridad"] == "vetada"].copy()
            if len(vetadas) and "vetos" in vetadas:
                vetadas = vetadas.assign(veto=vetadas["vetos"].fillna("").str.split("|")).explode("veto")
                lineas.append(_tabla(vetadas, "veto", "Qué habría pasado con los vetados, por veto "
                                                      "(si les va bien, el veto sobra)"))
        motivos = df.assign(motivo=df["motivo_descarte"].fillna("").str.split("|")).explode("motivo")
        motivos = motivos[motivos["motivo"] != ""]
        if len(motivos):
            lineas.append(_tabla(motivos, "motivo", "Por motivo de descarte (un token puede tener varios)"))

        lineas.append("## Narrativas\n")
        for col, titulo in [("narrativa_", "Por narrativa"),
                            ("papel_en_narrativa", "Líder de su narrativa frente a seguidores y clones"),
                            ("calor", "Calor de la narrativa (tokens con el mismo tema en el escaneo)"),
                            ("con_catalizador", "Con catalizador próximo"),
                            ("calor_palabra_", "Tokens del escaneo que comparten palabra con él")]:
            lineas.append(_tabla(df, col, titulo))

        lineas.append("## Carteras inteligentes\n")
        lineas.append(f"Cartera con buen historial: {CARTERA_MIN_TOKENS} tokens o más comprados antes "
                      f"de detectarlos y al menos el {CARTERA_MIN_ACIERTO:.0%} llegaron a 2x. Solo cuenta "
                      "el historial que se conocía en el momento de cada detección.\n")
        df["carteras_buenas_"] = df["carteras_buenas"].map(
            lambda v: "sin datos" if pd.isna(v) else ("0" if v == 0 else ("1" if v == 1 else "2+")))
        lineas.append(_tabla(df, "carteras_buenas_", "Carteras con buen historial entre los compradores"))
        ranking = _ranking_carteras(df, car) if not car.empty else None
        lineas.append("### Mejores carteras\n")
        lineas.append(ranking.to_markdown() + "\n" if ranking is not None
                      else f"Aún no hay carteras con {CARTERA_MIN_TOKENS}+ tokens resueltos.\n")

        lineas.append("## Holders\n")
        for col, titulo in [("top10_holders", "% del suministro en los 10 mayores holders"),
                            ("num_holders", "Número de holders"), ("gt_score_", "GT Score")]:
            lineas.append(_tabla(df, col, titulo))

        lineas.append("## Señales por separado\n")
        for col, titulo in [("edad", "Edad al detectarlo"), ("cap", "Capitalización al detectarlo"),
                            ("compradores_vs_vendedores", "Compradores / vendedores (1 h)"),
                            ("volumen_vs_cap", "Volumen de 1 h / capitalización"),
                            ("peligros_rugcheck", "Peligros de RugCheck"),
                            ("liquidez_bloqueada", "Liquidez bloqueada (RugCheck): con 0% el creador puede retirarla"),
                            ("puntuacion_q", "Puntuación (quintiles)"), ("dex", "DEX")]:
            lineas.append(_tabla(df, col, titulo))

        lineas.append("## Supervivencia por horizonte\n")
        for h in ["30m", "1h", "6h", "24h"]:
            v = df[f"vivo_{h}"].dropna()
            if len(v):
                lineas.append(f"- {h}: {v.mean():.0%} vivos (n={len(v)})")
        lineas.append("")

    lineas.append("## Supervivientes (tokens de 3 a 120 días que despiertan)\n")
    lineas.append(_supervivientes(sup))

    lineas.append("## Últimas alertas del vigía (6 h)\n")
    alertas = df[(df["origen"] == "vigia") & (df["ts"] >= ahora - timedelta(hours=6))]
    if len(alertas):
        t = alertas[["ts", "simbolo", "narrativa", "prioridad", "edad_min", "mc", "compradores_m5",
                     "vendedores_m5", "mint"]].sort_values("ts", ascending=False).copy()
        if "x_1h" in alertas:
            t["x_1h"] = alertas["x_1h"].round(2)
        t["ts"] = t["ts"].dt.strftime("%H:%M")
        t["mc"] = (t["mc"] / 1e3).round().astype(int).astype(str) + "K"
        lineas.append(t.to_markdown(index=False) + "\n")
    else:
        lineas.append("Ninguna.\n")

    lineas.append("## Señales de desplome (cuándo salir)\n")
    lineas.append(_senales_desplome(pd.DataFrame(almacen.serie()), df))

    lineas.append("## Palabras calientes (últimas 3 h)\n")
    lineas.append("Palabras que aparecen en muchos más tokens nuevos de lo normal: temas que "
                  "se están calentando aunque no estén en la lista de narrativas.\n")
    calientes = _palabras_calientes(df, ahora)
    lineas.append(calientes.to_markdown(index=False) + "\n" if calientes is not None else "Ninguna.\n")

    lineas.append("## Narrativas activas (últimas 2 h)\n")
    ult = df[(df["ts"] >= ahora - timedelta(hours=2)) & (df["narrativa"] != "")]
    if len(ult):
        filas = []
        for narrativa, g in ult.groupby("narrativa"):
            lider = g.sort_values("liq", ascending=False).iloc[0]
            cat = g["catalizador"].iloc[0]
            filas.append({"narrativa": narrativa, "tokens_nuevos": len(g),
                          "lider": lider["simbolo"], "mc_lider": f"{lider['mc'] / 1e3:.0f}K",
                          "catalizador": f"{cat} (en {int(g['dias_catalizador'].iloc[0])} días)" if cat else "",
                          "mint_lider": lider["mint"]})
        t = pd.DataFrame(filas).sort_values("tokens_nuevos", ascending=False)
        lineas.append(t.to_markdown(index=False) + "\n")
    else:
        lineas.append("Ninguna.\n")

    recientes = df[(df["pasa_filtro"] == 1) & (df["ts"] >= ahora - timedelta(hours=1))]
    lineas.append("## Pasan el filtro en la última hora\n")
    lineas.append("Solo son candidatos para vigilar mientras el filtro no demuestre ventaja. "
                  "Comprueba el contrato en rugcheck.xyz antes de hacer nada.\n")
    if len(recientes):
        cols = ["ts", "simbolo", "narrativa", "mc", "liq", "edad_min", "compradores_h1",
                "vendedores_h1", "top10_pct", "carteras_buenas", "mint"]
        t = recientes[cols].copy()
        t["ts"] = t["ts"].dt.strftime("%H:%M")
        t["mc"] = (t["mc"] / 1e3).round().astype(int).astype(str) + "K"
        t["liq"] = (t["liq"] / 1e3).round().astype(int).astype(str) + "K"
        lineas.append(t.to_markdown(index=False))
    else:
        lineas.append("Ninguno.")
    return "\n".join(lineas) + "\n"


def escribir(almacen, log=print):
    texto = generar(almacen)
    ruta = os.path.join(almacen.carpeta, "INFORME.md")
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)
    log(f"[informe] {ruta}")
    return texto
