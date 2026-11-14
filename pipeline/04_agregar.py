"""
PASO 4 — Agregar la actividad de fuego armonizada por región (país, departamento, provincia)
y calcular lo que necesitan la web y la política de estados.

Entradas: data/processed/celdas_dia.parquet, factores_calibracion.csv   (paso 3)
          data/regiones/geoBoundaries-PER-ADM2_simplified.geojson        (provincias, IGN 2020)
          data/regiones/geoBoundaries-PER-ADM1_simplified.geojson        (departamentos)

Salidas (data/processed/):
  celdas_region.parquet           a qué provincia/departamento pertenece cada celda 0.1°
  serie_mensual_region.parquet    serie armonizada por región y mes + climatología + anomalía
  climatologia_mensual.parquet    mediana y percentiles por región y mes (2003->hoy)
  clima_semanal_provincia.parquet percentiles por provincia y semana  -> factor C de la política
  frecuencia_celda_mes.parquet    % de años con fuego por celda y mes -> factor D de la política
  validacion_departamentos.csv    ¿el factor nacional funciona en cada departamento?
Salidas (data/regiones/): departamentos.geojson, provincias.geojson  (para el mapa web)
Figura: docs/figuras/ranking_departamentos.png

Uso:  python pipeline/04_agregar.py
"""
import unicodedata

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd

import config

CELDAS_DIA = config.PROCESSED / "celdas_dia.parquet"
FACTORES = config.PROCESSED / "factores_calibracion.csv"
CELDAS_REGION = config.PROCESSED / "celdas_region.parquet"
SERIE_REGION = config.PROCESSED / "serie_mensual_region.parquet"
CLIMA_MENSUAL = config.PROCESSED / "climatologia_mensual.parquet"
CLIMA_SEMANAL = config.PROCESSED / "clima_semanal_provincia.parquet"
FRECUENCIA = config.PROCESSED / "frecuencia_celda_mes.parquet"
VALID_DEP = config.PROCESSED / "validacion_departamentos.csv"

METRICAS = ["dias_celda", "focos"]
ANIOS_CLIMA = (config.SERIE_INICIO_CONFIABLE, config.ULTIMO_ANIO_COMPLETO)  # 2003-2025
UTM_PERU = "EPSG:32718"                 # proyección en metros (UTM 18S) para distancias


def slug(texto: str) -> str:
    """'Madre de Dios' -> 'madre-de-dios' (ids sin tildes ni espacios)."""
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "-".join(t.lower().split())


# ---------------------------------------------------------------------------
# 1. Límites administrativos
# ---------------------------------------------------------------------------
def preparar_limites():
    dep = gpd.read_file(config.REGIONES / "geoBoundaries-PER-ADM1_simplified.geojson")
    prov = gpd.read_file(config.REGIONES / "geoBoundaries-PER-ADM2_simplified.geojson")

    # En ADM1, Lima Metropolitana viene separada de Lima: la unimos. "El Callao" -> "Callao".
    dep["shapeName"] = dep.shapeName.replace({"Municipalidad Metropolitana de Lima": "Lima",
                                              "El Callao": "Callao"})

    # ADM2 no trae el departamento: cada provincia va al departamento con el que comparte más área
    # (con un punto interior fallaba en Callao, que es muy pequeño).
    prov_m, dep_m = prov.to_crs(UTM_PERU), dep.to_crs(UTM_PERU)
    prov_m["prov_idx"] = prov_m.index
    cruce = gpd.overlay(prov_m[["prov_idx", "geometry"]],
                        dep_m[["shapeName", "geometry"]].rename(columns={"shapeName": "departamento"}),
                        how="intersection", keep_geom_type=True)
    cruce["area"] = cruce.area
    mejor = cruce.sort_values("area").drop_duplicates("prov_idx", keep="last").set_index("prov_idx")
    prov["departamento"] = prov.index.map(mejor.departamento)
    prov["nombre"] = prov.shapeName
    prov["id"] = [f"{slug(d)}__{slug(p)}" for d, p in zip(prov.departamento, prov.nombre)]
    prov = prov[["id", "nombre", "departamento", "geometry"]]

    # Departamentos = unión de sus provincias (así ambos niveles encajan exactamente)
    deps = prov.dissolve(by="departamento", as_index=False)[["departamento", "geometry"]]
    deps["id"] = deps.departamento.map(slug)
    deps = deps.rename(columns={"departamento": "nombre"})[["id", "nombre", "geometry"]]

    prov.to_file(config.REGIONES / "provincias.geojson", driver="GeoJSON")
    deps.to_file(config.REGIONES / "departamentos.geojson", driver="GeoJSON")
    return prov, deps


