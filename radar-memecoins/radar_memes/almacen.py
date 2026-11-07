"""Registro en CSV: una fila por token detectado y una por cada control posterior."""

import csv
import os

COLUMNAS_DETECCION = [
    "ts", "mint", "simbolo", "nombre", "pool", "dex", "edad_min",
    "precio", "mc", "liq",
    "compradores_m5", "vendedores_m5", "compradores_h1", "vendedores_h1",
    "compras_h1", "ventas_h1", "vol_m5", "vol_h1", "compras_m5", "ventas_m5",
    "var_m5", "var_h1", "var_h6",
    "rc_score", "rc_peligros", "rc_avisos", "rc_riesgos", "lp_bloqueado",
    "clones", "pasa_filtro", "motivo_descarte", "puntuacion",
    "holders", "top10_pct", "top11_20_pct", "holders_antig_min",
    "mint_autoridad", "freeze_autoridad", "gt_score",
    "narrativa", "calor_narrativa", "puesto_narrativa", "catalizador", "dias_catalizador",
    "palabra_caliente", "calor_palabra", "carteras_registradas",
    "nombre_token", "descripcion", "twitter", "web", "prioridad", "avisado", "vetos",
]

COLUMNAS_SEGUIMIENTO = [
    "mint", "horizonte", "ts", "retraso_min", "precio", "mc", "liq", "vivo",
    # Solo en el control de 24 h, calculados con velas de 5 min:
    "max_x", "min_x", "min_hasta_max", "toco_2x", "regla_x",
    # Solo en el control de 7 días, con velas de 1 h:
    "max_x_7d", "horas_hasta_max_7d", "regla_tendencia_x",
]

# Carteras que compraron cada token antes de detectarlo (para buscar carteras
# que entran temprano en los tokens que luego suben).
COLUMNAS_CARTERAS = ["mint", "ts_deteccion", "cartera", "usd", "primera_compra"]

# Foto de cada token vivo en cada ciclo (~5 min), para estudiar qué pasa
# justo antes de un desplome y cuándo conviene salir.
COLUMNAS_SERIE = ["ts", "mint", "precio", "mc", "liq", "compras_m5", "ventas_m5",
                  "compradores_m5", "vendedores_m5", "vol_m5", "var_m5", "var_h1"]

# Supervivientes: tokens de días o semanas que despiertan (supervivientes.py).
COLUMNAS_SUPERVIVIENTE = COLUMNAS_DETECCION + [
    "compradores_h24", "vendedores_h24", "vol_h6", "vol_h24", "var_h24",
    "dias_vida", "vs_maximo", "peor_caida_previa", "resucitado",
]
COLUMNAS_BUSQUEDA = ["ts", "pools"]


class Almacen:
    def __init__(self, carpeta):
        self.carpeta = carpeta
        os.makedirs(carpeta, exist_ok=True)
        self.ruta_det = os.path.join(carpeta, "detecciones.csv")
        self.ruta_seg = os.path.join(carpeta, "seguimiento.csv")
        self.ruta_car = os.path.join(carpeta, "carteras.csv")
        self.ruta_serie = os.path.join(carpeta, "serie.csv")
        self.ruta_alertas = os.path.join(carpeta, "alertas.csv")
        self.ruta_sup = os.path.join(carpeta, "supervivientes.csv")
        self.ruta_busq = os.path.join(carpeta, "supervivientes_busquedas.csv")

    def _leer(self, ruta):
        if not os.path.exists(ruta):
            return []
        with open(ruta, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def _migrar(self, ruta, columnas):
        """Reescribe el CSV con las columnas actuales si se añadieron columnas nuevas."""
        with open(ruta, newline="", encoding="utf-8") as f:
            lector = csv.DictReader(f)
            if lector.fieldnames == columnas:
                return
            filas = list(lector)
        with open(ruta, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
            w.writeheader()
            w.writerows(filas)

    def _anadir(self, ruta, columnas, filas):
        if not filas:
            return
        nuevo = not os.path.exists(ruta)
        if not nuevo:
            self._migrar(ruta, columnas)
        with open(ruta, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=columnas, extrasaction="ignore")
            if nuevo:
                w.writeheader()
            w.writerows(filas)

    def detecciones(self):
        return self._leer(self.ruta_det)

    def seguimientos(self):
        return self._leer(self.ruta_seg)

    def guardar_detecciones(self, filas):
        self._anadir(self.ruta_det, COLUMNAS_DETECCION, filas)

    def guardar_seguimientos(self, filas):
        self._anadir(self.ruta_seg, COLUMNAS_SEGUIMIENTO, filas)

    def carteras(self):
        return self._leer(self.ruta_car)

    def guardar_carteras(self, filas):
        self._anadir(self.ruta_car, COLUMNAS_CARTERAS, filas)

    def serie(self):
        return self._leer(self.ruta_serie)

    def guardar_serie(self, filas):
        self._anadir(self.ruta_serie, COLUMNAS_SERIE, filas)

    def alertas(self):
        return self._leer(self.ruta_alertas)

    def guardar_alerta(self, fila):
        """Añade una alerta reescribiendo el archivo de forma atómica: el vigía
        corre en paralelo al ciclo principal, que lee este archivo."""
        filas = self.alertas() + [fila]
        temporal = self.ruta_alertas + ".tmp"
        with open(temporal, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNAS_DETECCION, extrasaction="ignore")
            w.writeheader()
            w.writerows(filas)
        os.replace(temporal, self.ruta_alertas)

    def supervivientes(self):
        return self._leer(self.ruta_sup)

    def guardar_superviviente(self, fila):
        self._anadir(self.ruta_sup, COLUMNAS_SUPERVIVIENTE, [fila])

    def supervivientes_busquedas(self):
        return self._leer(self.ruta_busq)

    def guardar_busqueda_supervivientes(self, fila):
        self._anadir(self.ruta_busq, COLUMNAS_BUSQUEDA, [fila])

    def registros(self):
        """Detecciones del escaneo, alertas del vigía y supervivientes, con su origen."""
        return ([dict(d, origen="escaneo") for d in self.detecciones()]
                + [dict(a, origen="vigia") for a in self.alertas()]
                + [dict(s, origen="superviviente") for s in self.supervivientes()])
