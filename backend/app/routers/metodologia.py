"""Transparencia del método: factores de calibración y su validación."""
import pandas as pd
from fastapi import APIRouter

from app import settings
from app.services import datos

router = APIRouter(prefix="/api/metodologia", tags=["Metodología"])


@router.get("/factores")
def factores():
    """Factor MODIS -> VIIRS por mes, con intervalo de confianza 90%."""
    return datos.a_json(pd.read_csv(settings.FACTORES))


@router.get("/validacion")
def validacion():
    """Error al predecir VIIRS con MODIS calibrado (dejando un año fuera)."""
    nac = pd.read_csv(settings.VALIDACION)
    dep = pd.read_csv(settings.VALIDACION_DEP)
    resumen = (nac.groupby("metrica")
                  .agg(error_abs_medio_pct=("error_pct_mensual", lambda x: round(x.abs().mean(), 1)),
                       r2_mensual_medio=("r2_meses", lambda x: round(x.mean(), 3)))
                  .reset_index())
    return {"nacional_resumen": datos.a_json(resumen),
            "nacional_por_anio": datos.a_json(nac),
            "departamentos": datos.a_json(dep)}
