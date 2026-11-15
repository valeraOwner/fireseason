"""
Contexto de cada foco: ¿cae en un área protegida? ¿a qué distancia está el poblado más cercano?
(factores E y F de docs/POLITICA_ESTADOS.md)

Usa los archivos que crea pipeline/05_contexto.py:
    zonas_protegidas.geojson   (SERNANP: ANP, amortiguamiento, protección estricta, reservas PIACI, franja de 5 km)
    poblados.csv               (GeoNames: centros poblados y su población)

En lugar de una tabla por celda de 11 km, se calcula foco por foco (más exacto y igual de rápido):
un "STRtree" es un índice espacial que encuentra en milisegundos qué polígonos contienen un punto
o qué poblados están a menos de 5 km.
"""
import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import STRtree, points

from app import settings

UTM_PERU = "EPSG:32718"          # UTM 18S, para medir distancias en metros
GRAVEDAD_ZONA = {"estricta": 4, "anp": 3, "amortiguamiento": 2, "cerca": 1}

_ctx: dict = {}


def disponible() -> bool:
    return settings.ZONAS_PROTEGIDAS.exists() and settings.POBLADOS.exists()


def _cargar():
    if _ctx:
        return _ctx
    zonas = gpd.read_file(settings.ZONAS_PROTEGIDAS)
    _ctx["zonas"] = zonas
    _ctx["arbol_zonas"] = STRtree(zonas.geometry.values)
    _ctx["gravedad"] = zonas.zona.map(GRAVEDAD_ZONA).to_numpy()

    pob = pd.read_csv(settings.POBLADOS)
    pob_utm = gpd.GeoSeries(points(pob.lon, pob.lat), crs=4326).to_crs(UTM_PERU)
    _ctx["poblados"] = pob
    _ctx["poblados_utm"] = pob_utm.values
    _ctx["arbol_poblados"] = STRtree(pob_utm.values)
    return _ctx


def anotar(lat: np.ndarray, lon: np.ndarray) -> pd.DataFrame:
    """Para cada foco devuelve: zona, zona_nombre, dist_poblado_km, poblado, pob_5km."""
    c = _cargar()
    n = len(lat)
    pts = points(lon, lat)
    out = pd.DataFrame({"zona": pd.Series([None] * n, dtype=object), "zona_nombre": None,
                        "dist_poblado_km": np.nan, "poblado": None, "pob_5km": 0.0})
    if n == 0:
        return out

    # F: polígonos que contienen cada foco; si hay varios, gana el más estricto
    foco, poligono = c["arbol_zonas"].query(pts, predicate="within")
    if len(foco):
        pares = pd.DataFrame({"foco": foco, "pol": poligono, "g": c["gravedad"][poligono]})
        mejor = pares.sort_values("g", ascending=False).drop_duplicates("foco")
        out.loc[mejor.foco, "zona"] = c["zonas"].zona.to_numpy()[mejor.pol]
        out.loc[mejor.foco, "zona_nombre"] = c["zonas"].nombre.to_numpy()[mejor.pol]

    # E: poblado más cercano y habitantes a menos de 5 km
    pts_utm = gpd.GeoSeries(pts, crs=4326).to_crs(UTM_PERU).values
    idx, dist = c["arbol_poblados"].query_nearest(pts_utm, return_distance=True, all_matches=False)
    out.loc[idx[0], "dist_poblado_km"] = dist / 1000
    out.loc[idx[0], "poblado"] = c["poblados"].nombre.to_numpy()[idx[1]]
    foco, pob = c["arbol_poblados"].query(pts_utm, predicate="dwithin", distance=5000)
    if len(foco):
        suma = pd.Series(c["poblados"].poblacion.to_numpy()[pob]).groupby(foco).sum()
        out.loc[suma.index, "pob_5km"] = suma.to_numpy()
    return out
