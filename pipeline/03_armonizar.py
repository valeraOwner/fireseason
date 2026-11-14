"""
PASO 3 — Armonizar MODIS y VIIRS en una sola serie comparable (2001 -> hoy).

Entrada : data/processed/focos_limpios.parquet           (paso 2)
Salidas : data/processed/celdas_dia.parquet              focos agregados por celda 0.1° y día
          data/processed/factores_calibracion.csv        factor MODIS->VIIRS por mes (+ intervalo)
          data/processed/validacion_calibracion.csv      prueba del método, año por año
          data/processed/serie_mensual_armonizada.parquet  LA serie final (Perú)
          docs/figuras/*.png                             calendario de fuego y serie anual

Idea en 4 pasos:
  1. Rejilla común: cada foco cae en una celda de 0.1° (~11 km). Contamos "días-celda con fuego"
     (una celda que ardió un día cuenta 1, aunque tenga 30 focos). Eso reduce la ventaja de
     resolución de VIIRS (375 m) sobre MODIS (1 km).
  2. Referencia VIIRS = S-NPP (continuo desde 2012). Los días que S-NPP no tiene datos se
     rellenan con NOAA-20 (mismo sensor). Así evitamos el "salto" de 2018 cuando se sumó NOAA-20.
  3. En 2012-2021 existen ambos sensores: factor[mes] = VIIRS / MODIS. Un factor por mes porque
     la diferencia cambia con la temporada.
  4. Serie final: VIIRS observado desde feb-2012; antes, MODIS x factor (con intervalo de confianza).
     Antes de ago-2002 solo existía Terra: se usa un factor propio Terra->VIIRS (calidad baja).

Uso:  python pipeline/03_armonizar.py
"""
from datetime import date

import duckdb
import numpy as np
import pandas as pd

import config

FOCOS = config.PROCESSED / "focos_limpios.parquet"
CELDAS_DIA = config.PROCESSED / "celdas_dia.parquet"
FACTORES = config.PROCESSED / "factores_calibracion.csv"
VALIDACION = config.PROCESSED / "validacion_calibracion.csv"
SERIE = config.PROCESSED / "serie_mensual_armonizada.parquet"

METRICAS = ["dias_celda", "focos"]
N_BOOTSTRAP = 2000
rng = np.random.default_rng(42)          # semilla fija: mismos resultados cada vez


# ---------------------------------------------------------------------------
# 1. Rejilla común y conteos mensuales por grupo de sensores
# ---------------------------------------------------------------------------
def crear_celdas_dia(con):
    c = config.TAMANO_CELDA_GRADOS
    con.execute(f"""
        COPY (
            SELECT fecha,
                   CAST(floor(lon / {c}) AS INTEGER) AS cx,     -- índice de columna de la celda
                   CAST(floor(lat / {c}) AS INTEGER) AS cy,     -- índice de fila de la celda
                   sensor, satelite,
                   count(*)              AS n_focos,
                   round(sum(frp), 1)    AS frp
            FROM read_parquet('{FOCOS.as_posix()}')
            GROUP BY ALL
        ) TO '{CELDAS_DIA.as_posix()}' (FORMAT parquet, COMPRESSION zstd)
    """)


