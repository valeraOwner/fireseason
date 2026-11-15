"""
PASO 6 — Modelo de predicción: riesgo de fuego esperado en las próximas 1–12 semanas.

Idea (docs/ARQUITECTURA.md, sección 3.4):
  1. CLIMATOLOGÍA: para cada celda de 0.1° (~11 km) y cada semana del año,
     p = fracción de años en que hubo fuego (VIIRS, 2013 → último año completo).
     Se suaviza con la semana anterior y la siguiente (con 13 años, una sola semana es muy ruidosa).
  2. AJUSTE POR CONDICIONES ACTUALES: si la provincia viene con más (o menos) fuego de lo normal
     en la última semana, la probabilidad de las próximas semanas sube (o baja):
         r  = (observado + 5) / (esperado + 5)          razón suavizada de la provincia
         m  = r ^ (beta * decaimiento^(h-1))            se desvanece con el horizonte h
         p' = 1 - (1 - p)^m
     beta y decaimiento se eligen con datos de 2013–2019 y se evalúan en 2020–2025 (años que el
     ajuste no vio). Si el ajuste no mejora a la climatología, queda beta = 0 (solo climatología).
  3. VALIDACIÓN: puntaje de Brier (error cuadrático de una probabilidad) y "skill" frente a la
     climatología y frente a una probabilidad constante. Se excluye el año evaluado de la climatología.

"Fuego en la semana" = al menos un foco VIIRS (S-NPP; NOAA-20 los días sin S-NPP, igual que el paso 4).

Salidas:
  data/processed/prediccion_clima.parquet   cx, cy, semana, p        (solo p >= 0.005)
  data/processed/prediccion_modelo.json     parámetros elegidos + métricas de validación
  docs/figuras/validacion_prediccion.png

Uso (desde la carpeta fireseason/):
    python pipeline/06_prediccion.py
"""
import json

import duckdb
import matplotlib
import numpy as np
import pandas as pd

import config

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

CELDAS_DIA = config.PROCESSED / "celdas_dia.parquet"
CELDAS_REGION = config.PROCESSED / "celdas_region.parquet"
SALIDA_CLIMA = config.PROCESSED / "prediccion_clima.parquet"
SALIDA_MODELO = config.PROCESSED / "prediccion_modelo.json"

ANIO_0, ANIO_1 = 2013, config.ULTIMO_ANIO_COMPLETO      # primer año completo con VIIRS
SEMANAS = 52
HORIZONTE = 12                                          # semanas hacia adelante
SUAVIZADO = 5.0                                         # +5 arriba y abajo en la razón r
ANIOS_AJUSTE = range(2013, 2020)                        # para elegir beta y decaimiento
ANIOS_PRUEBA = range(2020, ANIO_1 + 1)                  # para reportar (no se usan al elegir)
BETAS = [0.0, 0.25, 0.5, 0.75, 1.0]
DECAIMIENTOS = [0.6, 0.75, 0.9, 1.0]


# ---------------------------------------------------------------------------
# 1. Matriz celda × año × semana: ¿hubo fuego? (0/1)
# ---------------------------------------------------------------------------
def cargar_indicador():
    con = duckdb.connect()
    df = con.execute(f"""
        WITH c AS (SELECT * FROM read_parquet('{CELDAS_DIA.as_posix()}')),
        dias_snpp AS (SELECT DISTINCT fecha FROM c WHERE satelite = 'S-NPP'),
        v AS (
            SELECT fecha, cx, cy FROM c WHERE satelite = 'S-NPP'
            UNION ALL
            SELECT fecha, cx, cy FROM c WHERE satelite = 'NOAA-20' AND fecha NOT IN (SELECT fecha FROM dias_snpp)
        )
        SELECT DISTINCT cx, cy, year(fecha) AS anio, least((dayofyear(fecha) - 1) // 7 + 1, {SEMANAS}) AS semana
        FROM v WHERE year(fecha) BETWEEN {ANIO_0} AND {ANIO_1}
    """).df()
    region = con.execute(f"SELECT cx, cy, provincia_id FROM read_parquet('{CELDAS_REGION.as_posix()}')").df()

    celdas = region[["cx", "cy"]].drop_duplicates().reset_index(drop=True)
    celdas["i"] = np.arange(len(celdas))
    df = df.merge(celdas, on=["cx", "cy"])
    anios = ANIO_1 - ANIO_0 + 1
    fuego = np.zeros((len(celdas), anios, SEMANAS), dtype=np.float32)
    fuego[df.i.to_numpy(), (df.anio - ANIO_0).to_numpy(), (df.semana - 1).to_numpy()] = 1
    prov = celdas.merge(region, on=["cx", "cy"], how="left").provincia_id.fillna("sin-provincia")
    prov_idx, prov_ids = pd.factorize(prov)
    return celdas, fuego, prov_idx, list(prov_ids)


