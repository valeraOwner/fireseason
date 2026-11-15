"""
FireSeason API.

Arrancar (desde la carpeta backend/, con el entorno activado):
    uvicorn app.main:app --reload
Documentación interactiva: http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import settings
from app.routers import descarga, en_vivo, historico, metodologia, regiones
from app.services import datos


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    datos.iniciar()          # abre DuckDB y registra los Parquet del pipeline
    en_vivo.actualizar_en_segundo_plano()   # descarga focos de FIRMS cada 15 min
    yield


app = FastAPI(
    title="FireSeason API",
    description="Actividad de fuego armonizada MODIS + VIIRS (NASA FIRMS) para el Perú, e incendios en vivo con estado de riesgo.",
    version="0.1.0",
    lifespan=ciclo_de_vida,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ORIGENES_PERMITIDOS,
    allow_methods=["GET"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-Filas", "X-Truncado"],
)

app.include_router(regiones.router)
app.include_router(historico.router)
app.include_router(descarga.router)
app.include_router(metodologia.router)
app.include_router(en_vivo.router)


@app.get("/api/salud", tags=["Sistema"])
def salud():
    return {"estado": "ok"}
