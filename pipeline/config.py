"""
Configuración central del pipeline de FireSeason.
Todos los scripts importan sus rutas y parámetros desde aquí.
"""
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent.parent      # carpeta fireseason/
DATA = RAIZ / "data"
RAW_MODIS = DATA / "raw" / "modis"
RAW_VIIRS = DATA / "raw" / "viirs"
PROCESSED = DATA / "processed"
CONTEXTO = DATA / "contexto"
REGIONES = DATA / "regiones"

# ---------------------------------------------------------------------------
# Descarga desde NASA FIRMS (archivo anual por país, no necesita MAP_KEY)
# URL: https://firms.modaps.eosdis.nasa.gov/data/country/<fuente>/<año>/<fuente>_<año>_<País>.csv
# ---------------------------------------------------------------------------
FIRMS_COUNTRY_URL = "https://firms.modaps.eosdis.nasa.gov/data/country/{fuente}/{anio}/{fuente}_{anio}_{pais}.csv"

# Países a descargar. Empezamos con Perú; luego se agregan los vecinos.
# (Brasil es enorme: cientos de MB por año en VIIRS. Agregarlo al final.)
PAISES = [
    "Peru",
    # "Bolivia",
    # "Ecuador",
    # "Colombia",
    # "Chile",
    # "Brazil",
]

# Fuente FIRMS -> (año inicial, carpeta destino)
FUENTES = {
    "modis":       (2001, RAW_MODIS),   # Terra + Aqua, 1 km
    "viirs-snpp":  (2012, RAW_VIIRS),   # Suomi NPP, 375 m
    "viirs-jpss1": (2018, RAW_VIIRS),   # NOAA-20, 375 m
}

# El archivo anual de un año solo existe cuando el año terminó.
ULTIMO_ANIO_COMPLETO = date.today().year - 1

# ---------------------------------------------------------------------------
# Área de estudio
# ---------------------------------------------------------------------------
BBOX_PERU = (-81.5, -18.5, -68.5, 0.1)            # (lon_min, lat_min, lon_max, lat_max)
BBOX_SUDAMERICA = (-82.0, -56.0, -34.0, 13.0)

# ---------------------------------------------------------------------------
# Parámetros de limpieza y armonización
# ---------------------------------------------------------------------------
MODIS_CONFIANZA_MIN = 30                # MODIS: 0-100
VIIRS_CONFIANZA_OK = {"n", "h"}         # VIIRS: l=baja, n=nominal, h=alta
TIPO_VEGETACION = 0                     # type: 0 vegetación, 1 volcán, 2 otra fuente fija, 3 mar
TAMANO_CELDA_GRADOS = 0.1               # rejilla común (~11 km)

# ---------------------------------------------------------------------------
# Armonización MODIS -> VIIRS (paso 3)
# ---------------------------------------------------------------------------
# Años donde ambos sensores funcionan y se usan para calcular el factor.
# Se corta en 2021: desde 2022 Terra y Aqua salieron de su órbita habitual
# (cambió su hora de paso), lo que sesgaría el factor.
CALIB_ANIO_INICIO = 2012
CALIB_ANIO_FIN = 2021

AQUA_INICIO = date(2002, 8, 1)      # antes de esto solo hay MODIS Terra
VIIRS_INICIO = date(2012, 2, 1)     # S-NPP empieza el 20-ene-2012 (enero incompleto)
SERIE_INICIO_CONFIABLE = 2003       # primer año completo con Terra + Aqua

FIGURAS = RAIZ / "docs" / "figuras"