# ---------------------------------------------------------------------------
# 2. Cada celda 0.1° -> provincia y departamento (por su centro)
# ---------------------------------------------------------------------------
def asignar_celdas(con, prov):
    c = config.TAMANO_CELDA_GRADOS
    celdas = con.execute(f"SELECT DISTINCT cx, cy FROM read_parquet('{CELDAS_DIA.as_posix()}')").df()
    centros = gpd.GeoDataFrame(celdas, geometry=gpd.points_from_xy((celdas.cx + 0.5) * c,
                                                                   (celdas.cy + 0.5) * c), crs="EPSG:4326")
    dentro = gpd.sjoin(centros, prov, how="left", predicate="within")
    dentro = dentro[~dentro.index.duplicated()]

    # Celdas de borde (centro en el mar o en otro país): a la provincia más cercana
    faltan = dentro.id.isna()
    if faltan.any():
        cerca = gpd.sjoin_nearest(centros[faltan].to_crs(UTM_PERU), prov.to_crs(UTM_PERU), how="left")
        cerca = cerca[~cerca.index.duplicated()]
        dentro.loc[faltan, ["id", "nombre", "departamento"]] = cerca[["id", "nombre", "departamento"]].values

    # Ojo: usar dentro["cx"] y no dentro.cx (en GeoPandas, .cx es otra cosa: un indexador espacial)
    tabla = pd.DataFrame({"cx": dentro["cx"], "cy": dentro["cy"], "provincia_id": dentro["id"],
                          "provincia": dentro["nombre"], "departamento": dentro["departamento"]})
    tabla["departamento_id"] = tabla.departamento.map(slug)
    tabla.to_parquet(CELDAS_REGION, index=False)
    return tabla, int(faltan.sum())


# ---------------------------------------------------------------------------
# 3. Conteos por región y armonización (mismo método que el paso 3)
# ---------------------------------------------------------------------------
SQL_GRUPOS = f"""
    WITH c AS (SELECT * FROM read_parquet('{CELDAS_DIA.as_posix()}')),
    dias_snpp AS (SELECT DISTINCT fecha FROM c WHERE satelite = 'S-NPP'),
    grupos AS (
        SELECT 'MODIS' AS grupo, fecha, cx, cy, n_focos FROM c WHERE satelite IN ('Terra', 'Aqua')
        UNION ALL SELECT 'TERRA', fecha, cx, cy, n_focos FROM c WHERE satelite = 'Terra'
        UNION ALL SELECT 'VIIRS', fecha, cx, cy, n_focos FROM c WHERE satelite = 'S-NPP'
        UNION ALL SELECT 'VIIRS', fecha, cx, cy, n_focos FROM c
                  WHERE satelite = 'NOAA-20' AND fecha NOT IN (SELECT fecha FROM dias_snpp)
    ),
    por_celda AS (
        SELECT grupo, fecha, cx, cy, sum(n_focos) AS n FROM grupos GROUP BY ALL
    )
    SELECT * FROM por_celda JOIN celdas_region USING (cx, cy)
"""


def conteos(con, columna_region: str, con_semana=False) -> pd.DataFrame:
    semana = ", least((dayofyear(fecha) - 1) // 7 + 1, 52) AS semana" if con_semana else ""
    return con.execute(f"""
        SELECT {columna_region} AS region_id, grupo, year(fecha) AS anio, month(fecha) AS mes {semana},
               count(*) AS dias_celda, sum(n) AS focos
        FROM ({SQL_GRUPOS}) GROUP BY ALL
    """).df()