def conteos_mensuales(con) -> pd.DataFrame:
    """Tabla ancha: una fila por (anio, mes); columnas <GRUPO>_<metrica>."""
    df = con.execute(f"""
        WITH c AS (SELECT * FROM read_parquet('{CELDAS_DIA.as_posix()}')),
        dias_snpp AS (SELECT DISTINCT fecha FROM c WHERE satelite = 'S-NPP'),
        grupos AS (
            SELECT 'MODIS' AS grupo, fecha, cx, cy, n_focos FROM c WHERE satelite IN ('Terra', 'Aqua')
            UNION ALL
            SELECT 'TERRA', fecha, cx, cy, n_focos FROM c WHERE satelite = 'Terra'
            UNION ALL
            SELECT 'VIIRS', fecha, cx, cy, n_focos FROM c WHERE satelite = 'S-NPP'
            UNION ALL   -- relleno: días sin S-NPP se cubren con NOAA-20
            SELECT 'VIIRS', fecha, cx, cy, n_focos FROM c
            WHERE satelite = 'NOAA-20' AND fecha NOT IN (SELECT fecha FROM dias_snpp)
        ),
        por_celda AS (    -- una fila por grupo-celda-día (Terra y Aqua el mismo día = 1 día-celda)
            SELECT grupo, fecha, cx, cy, sum(n_focos) AS n FROM grupos GROUP BY ALL
        )
        SELECT grupo, year(fecha) AS anio, month(fecha) AS mes,
               count(*) AS dias_celda, sum(n) AS focos
        FROM por_celda GROUP BY ALL
    """).df()

    ancho = df.pivot_table(index=["anio", "mes"], columns="grupo", values=METRICAS, fill_value=0)
    ancho.columns = [f"{g}_{m}" for m, g in ancho.columns]

    # Rejilla completa de meses (un mes sin fuego = 0, no "falta")
    anios = range(int(df.anio.min()), int(df.anio.max()) + 1)
    todos = pd.MultiIndex.from_product([anios, range(1, 13)], names=["anio", "mes"])
    ancho = ancho.reindex(todos, fill_value=0).reset_index()
    ancho["inicio_mes"] = pd.to_datetime(dict(year=ancho.anio, month=ancho.mes, day=1)).dt.date

    # VIIRS no existe antes de feb-2012: eso es "sin dato", no cero
    for m in METRICAS:
        ancho.loc[ancho.inicio_mes < config.VIIRS_INICIO, f"VIIRS_{m}"] = np.nan
    return ancho


# ---------------------------------------------------------------------------
# 2. Factores de calibración por mes
# ---------------------------------------------------------------------------
def periodo_calibracion(ancho):
    return ancho[(ancho.anio.between(config.CALIB_ANIO_INICIO, config.CALIB_ANIO_FIN))
                 & (ancho.inicio_mes >= config.VIIRS_INICIO)]


def factor_con_intervalo(viirs: np.ndarray, base: np.ndarray):
    """Razón de sumas + intervalo 90% por bootstrap (remuestreando años)."""
    factor = viirs.sum() / base.sum()
    idx = rng.integers(0, len(viirs), size=(N_BOOTSTRAP, len(viirs)))
    sims = viirs[idx].sum(axis=1) / np.maximum(base[idx].sum(axis=1), 1e-9)
    return factor, np.percentile(sims, 5), np.percentile(sims, 95)


def calcular_factores(ancho) -> pd.DataFrame:
    cal = periodo_calibracion(ancho)
    filas = []
    for base in ["MODIS", "TERRA"]:
        for metrica in METRICAS:
            for mes in range(1, 13):
                sub = cal[cal.mes == mes]
                f, lo, hi = factor_con_intervalo(sub[f"VIIRS_{metrica}"].to_numpy(float),
                                                 sub[f"{base}_{metrica}"].to_numpy(float))
                filas.append(dict(base=base, metrica=metrica, mes=mes, factor=round(f, 3),
                                  ic90_bajo=round(lo, 3), ic90_alto=round(hi, 3), n_anios=len(sub)))
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# 3. Validación: dejar un año fuera (leave-one-year-out)
#    Para cada año, calibramos SIN ese año y predecimos VIIRS a partir de MODIS.
#    Comparamos con lo que VIIRS realmente midió. También lo comparamos con
#    usar un único factor para todo el año, para justificar el factor mensual.
# ---------------------------------------------------------------------------
def validar(ancho) -> pd.DataFrame:
    cal = periodo_calibracion(ancho)
    filas = []
    for metrica in METRICAS:
        v, b = f"VIIRS_{metrica}", f"MODIS_{metrica}"
        for anio in sorted(cal.anio.unique()):
            entreno, prueba = cal[cal.anio != anio], cal[cal.anio == anio]
            f_mes = entreno.groupby("mes")[v].sum() / entreno.groupby("mes")[b].sum()
            f_unico = entreno[v].sum() / entreno[b].sum()
            pred_mensual = prueba[b] * prueba.mes.map(f_mes)
            obs = prueba[v].sum()
            filas.append(dict(
                metrica=metrica, anio=anio, viirs_observado=int(obs),
                pred_factor_mensual=round(pred_mensual.sum()),
                pred_factor_unico=round(prueba[b].sum() * f_unico),
                error_pct_mensual=round(100 * (pred_mensual.sum() - obs) / obs, 1),
                error_pct_unico=round(100 * (prueba[b].sum() * f_unico - obs) / obs, 1),
                r2_meses=round(r2(prueba[v], pred_mensual), 3),
            ))
    return pd.DataFrame(filas)


