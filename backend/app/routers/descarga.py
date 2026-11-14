"""Descarga CSV de los focos detectados en una búsqueda."""
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app import settings
from app.services import datos

router = APIRouter(prefix="/api/descargar", tags=["Descargas"])


@router.get("/focos.csv")
def focos_csv(region: str = "peru",
              desde: date = Query(..., description="AAAA-MM-DD"),
              hasta: date = Query(..., description="AAAA-MM-DD")):
    """Focos limpios (MODIS + VIIRS, solo vegetación) de una región y rango de fechas."""
    r = datos.region(region)
    if r is None:
        raise HTTPException(404, f"Región '{region}' no existe.")
    if desde > hasta:
        raise HTTPException(400, "'desde' no puede ser mayor que 'hasta'.")

    df = datos.focos(region, r["nivel"], desde.isoformat(), hasta.isoformat())
    nombre = f"fireseason_focos_{region}_{desde}_{hasta}.csv"
    cabecera = {"Content-Disposition": f'attachment; filename="{nombre}"',
                "X-Filas": str(len(df)),
                "X-Truncado": str(len(df) >= settings.MAX_FILAS_CSV).lower()}
    # utf-8-sig: Excel abre bien las tildes
    return Response(df.to_csv(index=False).encode("utf-8-sig"), media_type="text/csv", headers=cabecera)