def suavizar(fuego):
    """Promedio de la semana con su anterior y su siguiente (dando la vuelta al año: la 52 toca a la 1)."""
    return (np.roll(fuego, 1, axis=-1) + fuego + np.roll(fuego, -1, axis=-1)) / 3


# ---------------------------------------------------------------------------
# 2. Ajuste por condiciones actuales
# ---------------------------------------------------------------------------
def razon_provincias(fuego_anio, p_clima, prov_idx, n_prov):
    """r por provincia y semana: celdas con fuego observadas vs esperadas por la climatología."""
    obs = np.zeros((n_prov, SEMANAS))
    esp = np.zeros((n_prov, SEMANAS))
    np.add.at(obs, prov_idx, fuego_anio)
    np.add.at(esp, prov_idx, p_clima)
    return (obs + SUAVIZADO) / (esp + SUAVIZADO)


def ajustar(p, r, beta, decaimiento, h):
    m = r ** (beta * decaimiento ** (h - 1))
    return 1 - (1 - p) ** m


# ---------------------------------------------------------------------------
# 3. Validación "dejando un año fuera"
# ---------------------------------------------------------------------------
def evaluar(fuego, prov_idx, n_prov, anios_eval):
    """Brier por horizonte para: constante, climatología y cada (beta, decaimiento)."""
    n_anios = fuego.shape[1]
    suave = suavizar(fuego)
    total = suave.sum(axis=1)                                   # celda × semana
    combos = [(b, d) for b in BETAS for d in DECAIMIENTOS if b > 0] + [(0.0, 1.0)]
    err = {k: np.zeros(HORIZONTE) for k in ["constante", *combos]}
    n = np.zeros(HORIZONTE)
    for anio in anios_eval:
        a = anio - ANIO_0
        p_clima = np.clip((total - suave[:, a]) / (n_anios - 1), 0, 1)   # sin el año evaluado (clip: redondeo float32)
        base = fuego[:, np.arange(n_anios) != a].mean()          # probabilidad constante
        r = razon_provincias(fuego[:, a], p_clima, prov_idx, n_prov)
        for h in range(1, HORIZONTE + 1):
            origen = np.arange(0, SEMANAS - h)                    # semana "hoy"; se predice origen + h
            obs = fuego[:, a, origen + h]
            pc = p_clima[:, origen + h]
            err["constante"][h - 1] += ((base - obs) ** 2).sum()
            r_celda = r[prov_idx][:, origen]
            for b, d in combos:
                pp = pc if b == 0 else ajustar(pc, r_celda, b, d, h)
                err[(b, d)][h - 1] += ((pp - obs) ** 2).sum()
            n[h - 1] += obs.size
    return {k: v / n for k, v in err.items()}


