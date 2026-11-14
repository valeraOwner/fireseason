"""Lista de regiones y sus límites (GeoJSON) para el mapa."""
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app import settings
from app.services import datos

router = APIRouter(prefix="/api/regiones", tags=["Regiones"])


@router.get("")
def listar(nivel: Literal["pais", "departamento", "provincia"] | None = None):
    """País, departamentos y provincias disponibles (id + nombre)."""
    return datos.a_json(datos.regiones(nivel))


@router.get("/geojson/{nivel}")
def geojson(nivel: Literal["departamentos", "provincias"]):
    """Límites para dibujar en el mapa."""
    return FileResponse(settings.REGIONES / f"{nivel}.geojson", media_type="application/geo+json")