def armonizar(df: pd.DataFrame, factores: pd.DataFrame, claves: list, ajuste: dict | None = None) -> pd.DataFrame:
    """df largo (por grupo) -> una fila por clave con valor armonizado de cada métrica.
    ajuste: {region_id: k} corrección regional que multiplica el factor nacional (paso 6)."""
    ancho = df.pivot_table(index=claves, columns="grupo", values=METRICAS, fill_value=0, aggfunc="sum")
    ancho.columns = [f"{g}_{m}" for m, g in ancho.columns]
    ancho = ancho.reset_index()
    for g in ["MODIS", "TERRA", "VIIRS"]:
        for m in METRICAS:
            if f"{g}_{m}" not in ancho:
                ancho[f"{g}_{m}"] = 0

    inicio = pd.to_datetime(dict(year=ancho.anio, month=ancho.mes, day=1)).dt.date
    es_viirs = inicio >= config.VIIRS_INICIO
    es_modis = (inicio >= config.AQUA_INICIO) & ~es_viirs
    ancho["fuente"] = np.select([es_viirs, es_modis], ["VIIRS", "MODIS"], "TERRA")
    k = ancho.region_id.map(ajuste).fillna(1.0) if ajuste else pd.Series(1.0, index=ancho.index)

    for m in METRICAS:
        f = factores[factores.metrica == m]
        resultado = {"valor": ancho[f"VIIRS_{m}"].astype(float)}
        resultado["bajo"] = resultado["valor"].copy()
        resultado["alto"] = resultado["valor"].copy()
        for base, mascara in [("MODIS", es_modis), ("TERRA", ~es_viirs & ~es_modis)]:
            fb = f[f.base == base].set_index("mes")
            crudo = ancho.loc[mascara, f"{base}_{m}"] * k[mascara]
            meses = ancho.loc[mascara, "mes"]
            resultado["valor"][mascara] = crudo * meses.map(fb.factor)
            resultado["bajo"][mascara] = crudo * meses.map(fb.ic90_bajo)
            resultado["alto"][mascara] = crudo * meses.map(fb.ic90_alto)
        ancho[m] = resultado["valor"].round(1)
        ancho[f"{m}_ic90_bajo"] = resultado["bajo"].round(1)
        ancho[f"{m}_ic90_alto"] = resultado["alto"].round(1)
    return ancho


def completar(df, regiones, claves_tiempo, rangos):
    """Agrega filas en 0 para meses/semanas sin fuego (un mes sin fuego es 0, no 'falta')."""
    idx = pd.MultiIndex.from_product([regiones, *rangos], names=["region_id", *claves_tiempo])
    cols = [c for c in df.columns if c not in ["region_id", *claves_tiempo]]
    out = df.set_index(["region_id", *claves_tiempo])[cols].groupby(level=list(range(len(idx.names)))).sum(numeric_only=True)
    return out.reindex(idx, fill_value=0).reset_index()


# ---------------------------------------------------------------------------
# 4. Climatología y anomalías
# ---------------------------------------------------------------------------
def climatologia(serie: pd.DataFrame, claves: list) -> pd.DataFrame:
    base = serie[serie.anio.between(*ANIOS_CLIMA)]
    g = base.groupby(claves).dias_celda
    return pd.DataFrame({
        "mediana": g.median(), "p75": g.quantile(0.75), "p90": g.quantile(0.90), "p95": g.quantile(0.95),
        "media": g.mean(), "desv": g.std(), "maximo": g.max(), "n_anios": g.count(),
    }).round(1).reset_index()


