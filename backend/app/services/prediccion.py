"""
Predicción de riesgo de fuego para las próximas 1–12 semanas (modelo de pipeline/06_prediccion.py).

p      = climatología: probabilidad de que la celda (~11 km) tenga al menos un foco VIIRS esa semana
p'     = p ajustada por las condiciones actuales de su provincia (últimos 7 días, datos FIRMS en vivo):
         r = (celdas con fuego observadas + 5) / (esperadas + 5)
         p' = 1 - (1 - p) ^ (r ^ (beta * decaimiento^(h-1)))
Es un RIESGO ESTACIONAL ESPERADO, no la certeza de que ocurra un incendio.
"""
import json
from datetime import date, datetime, timedelta, timezone

import duckdb
import numpy as np
import pandas as pd

from app import settings
from app.services import firms_client

SEMANAS = 52
HORIZONTE = 12

_m: dict = {}


def disponible() -> bool:
    return settings.PREDICCION_CLIMA.exists() and settings.PREDICCION_MODELO.exists()


def _cargar():
    if _m:
        return _m
    clima = duckdb.sql(f"SELECT * FROM read_parquet('{settings.PREDICCION_CLIMA.as_posix()}')").df()
    region = duckdb.sql(f"SELECT cx, cy, provincia_id, departamento_id, provincia, departamento "
                        f"FROM read_parquet('{settings.CELDAS_REGION.as_posix()}')").df()
    clima["p"] = clima.p.astype("float64").round(4)        # el Parquet guarda float32 (0.41 -> 0.4099999)
    clima = clima.merge(region, on=["cx", "cy"], how="left")
    _m["clima"] = clima
    _m["por_semana"] = {s: g.reset_index(drop=True) for s, g in clima.groupby("semana")}
    _m["modelo"] = json.loads(settings.PREDICCION_MODELO.read_text(encoding="utf-8"))
    _m["nombres_prov"] = region.drop_duplicates("provincia_id").set_index("provincia_id")[["provincia", "departamento"]]
    _m["nombres_dep"] = region.drop_duplicates("departamento_id").set_index("departamento_id").departamento
    _m["razon"] = {"hora": None}
    return _m


def semana_del_anio(d: date) -> int:
    return min((d.timetuple().tm_yday - 1) // 7 + 1, SEMANAS)


def rango_semana(anio: int, semana: int) -> tuple[date, date]:
    inicio = date(anio, 1, 1) + timedelta(days=7 * (semana - 1))
    fin = date(anio, 12, 31) if semana == SEMANAS else inicio + timedelta(days=6)
    return inicio, fin


def semanas_objetivo(hoy: date | None = None) -> list[dict]:
    """Las 12 semanas que vienen después de la semana actual."""
    hoy = hoy or datetime.now(timezone.utc).date()
    out, semana, anio = [], semana_del_anio(hoy), hoy.year
    for h in range(1, HORIZONTE + 1):
        semana += 1
        if semana > SEMANAS:
            semana, anio = 1, anio + 1
        inicio, fin = rango_semana(anio, semana)
        out.append({"h": h, "semana": semana, "anio": anio, "inicio": inicio.isoformat(), "fin": fin.isoformat()})
    return out


def razon_provincias() -> tuple[pd.Series, str]:
    """r de cada provincia con los focos de los últimos 7 días. Si FIRMS falla: r = 1 (solo climatología)."""
    m = _cargar()
    try:
        focos, hora, _ = firms_client.focos_recientes()
    except firms_client.FirmsError as e:
        return pd.Series(dtype=float), f"Sin datos en vivo ({e}); se usa solo la climatología."
    if m["razon"]["hora"] == hora:
        return m["razon"]["r"], m["razon"]["nota"]

    hoy = hora.date()
    # Igual que el histórico: VIIRS S-NPP ("N") y NOAA-20, confianza nominal o alta
    v = focos[(focos.satelite.isin(["N", "N20"])) & ~focos.confianza_baja
              & (focos.momento > hora - timedelta(days=7))]
    celdas = pd.DataFrame({"cx": np.floor(v.lon / settings.TAMANO_CELDA).astype(int),
                           "cy": np.floor(v.lat / settings.TAMANO_CELDA).astype(int)}).drop_duplicates()
    obs = celdas.merge(m["clima"][["cx", "cy", "provincia_id"]].drop_duplicates(), on=["cx", "cy"]) \
                .groupby("provincia_id").size()
    actual = m["por_semana"][semana_del_anio(hoy)]
    esp = actual.groupby("provincia_id").p.sum()
    s = m["modelo"]["suavizado"]
    r = (obs.reindex(esp.index).fillna(0) + s) / (esp + s)
    nota = f"Ajustado con focos VIIRS de los últimos 7 días (hasta {hora:%d/%m %H:%M} UTC)."
    m["razon"] = {"hora": hora, "r": r, "nota": nota}
    return r, nota


def _filtrar(df: pd.DataFrame, region: str) -> pd.DataFrame:
    if region == "peru":
        return df
    if "__" in region:
        return df[df.provincia_id == region]
    return df[df.departamento_id == region]


def prediccion(h: int, region: str = "peru") -> tuple[dict, pd.DataFrame]:
    """Celdas de la semana h con p (climatología) y p_modelo (ajustada)."""
    m = _cargar()
    obj = semanas_objetivo()[h - 1]
    df = _filtrar(m["por_semana"][obj["semana"]], region).copy()
    r, _ = razon_provincias()
    mod = m["modelo"]
    exponente = r.reindex(df.provincia_id).fillna(1.0).to_numpy() ** (mod["beta"] * mod["decaimiento"] ** (h - 1))
    df["p_modelo"] = 1 - (1 - df.p.to_numpy()) ** exponente
    return obj, df


def serie(region: str = "peru") -> list[dict]:
    """Celdas con fuego esperadas en cada una de las próximas 12 semanas (modelo y climatología)."""
    out = []
    for obj in semanas_objetivo():
        _, df = prediccion(obj["h"], region)
        out.append({**obj, "esperado": round(float(df.p_modelo.sum()), 1), "normal": round(float(df.p.sum()), 1),
                    "celdas_alto_riesgo": int((df.p_modelo >= 0.35).sum())})
    return out


def ranking(h: int, nivel: str) -> tuple[dict, pd.DataFrame]:
    obj, df = prediccion(h)
    col = "provincia_id" if nivel == "provincia" else "departamento_id"
    g = df.groupby(col).agg(esperado=("p_modelo", "sum"), normal=("p", "sum"),
                            alto_riesgo=("p_modelo", lambda x: int((x >= 0.35).sum()))).reset_index()
    g = g.rename(columns={col: "id"})
    if nivel == "provincia":
        nombres = _cargar()["nombres_prov"]
        g["nombre"] = g.id.map(nombres.provincia)
        g["departamento"] = g.id.map(nombres.departamento)
    else:
        g["nombre"] = g.id.map(_cargar()["nombres_dep"])
    g["cambio_pct"] = (100 * (g.esperado / g.normal.where(g.normal > 0) - 1)).round(0)
    g[["esperado", "normal"]] = g[["esperado", "normal"]].round(1)
    return obj, g.sort_values("esperado", ascending=False).reset_index(drop=True)


def modelo() -> dict:
    return _cargar()["modelo"]
