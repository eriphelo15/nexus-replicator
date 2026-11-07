"""
RADAR MEMES — registra tokens nuevos de Solana y mide qué pasa con ellos.

Uso:
  python radar.py ciclo                 # escanear + seguimiento + informe (una vez)
  python radar.py ciclo --cada 300      # repetir cada 5 min (en tu ordenador)
  python radar.py escanear
  python radar.py seguimiento
  python radar.py informe
  python radar.py vigia --duracion 3600  # alertas tempranas (NTFY_TOPIC para avisar al móvil)
  python radar.py supervivientes         # tokens de días/semanas que despiertan (1 vez por hora)

Los datos se guardan en --datos (por defecto datos_radar/).
"""

import argparse
import time

from radar_memes import analisis, escaner, fuentes, seguimiento, supervivientes, vigia
from radar_memes.almacen import Almacen


def main():
    parser = argparse.ArgumentParser(description="Radar de memecoins de Solana",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog=__doc__)
    parser.add_argument("accion", choices=["ciclo", "escanear", "seguimiento", "informe", "vigia",
                                           "supervivientes"])
    parser.add_argument("--datos", default="datos_radar", help="Carpeta de datos")
    parser.add_argument("--cada", type=int, default=0,
                        help="Repetir cada N segundos (0 = una sola vez)")
    parser.add_argument("--sin-rugcheck", action="store_true")
    parser.add_argument("--plazo", type=int, default=0,
                        help="Segundos máximos por ciclo; al agotarse se guarda lo obtenido (0 = sin límite)")
    parser.add_argument("--duracion", type=int, default=3600,
                        help="vigia: segundos que se mantiene vigilando")
    args = parser.parse_args()

    almacen = Almacen(args.datos)
    if args.accion == "vigia":
        vigia.vigilar(almacen, args.duracion)
        return
    while True:
        inicio = time.monotonic()
        fuentes.fijar_plazo(args.plazo)
        fuentes.errores.clear()
        # El seguimiento va primero: sus controles tienen hora y no se pueden repetir.
        if args.accion in ("ciclo", "seguimiento"):
            seguimiento.seguir(almacen)
        # Una vez por hora (lo decide el propio módulo). Va antes que las fotos y el
        # escaneo de lanzamientos: al final del ciclo no quedaba tiempo y no corría nunca.
        if args.accion in ("ciclo", "supervivientes") and not fuentes.sin_tiempo():
            supervivientes.buscar(almacen)
        if args.accion in ("ciclo", "seguimiento"):
            seguimiento.fotografiar(almacen)
        if args.accion in ("ciclo", "escanear"):
            escaner.escanear(almacen, con_rugcheck=not args.sin_rugcheck)
        if args.accion in ("ciclo", "informe"):
            analisis.escribir(almacen)
        print(f"[ciclo] {time.monotonic() - inicio:.0f} s; errores: {dict(fuentes.errores) or 'ninguno'}")
        if not args.cada:
            break
        time.sleep(args.cada)


if __name__ == "__main__":
    main()