def r2(obs, pred):
    obs, pred = np.asarray(obs, float), np.asarray(pred, float)
    return 1 - ((obs - pred) ** 2).sum() / ((obs - obs.mean()) ** 2).sum()


# ---------------------------------------------------------------------------
# 4. Serie armonizada
# ---------------------------------------------------------------------------
def armonizar(ancho, factores) -> pd.DataFrame:
    filas = []
    for metrica in METRICAS:
        f = factores[factores.metrica == metrica].set_index(["base", "mes"])
        for r in ancho.itertuples():
            if r.inicio_mes >= config.VIIRS_INICIO:
                valor = getattr(r, f"VIIRS_{metrica}")
                bajo = alto = valor
                fuente, calidad = "VIIRS S-NPP (observado)", "alta"
            else:
                base = "MODIS" if r.inicio_mes >= config.AQUA_INICIO else "TERRA"
                fac = f.loc[(base, r.mes)]
                crudo = getattr(r, f"{base}_{metrica}")
                valor, bajo, alto = crudo * fac.factor, crudo * fac.ic90_bajo, crudo * fac.ic90_alto
                if base == "MODIS":
                    fuente, calidad = "MODIS Terra+Aqua (calibrado)", "media"
                else:
                    fuente, calidad = "MODIS solo Terra (calibrado)", "baja"
            filas.append(dict(anio=r.anio, mes=r.mes, metrica=metrica,
                              valor=round(valor), ic90_bajo=round(bajo), ic90_alto=round(alto),
                              modis_crudo=int(getattr(r, f"MODIS_{metrica}")),
                              fuente=fuente, calidad=calidad))
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# 5. Figuras
# ---------------------------------------------------------------------------
def figuras(serie):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, PowerNorm

    config.FIGURAS.mkdir(parents=True, exist_ok=True)
    INK, MUTED, GRID = "#1f1f1e", "#6b6b66", "#e4e3df"
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
                         "xtick.color": MUTED, "ytick.color": MUTED, "text.color": INK})

    s = serie[serie.metrica == "dias_celda"]
    meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]

    # --- Calendario de fuego: años x meses, rampa naranja de un solo tono ---
    tabla = s.pivot(index="anio", columns="mes", values="valor")
    confiable = s[s.anio >= config.SERIE_INICIO_CONFIABLE]
    pct_ago_oct = confiable[confiable.mes.isin([8, 9, 10])].valor.sum() / confiable.valor.sum()

    rampa = LinearSegmentedColormap.from_list("fuego", ["#fdf3ec", "#f4a77f", "#eb6834", "#b8461d", "#6e2410"])
    fig, ax = plt.subplots(figsize=(8, 9), dpi=150)
    im = ax.imshow(tabla.values, cmap=rampa, norm=PowerNorm(0.5, vmin=0, vmax=np.nanmax(tabla.values)),
                   aspect="auto")
    ax.set_xticks(range(12), meses)
    ax.set_yticks(range(len(tabla)), tabla.index)
    ax.tick_params(length=0)
    for lado in ax.spines.values():
        lado.set_visible(False)
    # separadores finos entre celdas (2 px de "superficie")
    ax.set_xticks(np.arange(-0.5, 12), minor=True)
    ax.set_yticks(np.arange(-0.5, len(tabla)), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.5)
    ax.tick_params(which="minor", length=0)
    # marcar los años con datos parciales y el cambio de fuente
    for i, anio in enumerate(tabla.index):
        if anio < config.AQUA_INICIO.year:
            ax.text(12.3, i, "solo Terra: calidad baja", va="center", fontsize=8, color=MUTED)
        elif anio < config.SERIE_INICIO_CONFIABLE:
            ax.text(12.3, i, "Terra; Aqua desde agosto", va="center", fontsize=8, color=MUTED)
        if anio == 2012:
            ax.text(12.3, i, "desde aquí: VIIRS observado", va="center", fontsize=8, color=MUTED)
        if anio == 2003:
            ax.text(12.3, i, "MODIS calibrado a escala VIIRS", va="center", fontsize=8, color=MUTED)
    cb = fig.colorbar(im, ax=ax, orientation="horizontal", fraction=0.03, pad=0.05, aspect=40)
    cb.set_ticks([0, 500, 2000, 5000, 10000, 15000])
    cb.set_ticklabels(["0", "500", "2 000", "5 000", "10 000", "15 000"])
    cb.set_label("días-celda con fuego (escala VIIRS)")
    cb.outline.set_visible(False)
    ax.set_title(f"Perú: agosto–octubre concentra el {pct_ago_oct:.0%} de la actividad de fuego",
                 loc="left", fontsize=12, fontweight="bold", pad=24)
    ax.text(0, 1.015, "Calendario de fuego armonizado MODIS + VIIRS, 2001–2025 · NASA FIRMS",
            transform=ax.transAxes, fontsize=9, color=MUTED)
    fig.savefig(config.FIGURAS / "calendario_fuego_peru.png", bbox_inches="tight")
    plt.close(fig)

    # --- Serie anual: MODIS sin armonizar vs serie armonizada ---
    anual = s.groupby("anio")[["valor", "ic90_bajo", "ic90_alto", "modis_crudo"]].sum()
    AZUL, NARANJA = "#2a78d6", "#eb6834"      # paleta categórica: slots 1 y 2
    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=150)
    ax.fill_between(anual.index, anual.ic90_bajo, anual.ic90_alto, color=AZUL, alpha=0.15, linewidth=0)
    ax.plot(anual.index, anual.valor, color=AZUL, linewidth=2, marker="o", markersize=4,
            label="Serie armonizada (escala VIIRS)")
    ax.plot(anual.index, anual.modis_crudo, color=NARANJA, linewidth=2, marker="o", markersize=4,
            label="MODIS sin armonizar")
    ax.axvline(2011.5, color=MUTED, linewidth=1, linestyle=":")
    ax.text(2011.6, ax.get_ylim()[1] * 0.95, "VIIRS desde 2012", fontsize=8, color=MUTED, va="top")
    ax.text(anual.index[-1] + 0.3, anual.valor.iloc[-1], "Armonizada", color=INK, fontsize=9, va="center")
    ax.text(anual.index[-1] + 0.3, anual.modis_crudo.iloc[-1], "MODIS crudo", color=INK, fontsize=9, va="center")
    ax.set_xlim(anual.index[0] - 0.5, anual.index[-1] + 2.5)
    ax.set_ylim(bottom=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for lado in ["top", "right", "left"]:
        ax.spines[lado].set_visible(False)
    ax.set_ylabel("días-celda con fuego por año")
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    ax.set_title("Sin armonizar, MODIS subestima la actividad de fuego frente a VIIRS",
                 loc="left", fontsize=12, fontweight="bold")
    ax.text(0, -0.15, "Banda: intervalo de confianza 90% del factor de calibración (años previos a 2012).",
            transform=ax.transAxes, fontsize=8, color=MUTED)
    fig.savefig(config.FIGURAS / "serie_anual_armonizada.png", bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
def main():
    con = duckdb.connect()

    print("1/5 Rejilla común (celdas de 0.1°) ...")
    crear_celdas_dia(con)
    ancho = conteos_mensuales(con)

    print("2/5 Factores de calibración por mes ...")
    factores = calcular_factores(ancho)
    factores.to_csv(FACTORES, index=False)

    print("3/5 Validación (dejar un año fuera) ...")
    val = validar(ancho)
    val.to_csv(VALIDACION, index=False)

    print("4/5 Serie armonizada ...")
    serie = armonizar(ancho, factores)
    serie.to_parquet(SERIE, index=False)

    print("5/5 Figuras ...")
    figuras(serie)

    # ---- Resumen ----
    print("\n=== FACTORES MODIS -> VIIRS (días-celda) ===")
    print(factores[(factores.base == "MODIS") & (factores.metrica == "dias_celda")]
          [["mes", "factor", "ic90_bajo", "ic90_alto"]].to_string(index=False))

    print("\n=== FACTORES MODIS -> VIIRS (focos) ===")
    print(factores[(factores.base == "MODIS") & (factores.metrica == "focos")]
          [["mes", "factor", "ic90_bajo", "ic90_alto"]].to_string(index=False))

    print("\n=== VALIDACIÓN (error al predecir el total anual de VIIRS) ===")
    for metrica in METRICAS:
        v = val[val.metrica == metrica]
        print(f"{metrica:>10}: error medio absoluto  factor mensual = {v.error_pct_mensual.abs().mean():.1f}%"
              f"  | factor único = {v.error_pct_unico.abs().mean():.1f}%"
              f"  | R² mensual medio = {v.r2_meses.mean():.2f}")

    print(f"\nArchivos en {config.PROCESSED} y figuras en {config.FIGURAS}")


if __name__ == "__main__":
    main()
