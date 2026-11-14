"""
Acceso a los datos armonizados con DuckDB.

DuckDB lee los Parquet directamente: no hace falta una base de datos aparte.
Las vistas se crean una vez al iniciar; cada consulta usa su propio cursor
(así varias peticiones a la vez no se pisan).
"""
import json

import duckdb
import pandas as pd

from app import settings

_con: duckdb.DuckDBPyConnection | None = None


def iniciar():
    """Crea la conexión y las vistas. Falla con un mensaje claro si falta correr el pipeline."""
    global _con
    faltan = [p.name for p in (settings.FOCOS, settings.SERIE_REGION, settings.CLIMA_MENSUAL,
                               settings.CELDAS_REGION) if not p.exists()]
    if faltan:
        raise RuntimeError(f"Faltan archivos {faltan}. Ejecuta el pipeline (pasos 1 a 4) primero.")

    _con = duckdb.connect()
    _con.execute(f"CREATE VIEW serie AS SELECT * FROM read_parquet('{settings.SERIE_REGION.as_posix()}')")
    _con.execute(f"CREATE VIEW clima AS SELECT * FROM read_parquet('{settings.CLIMA_MENSUAL.as_posix()}')")
    _con.execute(f"CREATE VIEW focos AS SELECT * FROM read_parquet('{settings.FOCOS.as_posix()}')")
    _con.execute(f"CREATE VIEW celdas_region AS SELECT * FROM read_parquet('{settings.CELDAS_REGION.as_posix()}')")


def consulta(sql: str, params: list | None = None) -> pd.DataFrame:
    return _con.cursor().execute(sql, params or []).df()


def a_json(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> lista de dicts apta para JSON (NaN pasa a null)."""
    return json.loads(df.to_json(orient="records", force_ascii=False))


# ---------------------------------------------------------------------------
# Regiones
# ---------------------------------------------------------------------------
def regiones(nivel: str | None = None) -> pd.DataFrame:
    sql = "SELECT DISTINCT nivel, region_id AS id, region AS nombre FROM serie"
    params = []
    if nivel:
        sql += " WHERE nivel = ?"
        params.append(nivel)
    df = consulta(sql + " ORDER BY nivel, nombre", params)
    # las provincias tienen id "departamento__provincia"
    df["departamento_id"] = df.id.where(df.nivel != "provincia").fillna(df.id.str.split("__").str[0])
    df.loc[df.nivel == "pais", "departamento_id"] = None
    return df


def region(region_id: str) -> dict | None:
    df = consulta("SELECT DISTINCT nivel, region_id AS id, region AS nombre FROM serie WHERE region_id = ?",
                  [region_id])
    return None if df.empty else df.iloc[0].to_dict()


# ---------------------------------------------------------------------------
# Histórico
# ---------------------------------------------------------------------------
def calendario(region_id: str, desde: int, hasta: int, metrica: str) -> pd.DataFrame:
    return consulta(f"""
        SELECT anio, mes,
               {metrica} AS valor, {metrica}_ic90_bajo AS ic90_bajo, {metrica}_ic90_alto AS ic90_alto,
               fuente, calidad, mediana, p75, p90, p95, anomalia_pct, z, percentil, categoria
        FROM serie
        WHERE region_id = ? AND anio BETWEEN ? AND ?
        ORDER BY anio, mes
    """, [region_id, desde, hasta])


def climatologia(region_id: str) -> pd.DataFrame:
    df = consulta("""
        SELECT mes, mediana, p75, p90, p95, media, desv, maximo, n_anios
        FROM clima WHERE region_id = ? ORDER BY mes
    """, [region_id])
    # Temporada crítica: los meses cuya mediana está en el cuartil superior de las 12 medianas
    umbral = df.mediana.quantile(0.75)
    df["temporada_critica"] = df.mediana >= umbral
    total = df.mediana.sum()
    df["porcentaje_del_anio"] = (100 * df.mediana / total).round(1) if total else 0.0
    return df


def serie_anual(region_id: str, desde: int, hasta: int, metrica: str) -> pd.DataFrame:
    return consulta(f"""
        SELECT anio,
               round(sum({metrica}), 1)           AS valor,
               round(sum({metrica}_ic90_bajo), 1) AS ic90_bajo,
               round(sum({metrica}_ic90_alto), 1) AS ic90_alto,
               min(calidad)                        AS calidad_minima
        FROM serie WHERE region_id = ? AND anio BETWEEN ? AND ?
        GROUP BY anio ORDER BY anio
    """, [region_id, desde, hasta])


def mes_mas_reciente(region_id: str) -> tuple[int, int]:
    df = consulta("SELECT max(anio * 100 + mes) AS am FROM serie WHERE region_id = ?", [region_id])
    am = int(df.am.iloc[0])
    return am // 100, am % 100


def anomalia(region_id: str, anio: int, mes: int) -> pd.DataFrame:
    return consulta("""
        SELECT anio, mes, dias_celda AS valor, mediana, p75, p90, p95, media,
               anomalia_pct, z, percentil, categoria, fuente, calidad
        FROM serie WHERE region_id = ? AND anio = ? AND mes = ?
    """, [region_id, anio, mes])


def ranking(nivel: str, desde: int, hasta: int, metrica: str, departamento_id: str | None) -> pd.DataFrame:
    filtro, params = "", [nivel, desde, hasta]
    if departamento_id:
        filtro = "AND split_part(region_id, '__', 1) = ?"
        params.append(departamento_id)
    df = consulta(f"""
        SELECT region_id AS id, region AS nombre,
               round(sum({metrica}) / (? - ? + 1), 1) AS promedio_anual
        FROM serie WHERE nivel = ? AND anio BETWEEN ? AND ? {filtro}
        GROUP BY ALL ORDER BY promedio_anual DESC
    """, [hasta, desde, *params])
    total = df.promedio_anual.sum()
    df["porcentaje"] = (100 * df.promedio_anual / total).round(1) if total else 0.0
    df.insert(0, "puesto", range(1, len(df) + 1))
    return df


# ---------------------------------------------------------------------------
# Focos crudos (descarga CSV)
# ---------------------------------------------------------------------------
def focos(region_id: str, nivel: str, desde: str, hasta: str) -> pd.DataFrame:
    c = settings.TAMANO_CELDA
    filtro, params = "", [desde, hasta]
    if nivel == "departamento":
        filtro, params = "AND r.departamento_id = ?", params + [region_id]
    elif nivel == "provincia":
        filtro, params = "AND r.provincia_id = ?", params + [region_id]
    return consulta(f"""
        SELECT f.fecha, f.hora, f.lat, f.lon, f.sensor, f.satelite, f.confianza, f.frp, f.dia_noche,
               r.departamento, r.provincia
        FROM focos f
        JOIN celdas_region r
          ON r.cx = CAST(floor(f.lon / {c}) AS INTEGER) AND r.cy = CAST(floor(f.lat / {c}) AS INTEGER)
        WHERE f.fecha BETWEEN CAST(? AS DATE) AND CAST(? AS DATE) {filtro}
        ORDER BY f.fecha, f.hora
        LIMIT {settings.MAX_FILAS_CSV}
    """, params)
