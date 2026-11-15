"""Riesgo de fuego esperado para las próximas 1–12 semanas."""
from typing import Literal

import numpy as np

from fastapi import APIRouter, HTTPException, Query

from app.services import prediccion as pred
from app.services.datos import a_json

router = APIRouter(prefix="/api/prediccion", tags=["Predicción"])

AVISO = ("Riesgo estacional esperado según 13 años de datos VIIRS (2013–2025), ajustado levemente por la "
         "actividad de los últimos 7 días. No es la certeza de que ocurra un incendio.")
UMBRAL_MAPA = 0.03       # celdas con menos probabilidad no se envían (mapa más liviano)


def _verificar():
    if not pred.disponible():
        raise HTTPException(503, "Falta el modelo: ejecuta python pipeline/06_prediccion.py")


@router.get("/semanas")
def semanas(region: str = "peru"):
    """Las próximas 12 semanas: celdas con fuego esperadas (modelo) vs lo normal (climatología)."""
    _verificar()
    _, nota = pred.razon_provincias()
    return {"region": region, "aviso": AVISO, "ajuste": nota, "semanas": pred.serie(region)}


@router.get("/celdas")
def celdas(h: int = Query(1, ge=1, le=12, description="Semanas hacia adelante"), region: str = "peru"):
    """Probabilidad de fuego de cada celda de 0.1° en la semana elegida (para el mapa)."""
    _verificar()
    obj, df = pred.prediccion(h, region)
    df = df[df.p_modelo >= UMBRAL_MAPA]
    # Formato compacto: [cx, cy, p_modelo, p_climatologia]
    filas = np.column_stack([df.cx, df.cy, df.p_modelo.round(3), df.p.round(3)]).tolist() if len(df) else []
    return {**obj, "tamano_celda": 0.1, "columnas": ["cx", "cy", "p", "p_normal"], "celdas": filas}


@router.get("/ranking")
def ranking(h: int = Query(1, ge=1, le=12), nivel: Literal["departamento", "provincia"] = "provincia",
            limite: int = Query(15, ge=1, le=200)):
    """Regiones con más fuego esperado en la semana elegida."""
    _verificar()
    obj, df = pred.ranking(h, nivel)
    return {**obj, "nivel": nivel, "regiones": a_json(df.head(limite))}


@router.get("/modelo")
def modelo():
    """Cómo se construyó el modelo y qué tan bien predice (validación en años que no vio)."""
    _verificar()
    return pred.modelo()