def anomalias(serie: pd.DataFrame, clima: pd.DataFrame, claves: list) -> pd.DataFrame:
    s = serie.merge(clima, on=claves, how="left")
    v = s.dias_celda
    s["anomalia_pct"] = np.where(s.mediana > 0, 100 * (v - s.mediana) / s.mediana, np.nan).round(1)
    s["z"] = np.where(s.desv > 0, (v - s.media) / s.desv, np.nan).round(2)
    s["categoria"] = np.select([v > s.p95, v > s.p90, v > s.p75, v <= s.mediana],
                               ["extremo", "muy alto", "sobre lo normal", "normal o menor"],
                               "levemente sobre la mediana")
    # Percentil empírico: % de años de la climatología con un valor menor o igual
    base = serie[serie.anio.between(*ANIOS_CLIMA)][claves + ["dias_celda"]]
    ref = base.groupby(claves).dias_celda.apply(lambda x: np.sort(x.to_numpy()))
    s["percentil"] = [round(100 * np.searchsorted(ref[k], val, side="right") / len(ref[k]))
                      if k in ref.index else np.nan
                      for k, val in zip(s[claves].itertuples(index=False, name=None), v)]
    return s


# ---------------------------------------------------------------------------
# 5. Frecuencia histórica por celda (factor D: "zona inusual")
#    Solo VIIRS 2013-hoy para que todos los años midan igual.
# ---------------------------------------------------------------------------
def frecuencia_celdas(con):
    a0, a1 = 2013, config.ULTIMO_ANIO_COMPLETO
    con.execute(f"""
        COPY (
            WITH v AS ({SQL_GRUPOS})
            SELECT cx, cy, month(fecha) AS mes,
                   count(DISTINCT year(fecha)) AS anios_con_fuego,
                   {a1 - a0 + 1} AS n_anios,
                   round(count(DISTINCT year(fecha)) / {a1 - a0 + 1}, 3) AS frecuencia
            FROM v WHERE grupo = 'VIIRS' AND year(fecha) BETWEEN {a0} AND {a1}
            GROUP BY ALL
        ) TO '{FRECUENCIA.as_posix()}' (FORMAT parquet)
    """)


# ---------------------------------------------------------------------------
# 6. Ajuste regional del factor + validación por departamento
#    El factor nacional no calza igual en todas partes (selva vs sierra: distinto tamaño de fuegos).
#    k_dep = VIIRS observado / (MODIS x factor nacional) en 2012-2021.
#    Se valida dejando un año fuera: k se calcula SIN el año que se predice.
# ---------------------------------------------------------------------------
K_MIN, K_MAX = 0.5, 2.0          # límites de seguridad
MIN_DIAS_CELDA_CALIB = 500       # con menos actividad, k = 1 (muy poca información)


def _anual_calibracion(dep_mes, factores):
    f = factores[(factores.base == "MODIS") & (factores.metrica == "dias_celda")].set_index("mes").factor
    d = dep_mes[dep_mes.anio.between(config.CALIB_ANIO_INICIO, config.CALIB_ANIO_FIN)
                & (dep_mes.fuente == "VIIRS")].copy()
    d["pred"] = d.MODIS_dias_celda * d.mes.map(f)
    return d.groupby(["region_id", "anio"])[["VIIRS_dias_celda", "pred"]].sum().reset_index()


def _k(filas):
    obs, pred = filas.VIIRS_dias_celda.sum(), filas.pred.sum()
    if obs < MIN_DIAS_CELDA_CALIB or pred <= 0:
        return 1.0
    return float(np.clip(obs / pred, K_MIN, K_MAX))


