"""
PASO 1 — Descargar el archivo histórico de focos de calor desde NASA FIRMS.

Baja un CSV por fuente, año y país. Si el archivo ya existe, lo salta
(puedes cortar y volver a ejecutar sin perder lo descargado).

Uso (desde la carpeta fireseason/):
    python pipeline/01_descargar.py                 # todo
    python pipeline/01_descargar.py --anios 2023    # solo un año (para probar)
"""
import argparse
import sys

import requests
from tqdm import tqdm

import config


def descargar(url: str, destino) -> str:
    """Descarga url a destino. Devuelve 'ok', 'existe' o 'no-disponible'."""
    if destino.exists() and destino.stat().st_size > 0:
        return "existe"

    respuesta = requests.get(url, stream=True, timeout=120)
    if respuesta.status_code == 404:
        return "no-disponible"
    respuesta.raise_for_status()

    temporal = destino.with_suffix(".part")       # evita archivos a medias
    with open(temporal, "wb") as f:
        for bloque in respuesta.iter_content(chunk_size=1 << 20):
            f.write(bloque)
    temporal.replace(destino)
    return "ok"


def main():
    parser = argparse.ArgumentParser(description="Descarga CSV anuales de NASA FIRMS")
    parser.add_argument("--anios", type=int, nargs="*", help="años a descargar (por defecto: todos)")
    args = parser.parse_args()

    tareas = []
    for fuente, (anio_inicio, carpeta) in config.FUENTES.items():
        carpeta.mkdir(parents=True, exist_ok=True)
        anios = args.anios or range(anio_inicio, config.ULTIMO_ANIO_COMPLETO + 1)
        for anio in anios:
            if anio < anio_inicio:
                continue
            for pais in config.PAISES:
                url = config.FIRMS_COUNTRY_URL.format(fuente=fuente, anio=anio, pais=pais)
                destino = carpeta / f"{fuente}_{anio}_{pais}.csv"
                tareas.append((url, destino))

    resumen = {"ok": 0, "existe": 0, "no-disponible": 0, "error": 0}
    for url, destino in tqdm(tareas, desc="Descargando", unit="archivo"):
        try:
            resumen[descargar(url, destino)] += 1
        except requests.RequestException as e:
            resumen["error"] += 1
            tqdm.write(f"ERROR {destino.name}: {e}")

    print("\nResumen:", resumen)
    if resumen["error"]:
        print("Hubo errores: vuelve a ejecutar el script para reintentar solo los que faltan.")
        sys.exit(1)


if __name__ == "__main__":
    main()
