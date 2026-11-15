"""
PASO 5 — Contexto para los factores E (población) y F (áreas protegidas) de la política de riesgo.

Descarga:
  - SERNANP (servicio oficial ArcGIS "servicio_descarga"):
        ANP nacionales, zonas reservadas, áreas de conservación regional y privada,
        zonas de amortiguamiento, zonificación interna (solo "Zona de Protección Estricta")
        y reservas PIACI (reservas indígenas y territoriales para pueblos en aislamiento).
  - GeoNames (PE.zip): centros poblados del Perú con su población (cuando se conoce).

Salidas (data/processed/):
  zonas_protegidas.geojson   polígonos con su "zona": estricta | anp | amortiguamiento | cerca (a < 5 km de un ANP/PIACI)
  poblados.csv               nombre, lat, lon, poblacion

El backend usa estos archivos para calcular, foco por foco, si cae dentro de un área protegida y a qué
distancia está el poblado más cercano.

Uso (desde la carpeta fireseason/):
    python pipeline/05_contexto.py
    python pipeline/05_contexto.py --forzar      # vuelve a descargar aunque ya existan los archivos
"""
import argparse
import io
import zipfile

import geopandas as gpd
import pandas as pd
import requests

import config

SERNANP = ("https://geoservicios.sernanp.gob.pe/arcgis/rest/services/"
           "sernanp_visor/servicio_descarga/MapServer/{capa}/query")
GEONAMES = "https://download.geonames.org/export/dump/PE.zip"
CABECERA = {"User-Agent": "FireSeason/0.1 (NASA Space Apps)"}

# capa del servicio -> (zona según la política, columna con el nombre, filtro SQL)
CAPAS = {
    "anp_nacional":     (1,  "anp",             "anp_nomb", "1=1"),
    "zona_reservada":   (2,  "anp",             "zr_nomb",  "1=1"),
    "acr":              (3,  "anp",             "acr_nomb", "1=1"),
    "acp":              (4,  "anp",             "acp_nomb", "1=1"),
    "amortiguamiento":  (8,  "amortiguamiento", "anp_nomb", "1=1"),
    "proteccion_estricta": (9, "estricta",      "anp_nomb", "tz_nomb = 'Zona de Protección Estricta'"),
    # Solo reservas ya creadas; las "solicitudes de creación" aún no tienen protección legal
    "piaci":            (32, "estricta",        "ri_nomb",  "ri_cate IN ('Reserva Indígena', 'Reserva Territorial')"),
}

DISTANCIA_CERCA_M = 5_000      # factor F: "a menos de 5 km" de un ANP o reserva
UTM_PERU = "EPSG:32718"        # UTM 18S: zona central del Perú, para medir en metros

# Tipos de GeoNames que NO son un poblado habitado hoy
GEONAMES_DESCARTAR = {"PPLX", "PPLH", "PPLQ", "PPLW", "PPLCH"}


def descargar_capa(capa: int, filtro: str) -> gpd.GeoDataFrame:
    """Baja una capa de ArcGIS en GeoJSON, por páginas (el servidor limita cuántas filas da por pedido)."""
    partes, desde = [], 0
    while True:
        r = requests.get(SERNANP.format(capa=capa), headers=CABECERA, timeout=180, params={
            "where": filtro, "outFields": "*", "outSR": 4326, "f": "geojson",
            "resultOffset": desde, "resultRecordCount": 500,
            "maxAllowableOffset": 0.0005,      # simplifica bordes a ~50 m (archivos más livianos)
            "geometryPrecision": 5,
        })
        r.raise_for_status()
        datos = r.json()
        if "error" in datos:
            raise RuntimeError(f"SERNANP capa {capa}: {datos['error']}")
        if not datos.get("features"):
            break
        partes.append(gpd.GeoDataFrame.from_features(datos["features"], crs=4326))
        if not datos.get("exceededTransferLimit") and not datos.get("properties", {}).get("exceededTransferLimit"):
            break
        desde += len(datos["features"])
    return pd.concat(partes, ignore_index=True) if partes else gpd.GeoDataFrame(geometry=[], crs=4326)


