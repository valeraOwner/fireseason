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
