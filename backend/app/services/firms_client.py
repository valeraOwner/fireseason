"""
Cliente de la API de NASA FIRMS (focos de las últimas horas/días, "NRT").

URL de la API "area":
    https://firms.modaps.eosdis.nasa.gov/api/area/csv/<MAP_KEY>/<FUENTE>/<oeste,sur,este,norte>/<días>[/<fecha>]
    - <días> va de 1 a 5. Sin <fecha> trae los últimos <días> días (hasta hoy, en hora UTC).
    - Con <fecha> trae desde esa fecha hacia adelante.
    Para tener 7 días hacemos 2 pedidos por satélite: los últimos 5 días + los 2 días anteriores.

La MAP_KEY vive solo aquí, en el backend: el navegador nunca la ve.
Las respuestas se guardan en memoria (caché) durante settings.CACHE_MINUTOS para no
gastar el límite de FIRMS (5000 pedidos cada 10 minutos) ni hacer esperar al usuario.
"""
import io
import threading
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from app import settings

URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{fuente}/{bbox}/{dias}"

_cache: dict = {"focos": None, "hora": None, "errores": []}
_candado = threading.Lock()


class FirmsError(RuntimeError):
    pass


def _pedir(fuente: str, dias: int, fecha: str | None = None) -> pd.DataFrame:
    bbox = ",".join(str(x) for x in settings.BBOX_EN_VIVO)
    url = URL.format(key=settings.FIRMS_MAP_KEY, fuente=fuente, bbox=bbox, dias=dias)
    if fecha:
        url += f"/{fecha}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    texto = r.text.strip()
    # FIRMS responde texto plano (no CSV) cuando hay un problema con la clave o los parámetros
    if not texto.startswith("latitude"):
        raise FirmsError(f"{fuente}: {texto[:200]}")
    return pd.read_csv(io.StringIO(texto))


def _normalizar(df: pd.DataFrame, fuente: str) -> pd.DataFrame:
    """Columnas comunes para MODIS y VIIRS (mismos nombres que el histórico)."""
    if df.empty:
        return pd.DataFrame()
    es_viirs = fuente.startswith("VIIRS")
    hora = df.acq_time.astype(int).astype(str).str.zfill(4)            # 631 -> "0631"
    out = pd.DataFrame({
        "lat": df.latitude.astype(float),
        "lon": df.longitude.astype(float),
        "momento": pd.to_datetime(df.acq_date + " " + hora, format="%Y-%m-%d %H%M", utc=True),
        "sensor": "VIIRS" if es_viirs else "MODIS",
        "satelite": df.satellite.astype(str),
        "confianza": df.confidence.astype(str),
        "frp": pd.to_numeric(df.frp, errors="coerce").fillna(0.0),
        "dia_noche": df.daynight,
    })
    # Confianza baja: VIIRS "l"; MODIS < 30 (mismo umbral que el pipeline)
    if es_viirs:
        out["confianza_baja"] = out.confianza.str.lower().eq("l")
    else:
        out["confianza_baja"] = pd.to_numeric(out.confianza, errors="coerce").fillna(0) < 30
    return out


def _descargar_todo() -> tuple[pd.DataFrame, list[str]]:
    hoy = datetime.now(timezone.utc).date()
    antes = (hoy - timedelta(days=settings.DIAS_EN_VIVO - 1)).isoformat()   # 2 días previos a los últimos 5
    partes, errores = [], []
    for fuente in settings.FUENTES_NRT:
        try:
            for dias, fecha in [(5, None), (settings.DIAS_EN_VIVO - 5, antes)]:
                partes.append(_normalizar(_pedir(fuente, dias, fecha), fuente))
        except (requests.RequestException, FirmsError) as e:
            errores.append(f"{fuente}: {e}")   # si un satélite falla, seguimos con los demás
    partes = [p for p in partes if not p.empty]
    if not partes:
        if errores:
            raise FirmsError("; ".join(errores))
        return pd.DataFrame(columns=["lat", "lon", "momento", "sensor", "satelite", "confianza",
                                     "frp", "dia_noche", "confianza_baja"]), errores
    focos = (pd.concat(partes, ignore_index=True)
               .drop_duplicates(["lat", "lon", "momento", "satelite"])   # los 2 pedidos pueden solaparse
               .sort_values("momento", ignore_index=True))
    return focos, errores


def focos_recientes(forzar: bool = False) -> tuple[pd.DataFrame, datetime, list[str]]:
    """Focos de los últimos DIAS_EN_VIVO días. Usa la caché si es reciente.
    Si FIRMS falla y hay datos viejos en caché, devuelve esos (mejor algo que nada)."""
    if not settings.FIRMS_MAP_KEY or settings.FIRMS_MAP_KEY == "pega_tu_clave_aqui":
        raise FirmsError("Falta FIRMS_MAP_KEY en el archivo .env (ver .env.example).")
    with _candado:   # si llegan 2 peticiones a la vez, solo una descarga
        ahora = datetime.now(timezone.utc)
        vigente = _cache["hora"] and ahora - _cache["hora"] < timedelta(minutes=settings.CACHE_MINUTOS)
        if forzar or not vigente:
            try:
                focos, errores = _descargar_todo()
                _cache.update(focos=focos, hora=ahora, errores=errores)
            except (requests.RequestException, FirmsError) as e:
                if _cache["focos"] is None:
                    raise FirmsError(str(e)) from e
                _cache["errores"] = [f"No se pudo actualizar, se muestran datos de las {_cache['hora']:%H:%M} UTC: {e}"]
        return _cache["focos"], _cache["hora"], _cache["errores"]