def ajuste_regional(dep_mes, factores):
    anual = _anual_calibracion(dep_mes, factores)
    k = {r: round(_k(g), 3) for r, g in anual.groupby("region_id")}

    filas = []
    for r, g in anual.groupby("region_id"):
        for anio in g.anio:
            prueba = g[g.anio == anio].iloc[0]
            if prueba.VIIRS_dias_celda < 50:            # año con muy poco fuego: no se evalúa
                continue
            k_sin = _k(g[g.anio != anio])
            e_nac = 100 * (prueba.pred - prueba.VIIRS_dias_celda) / prueba.VIIRS_dias_celda
            e_aj = 100 * (prueba.pred * k_sin - prueba.VIIRS_dias_celda) / prueba.VIIRS_dias_celda
            filas.append(dict(region_id=r, anio=anio, viirs=prueba.VIIRS_dias_celda, e_nac=e_nac, e_aj=e_aj))
    v = pd.DataFrame(filas)
    res = v.groupby("region_id").agg(
        viirs_anual_medio=("viirs", "mean"),
        error_factor_nacional_pct=("e_nac", lambda x: x.abs().mean()),
        error_con_ajuste_pct=("e_aj", lambda x: x.abs().mean()),
    ).round(1)
    res["k"] = res.index.map(k)
    res = res.sort_values("viirs_anual_medio", ascending=False).reset_index()
    res.to_csv(VALID_DEP, index=False)

    # error ponderado por actividad (los departamentos con más fuego pesan más)
    w = v.viirs
    global_nac = float((v.e_nac.abs() * w).sum() / w.sum())
    global_aj = float((v.e_aj.abs() * w).sum() / w.sum())
    return k, res, global_nac, global_aj


