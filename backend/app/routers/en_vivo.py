"""Incendios en vivo (datos NRT de FIRMS) con su estado de riesgo."""
import logging
import threading
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app import settings
from app.services import firms_client, riesgo
from app.services.datos import a_json

router = APIRouter(prefix="/api/en-vivo", tags=["En vivo"])

AVISO = ("Datos preliminares (NRT) de NASA FIRMS. Herramienta de apoyo: "
         "no reemplaza las alertas oficiales de SERFOR, SERNANP o INDECI.")


_ultimo: dict = {"hora_firms": None, "resultado": None}
_candado = threading.Lock()
log = logging.getLogger("uvicorn.error")


def _calcular(forzar: bool = False):
    """Pide los focos (con caché) y calcula los eventos solo si llegaron datos nuevos de FIRMS."""
    try:
        focos, hora_firms, errores = firms_client.focos_recientes(forzar)
    except firms_client.FirmsError as e:
        raise HTTPException(503, f"No se pudo consultar NASA FIRMS: {e}") from e
    with _candado:
        if _ultimo["hora_firms"] != hora_firms:
            ahora = datetime.now(timezone.utc)
            _ultimo.update(hora_firms=hora_firms, resultado=riesgo.calcular_eventos(focos, ahora))
        eventos, focos_ev, prov = _ultimo["resultado"]
    return eventos, focos_ev, prov, hora_firms, errores


@router.get("")
def en_vivo(actualizar: bool = Query(False, description="Ignorar la caché y volver a preguntar a FIRMS"),
            incluir_focos: bool = Query(True, description="Incluir cada foco (puntos del mapa)")):
    """Eventos activos (últimas 72 h) en el Perú y la frontera, ordenados por gravedad."""
    eventos, focos_ev, prov, hora, errores = _calcular(actualizar)
    # Cada estado cuenta solo eventos activos; los "en observación" (sin focos en 24 h) van aparte
    resumen = {e: sum(1 for x in eventos if x["estado"] == e and not x["en_observacion"]) for e in riesgo.ESTADOS}
    resumen["en_observacion"] = sum(x["en_observacion"] for x in eventos)
    resumen["por_confirmar"] = sum(x["por_confirmar"] for x in eventos)
    # Para la lista no hace falta la historia ni los factores completos (van en /eventos/{id})
    ligeros = [{k: v for k, v in e.items() if k not in ("historia", "factores", "reglas")} for e in eventos]
    respuesta = {
        "actualizado": hora.isoformat(),
        "proxima_actualizacion_min": settings.CACHE_MINUTOS,
        "zona": settings.BBOX_EN_VIVO,
        "satelites": settings.FUENTES_NRT,
        "aviso": AVISO,
        "advertencias": errores,
        "resumen": resumen,
        "eventos": ligeros,
    }
    if incluir_focos:
        f = focos_ev[["lat", "lon", "momento", "sensor", "satelite", "frp", "confianza", "evento_id"]].copy()
        f["momento"] = f.momento.dt.strftime("%Y-%m-%dT%H:%MZ")
        respuesta["focos"] = a_json(f)
    return respuesta


@router.get("/eventos/{evento_id}")
def ficha(evento_id: str):
    """Ficha de un evento: los 6 factores, las reglas aplicadas y cómo cambió en 48 h."""
    eventos, focos_ev, *_ = _calcular()
    ev = next((e for e in eventos if e["id"] == evento_id), None)
    if ev is None:
        raise HTTPException(404, "El evento ya no está activo (se cerró o se actualizaron los datos).")
    f = focos_ev[focos_ev.evento_id == evento_id][["lat", "lon", "momento", "sensor", "satelite", "frp", "confianza"]].copy()
    f["momento"] = f.momento.dt.strftime("%Y-%m-%dT%H:%MZ")
    return {**ev, "focos": a_json(f), "parametros": riesgo.PARAMETROS}


@router.get("/provincias")
def provincias():
    """Factor C para todas las provincias: actividad de los últimos 7 días vs la misma semana en la historia."""
    *_, prov, hora, _ = _calcular()
    df = prov.reset_index().rename(columns={"region_id": "id", "region": "nombre"})
    return {"actualizado": hora.isoformat(),
            "provincias": a_json(df.sort_values(["puntos_c", "dias_celda_7d"], ascending=False))}


def actualizar_en_segundo_plano():
    """Hilo que refresca los datos cada CACHE_MINUTOS, para que el usuario nunca espere la descarga."""
    def bucle():
        while True:
            try:
                _calcular(forzar=True)
                log.info("En vivo: datos de FIRMS actualizados")
            except Exception as e:                 # que un fallo de red no mate el hilo
                log.warning(f"En vivo: no se pudo actualizar ({e})")
            time.sleep(settings.CACHE_MINUTOS * 60)
    threading.Thread(target=bucle, daemon=True, name="en-vivo").start()