def auc(p, obs):
    """Área bajo la curva ROC: probabilidad de que una celda que ardió tenga más p que una que no."""
    rango = pd.Series(p).rank().to_numpy()
    pos = obs.astype(bool)
    n1, n0 = pos.sum(), (~pos).sum()
    return float((rango[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def main():
    print("1/4 Matriz celda × año × semana (VIIRS) ...")
    celdas, fuego, prov_idx, prov_ids = cargar_indicador()
    n_prov = len(prov_ids)
    print(f"   {len(celdas)} celdas, {fuego.shape[1]} años ({ANIO_0}-{ANIO_1}), {n_prov} provincias; "
          f"{100 * fuego.mean():.2f} % de celda-semanas con fuego")

    print("2/4 Eligiendo beta y decaimiento con", f"{ANIOS_AJUSTE.start}-{ANIOS_AJUSTE.stop - 1} ...")
    ajuste = evaluar(fuego, prov_idx, n_prov, ANIOS_AJUSTE)
    clima_aj = ajuste[(0.0, 1.0)].mean()
    mejor = min((k for k in ajuste if k != "constante"), key=lambda k: ajuste[k].mean())
    beta, decaimiento = mejor
    print(f"   mejor: beta={beta}, decaimiento={decaimiento} "
          f"(Brier {ajuste[mejor].mean():.5f} vs climatología {clima_aj:.5f})")

    print("3/4 Validando en", f"{ANIOS_PRUEBA.start}-{ANIOS_PRUEBA.stop - 1} (años no usados al elegir) ...")
    prueba = evaluar(fuego, prov_idx, n_prov, ANIOS_PRUEBA)
    bs_const, bs_clima, bs_modelo = prueba["constante"], prueba[(0.0, 1.0)], prueba[mejor]
    skill_clima = 1 - bs_clima / bs_const
    skill_ajuste = 1 - bs_modelo / bs_clima
    for h in (1, 2, 4, 8, 12):
        print(f"   h={h:>2}: skill climatología vs constante {100 * skill_clima[h - 1]:5.1f} % · "
              f"ajuste vs climatología {100 * skill_ajuste[h - 1]:+5.1f} %")

    # AUC de la climatología en los años de prueba (¿separa celdas que arden de las que no?)
    suave = suavizar(fuego)
    total = suave.sum(axis=1)
    aucs = []
    for anio in ANIOS_PRUEBA:
        a = anio - ANIO_0
        p_clima = np.clip((total - suave[:, a]) / (fuego.shape[1] - 1), 0, 1)
        aucs.append(auc(p_clima.ravel(), fuego[:, a].ravel()))
    print(f"   AUC climatología: {np.mean(aucs):.3f} (0.5 = azar, 1 = perfecto)")

    print("4/4 Guardando climatología final (todos los años) ...")
    p_final = suave.mean(axis=1)                                 # celda × semana
    i, s = np.nonzero(p_final >= 0.005)
    tabla = pd.DataFrame({"cx": celdas.cx.to_numpy()[i], "cy": celdas.cy.to_numpy()[i],
                          "semana": s + 1, "p": p_final[i, s].round(4)})
    duckdb.from_df(tabla).write_parquet(SALIDA_CLIMA.as_posix())  # (pyarrow-parquet está bloqueado en este equipo)
    modelo = {
        "anios_climatologia": [ANIO_0, ANIO_1],
        "definicion": "probabilidad de al menos un foco VIIRS en la celda de 0.1° durante la semana",
        "beta": beta, "decaimiento": decaimiento, "suavizado": SUAVIZADO,
        "anios_ajuste": [ANIOS_AJUSTE.start, ANIOS_AJUSTE.stop - 1],
        "anios_prueba": [ANIOS_PRUEBA.start, ANIOS_PRUEBA.stop - 1],
        "auc_climatologia": round(float(np.mean(aucs)), 3),
        "por_horizonte": [
            {"semanas": h, "brier_constante": round(float(bs_const[h - 1]), 5),
             "brier_climatologia": round(float(bs_clima[h - 1]), 5),
             "brier_modelo": round(float(bs_modelo[h - 1]), 5),
             "skill_climatologia_pct": round(100 * float(skill_clima[h - 1]), 1),
             "mejora_ajuste_pct": round(100 * float(skill_ajuste[h - 1]), 1)}
            for h in range(1, HORIZONTE + 1)],
    }
    SALIDA_MODELO.write_text(json.dumps(modelo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   -> {SALIDA_CLIMA.name}: {len(tabla)} filas · {SALIDA_MODELO.name}")

    fig, ax = plt.subplots(figsize=(7, 3.6))
    h = np.arange(1, HORIZONTE + 1)
    ax.plot(h, 100 * skill_clima, marker="o", color="#3987e5", label="Climatología vs. prob. constante")
    ax.plot(h, 100 * (1 - bs_modelo / bs_const), marker="o", color="#d95926", label="Modelo final vs. prob. constante")
    ax.axhline(0, color="#888", lw=0.8)
    ax.set_xlabel("Semanas hacia adelante")
    ax.set_ylabel("Mejora en el puntaje de Brier (%)")
    ax.set_title(f"Validación en {ANIOS_PRUEBA.start}–{ANIOS_PRUEBA.stop - 1} (años no usados al ajustar)")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(config.FIGURAS / "validacion_prediccion.png", dpi=130)


if __name__ == "__main__":
    main()
