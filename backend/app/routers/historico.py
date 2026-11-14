"""Endpoints del histórico armonizado: calendario, climatología, anomalías, ranking."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app import settings
from app.services import datos

router = APIRouter(prefix="/api/historico", tags=["Histórico armonizado"])

Metrica = Literal["dias_celda", "focos"]
DESCRIPCION_METRICA = ("dias_celda = celdas de ~11 km con fuego cada día (recomendado); "
                       "focos = número de focos equivalentes a VIIRS")


def _region_o_404(region_id: str) -> dict:
    r = datos.region(region_id)
    if r is None:
        raise HTTPException(404, f"Región '{region_id}' no existe. Consulta /api/regiones.")
    return r


def _rango(desde: int, hasta: int):
    if desde > hasta:
        raise HTTPException(400, "'desde' no puede ser mayor que 'hasta'.")


@router.get("/calendario")
def calendario(region: str = "peru",
               desde: int = Query(settings.ANIO_CONFIABLE, ge=settings.ANIO_MIN),
               hasta: int = Query(2100),
               metrica: Metrica = Query("dias_celda", description=DESCRIPCION_METRICA)):
    """Calendario de fuego: una celda por año y mes, con su anomalía respecto a la mediana histórica."""
    r = _region_o_404(region)
    _rango(desde, hasta)
    return {"region": r, "metrica": metrica, "celdas": datos.a_json(datos.calendario(region, desde, hasta, metrica))}


@router.get("/climatologia")
def climatologia(region: str = "peru"):
    """Mediana y percentiles de cada mes (2003 en adelante) y qué meses forman la temporada crítica."""
    r = _region_o_404(region)
    df = datos.climatologia(region)
    return {"region": r,
            "meses_criticos": df[df.temporada_critica].mes.tolist(),
            "meses": datos.a_json(df)}


@router.get("/serie-anual")
def serie_anual(region: str = "peru",
                desde: int = Query(settings.ANIO_MIN, ge=settings.ANIO_MIN),
                hasta: int = Query(2100),
                metrica: Metrica = "dias_celda"):
    """Total por año, con intervalo de confianza 90% de la calibración (años antes de 2012)."""
    r = _region_o_404(region)
    _rango(desde, hasta)
    return {"region": r, "metrica": metrica, "anios": datos.a_json(datos.serie_anual(region, desde, hasta, metrica))}


@router.get("/anomalia")
def anomalia(region: str = "peru", anio: int | None = None, mes: int | None = Query(None, ge=1, le=12)):
    """Compara un mes con su mediana histórica. Sin anio/mes: usa el último mes disponible."""
    r = _region_o_404(region)
    if anio is None or mes is None:
        anio, mes = datos.mes_mas_reciente(region)
    df = datos.anomalia(region, anio, mes)
    if df.empty:
        raise HTTPException(404, f"Sin datos para {mes}/{anio}.")
    return {"region": r, **datos.a_json(df)[0]}


@router.get("/ranking")
def ranking(nivel: Literal["departamento", "provincia"] = "departamento",
            desde: int = Query(settings.ANIO_CONFIABLE, ge=settings.ANIO_MIN),
            hasta: int = Query(2100),
            metrica: Metrica = "dias_celda",
            departamento: str | None = Query(None, description="Solo provincias de este departamento (id)")):
    """Regiones ordenadas por actividad de fuego promedio por año."""
    _rango(desde, hasta)
    hasta = min(hasta, datos.mes_mas_reciente("peru")[0])
    df = datos.ranking(nivel, desde, hasta, metrica, departamento)
    return {"nivel": nivel, "desde": desde, "hasta": hasta, "metrica": metrica, "regiones": datos.a_json(df)}