def zonas_protegidas(forzar: bool) -> gpd.GeoDataFrame:
    config.CONTEXTO.mkdir(parents=True, exist_ok=True)
    capas = []
    for nombre, (capa, zona, col_nombre, filtro) in CAPAS.items():
        archivo = config.CONTEXTO / f"sernanp_{nombre}.geojson"
        if forzar or not archivo.exists():
            print(f"   descargando {nombre} (capa {capa}) ...")
            gdf = descargar_capa(capa, filtro)
            gdf.to_file(archivo, driver="GeoJSON")
        gdf = gpd.read_file(archivo)
        print(f"   {nombre:<20} {len(gdf):>5} polígonos -> {zona}")
        capas.append(gpd.GeoDataFrame({
            "zona": zona, "tipo": nombre, "nombre": gdf[col_nombre].astype(str).str.strip(),
        }, geometry=gdf.geometry.make_valid(), crs=4326))
    zonas = pd.concat(capas, ignore_index=True)
    zonas = zonas[~zonas.geometry.is_empty & zonas.geometry.notna()]

    # "cerca": franja de 5 km alrededor de ANP y reservas PIACI (se mide en metros con UTM)
    nucleo = zonas[zonas.zona.isin(["anp", "estricta"])].to_crs(UTM_PERU)
    cerca = nucleo.copy()
    cerca["geometry"] = nucleo.buffer(DISTANCIA_CERCA_M, quad_segs=4).simplify(100)
    cerca["zona"], cerca["tipo"] = "cerca", "a menos de 5 km"
    zonas = pd.concat([zonas, cerca.to_crs(4326)], ignore_index=True)
    return gpd.GeoDataFrame(zonas, geometry="geometry", crs=4326)


def poblados(forzar: bool) -> pd.DataFrame:
    """Centros poblados de GeoNames. Formato: https://download.geonames.org/export/dump/readme.txt"""
    archivo = config.CONTEXTO / "geonames_PE.zip"
    if forzar or not archivo.exists():
        print("   descargando GeoNames PE.zip ...")
        r = requests.get(GEONAMES, headers=CABECERA, timeout=300)
        r.raise_for_status()
        archivo.write_bytes(r.content)
    columnas = ["geonameid", "name", "asciiname", "alternatenames", "latitude", "longitude", "feature_class",
                "feature_code", "country_code", "cc2", "admin1", "admin2", "admin3", "admin4", "population",
                "elevation", "dem", "timezone", "modification_date"]
    with zipfile.ZipFile(archivo) as z, z.open("PE.txt") as f:
        df = pd.read_csv(io.TextIOWrapper(f, encoding="utf-8"), sep="\t", header=None, names=columnas,
                         usecols=["name", "latitude", "longitude", "feature_class", "feature_code", "population"],
                         quoting=3, low_memory=False)
    df = df[(df.feature_class == "P") & ~df.feature_code.isin(GEONAMES_DESCARTAR)]
    return pd.DataFrame({"nombre": df.name, "lat": df.latitude.round(5), "lon": df.longitude.round(5),
                         "poblacion": df.population.fillna(0).astype(int), "tipo": df.feature_code})


def main():
    parser = argparse.ArgumentParser(description="Contexto para los factores E y F")
    parser.add_argument("--forzar", action="store_true", help="volver a descargar")
    args = parser.parse_args()

    print("1/2 Áreas protegidas (SERNANP) ...")
    zonas = zonas_protegidas(args.forzar)
    salida = config.PROCESSED / "zonas_protegidas.geojson"
    zonas.to_file(salida, driver="GeoJSON")
    print(f"   -> {salida.name}: {len(zonas)} polígonos", zonas.zona.value_counts().to_dict())

    print("2/2 Centros poblados (GeoNames) ...")
    pob = poblados(args.forzar)
    salida = config.PROCESSED / "poblados.csv"
    pob.to_csv(salida, index=False)
    print(f"   -> {salida.name}: {len(pob)} poblados, {int((pob.poblacion > 0).sum())} con población conocida, "
          f"{int((pob.poblacion >= 1000).sum())} con 1000 habitantes o más")


if __name__ == "__main__":
    main()
