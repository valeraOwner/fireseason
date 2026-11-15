"""Rutas y parámetros del backend."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]          # carpeta fireseason/
PROCESSED = RAIZ / "data" / "processed"
REGIONES = RAIZ / "data" / "regiones"

# Archivos generados por el pipeline (pasos 2-4)
FOCOS = PROCESSED / "focos_limpios.parquet"
SERIE_REGION = PROCESSED / "serie_mensual_region.parquet"
CLIMA_MENSUAL = PROCESSED / "climatologia_mensual.parquet"
CELDAS_REGION = PROCESSED / "celdas_region.parquet"
FACTORES = PROCESSED / "factores_calibracion.csv"
VALIDACION = PROCESSED / "validacion_calibracion.csv"
VALIDACION_DEP = PROCESSED / "validacion_departamentos.csv"

TAMANO_CELDA = 0.1
ANIO_MIN, ANIO_CONFIABLE = 2001, 2003

# Desde qué páginas se puede llamar a la API (el frontend de desarrollo usa el puerto 5173)
ORIGENES_PERMITIDOS = ["http://localhost:5173", "http://127.0.0.1:5173"]

MAX_FILAS_CSV = 1_000_000

# ---------------------------------------------------------------------------
# Módulo En vivo (API FIRMS, datos NRT = "casi en tiempo real")
# ---------------------------------------------------------------------------
import os                                            # noqa: E402
from dotenv import load_dotenv                       # noqa: E402

load_dotenv(RAIZ / ".env")
FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", "")

# Satélites que se consultan. Los 3 VIIRS (375 m) + MODIS (1 km).
FUENTES_NRT = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "MODIS_NRT"]

# Zona que se consulta: Perú con un margen de ~0.5° para ver lo que pasa en la frontera.
BBOX_EN_VIVO = (-82.0, -19.0, -68.0, 0.6)           # (oeste, sur, este, norte)

DIAS_EN_VIVO = 7          # días que se piden a FIRMS (7 para el factor C: "focos de la provincia en 7 días")
CACHE_MINUTOS = 15        # cada cuánto se vuelve a preguntar a FIRMS (la política dice 15–30 min)

# Tablas del pipeline que usa la política de riesgo
CLIMA_SEMANAL = PROCESSED / "clima_semanal_provincia.parquet"   # factor C
FRECUENCIA = PROCESSED / "frecuencia_celda_mes.parquet"         # factor D
ZONAS_PROTEGIDAS = PROCESSED / "zonas_protegidas.geojson"      # factor F (lo crea 05_contexto.py)
POBLADOS = PROCESSED / "poblados.csv"                           # factor E (lo crea 05_contexto.py)

# Predicción (lo crea pipeline/06_prediccion.py)
PREDICCION_CLIMA = PROCESSED / "prediccion_clima.parquet"
PREDICCION_MODELO = PROCESSED / "prediccion_modelo.json"