# ---------------------------------------------------------------------------
# 7. Figura: ranking de departamentos
# ---------------------------------------------------------------------------
def figura_ranking(serie_dep: pd.DataFrame, nombres: dict):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    INK, MUTED, GRID, NARANJA = "#1f1f1e", "#6b6b66", "#e4e3df", "#eb6834"
    plt.rcParams.update({"font.size": 10, "xtick.color": MUTED, "ytick.color": INK, "text.color": INK})

    base = serie_dep[serie_dep.anio.between(*ANIOS_CLIMA)]
    anual = base.groupby("region_id").dias_celda.sum() / (ANIOS_CLIMA[1] - ANIOS_CLIMA[0] + 1)
    anual = anual.sort_values()
    top3 = anual.iloc[-3:].sum() / anual.sum()
    etiquetas = [nombres[i] for i in anual.index]

    fig, ax = plt.subplots(figsize=(8, 8), dpi=150)
    ax.barh(etiquetas, anual.values, color=NARANJA, height=0.7)
    for i, (nombre, val) in enumerate(zip(etiquetas, anual.values)):
        if i >= len(anual) - 3:                       # etiquetas solo en el top 3
            ax.text(val + anual.max() * 0.01, i, f"{val:,.0f}".replace(",", " "), va="center", fontsize=9)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    for lado in ["top", "right", "left", "bottom"]:
        ax.spines[lado].set_visible(False)
    ax.set_xlabel("días-celda con fuego por año (promedio 2003–2025, escala VIIRS)", color=MUTED)
    n1, n2, n3 = etiquetas[-1], etiquetas[-2], etiquetas[-3]
    ax.set_title(f"{n1}, {n2} y {n3} concentran el {top3:.0%} del fuego del Perú",
                 loc="left", fontsize=12, fontweight="bold")
    fig.savefig(config.FIGURAS / "ranking_departamentos.png", bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
def main():
    con = duckdb.connect()
    factores = pd.read_csv(FACTORES)
    anios = range(2001, config.ULTIMO_ANIO_COMPLETO + 1)

    print("1/7 Límites de departamentos y provincias ...")
    prov, deps = preparar_limites()

    print("2/7 Asignando celdas a provincias ...")
    celdas_region, n_borde = asignar_celdas(con, prov)
    con.register("celdas_region", celdas_region)

    print("3/7 Series mensuales armonizadas por región (con ajuste regional) ...")
    regiones = {"departamento": list(deps.id), "provincia": list(prov.id)}
    nombres = {"peru": "Perú", **dict(zip(deps.id, deps.nombre)),
               **{r.id: f"{r.nombre} ({r.departamento})" for r in prov.itertuples()}}

    # 3a. Ajuste por departamento (calculado con el factor nacional)
    conteo_dep = conteos(con, "departamento_id")
    k_dep, validacion_dep, err_nac, err_aj = ajuste_regional(
        armonizar(conteo_dep, factores, ["region_id", "anio", "mes"]), factores)
    # cada provincia usa el ajuste de su departamento
    k_prov = {r.id: k_dep.get(slug(r.departamento), 1.0) for r in prov.itertuples()}

    # 3b. Series con ajuste. País = suma de departamentos (así los 3 niveles cuadran entre sí)
    series = []
    for nivel, conteo, ajuste in [("departamento", conteo_dep, k_dep),
                                  ("provincia", conteos(con, "provincia_id"), k_prov)]:
        df = armonizar(conteo, factores, ["region_id", "anio", "mes"], ajuste)
        cols = ["region_id", "anio", "mes", "MODIS_dias_celda"] +                [c for c in df.columns if c.startswith(("dias_celda", "focos"))]
        df = df[cols].rename(columns={"MODIS_dias_celda": "modis_crudo_dias_celda"})
        df = completar(df, regiones[nivel], ["anio", "mes"], [anios, range(1, 13)])
        df.insert(0, "nivel", nivel)
        series.append(df)
    pais = series[0].drop(columns=["nivel", "region_id"]).groupby(["anio", "mes"], as_index=False).sum()
    pais.insert(0, "region_id", "peru")
    pais.insert(0, "nivel", "pais")
    serie = pd.concat([pais, *series], ignore_index=True)
    inicio = pd.to_datetime(dict(year=serie.anio, month=serie.mes, day=1)).dt.date
    serie["fuente"] = np.select([inicio >= config.VIIRS_INICIO, inicio >= config.AQUA_INICIO],
                                ["VIIRS S-NPP (observado)", "MODIS Terra+Aqua (calibrado)"],
                                "MODIS solo Terra (calibrado)")
    serie["calidad"] = np.select([inicio >= config.VIIRS_INICIO, serie.anio >= config.SERIE_INICIO_CONFIABLE],
                                 ["alta", "media"], "baja")
    serie["region"] = serie.region_id.map(nombres)

    print("4/7 Climatología y anomalías mensuales ...")
    clima = climatologia(serie, ["nivel", "region_id", "mes"])
    clima.to_parquet(CLIMA_MENSUAL, index=False)
    serie = anomalias(serie, clima, ["nivel", "region_id", "mes"])
    serie.to_parquet(SERIE_REGION, index=False)

    print("5/7 Climatología semanal por provincia (factor C) ...")
    sem = armonizar(conteos(con, "provincia_id", con_semana=True), factores,
                    ["region_id", "anio", "mes", "semana"], k_prov)
    sem = sem.groupby(["region_id", "anio", "semana"], as_index=False)[["dias_celda", "focos"]].sum()
    sem = completar(sem, regiones["provincia"], ["anio", "semana"], [anios, range(1, 53)])
    clima_sem = climatologia(sem, ["region_id", "semana"])
    clima_sem["region"] = clima_sem.region_id.map(nombres)
    clima_sem.to_parquet(CLIMA_SEMANAL, index=False)

    print("6/7 Frecuencia histórica por celda (factor D) ...")
    frecuencia_celdas(con)

    print("7/7 Figura de ranking ...")
    figura_ranking(serie[serie.nivel == "departamento"], nombres)

    # ---- Resumen ----
    print(f"\nRegiones: {len(deps)} departamentos, {len(prov)} provincias. "
          f"Celdas: {len(celdas_region):,} ({n_borde} de borde asignadas a la provincia más cercana).")

    print("\n=== Error al predecir VIIRS por departamento (dejar un año fuera, 2012–2021) ===")
    print(f"Error medio ponderado:  solo factor nacional = {err_nac:.1f}%  |  con ajuste regional = {err_aj:.1f}%")
    v = validacion_dep.head(12).copy()
    v["region_id"] = v.region_id.map(nombres)
    print(v.to_string(index=False))

    ultimo = config.ULTIMO_ANIO_COMPLETO
    print(f"\n=== Meses 'extremo' (sobre P95) en {ultimo}, por departamento ===")
    ext = serie[(serie.nivel == "departamento") & (serie.anio == ultimo) & (serie.categoria == "extremo")]
    print(ext[["region", "mes", "dias_celda", "mediana", "anomalia_pct"]].to_string(index=False)
          if len(ext) else "Ninguno.")


if __name__ == "__main__":
    main()
