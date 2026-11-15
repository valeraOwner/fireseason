"""
Estados de riesgo de los incendios en vivo (Prevención / Alto / Crítico).

Implementa docs/POLITICA_ESTADOS.md:
  1. Agrupa los focos en EVENTOS (focos a <= 2 km entre sí).
  2. Calcula 6 factores (A..F) que suman un puntaje de 0 a 100.
  3. Aplica las reglas directas (fuerzan un estado aunque el puntaje sea bajo).
  4. Aplica las reglas de transición: subir al instante, bajar solo con margen y tiempo.

No guardamos nada en una base de datos: como tenemos 7 días de focos, el "pasado" de cada
evento se reconstruye mirando cómo estaba hace 6 h, 12 h, ... 48 h (fotos cada 6 h).

Todos los umbrales están en PARAMETROS para ajustarlos sin tocar el resto del código.
"""
import hashlib
from datetime import datetime, timedelta

import duckdb
import numpy as np
import pandas as pd

from app import settings

# ---------------------------------------------------------------------------
# Parámetros de la política (sección "Parámetros, visualización y validación")
# ---------------------------------------------------------------------------
PARAMETROS = {
    "umbral_alto": 40,
    "umbral_critico": 70,
    "margen_bajar": 10,          # para bajar hay que quedar 10 puntos bajo el umbral...
    "horas_para_bajar": 24,      # ...durante 24 h seguidas
    "radio_km": 2.0,             # radio de agrupación de focos
    "horas_observacion": 24,     # sin focos nuevos por 24 h -> "En observación"
    "horas_cierre": 72,          # sin focos nuevos por 72 h -> el evento se cierra (no se muestra)
    "paso_fotos_h": 6,           # cada cuántas horas se reconstruye el pasado del evento
    "horas_historia": 48,        # hasta cuántas horas atrás se reconstruye
}

ESTADOS = ["prevencion", "alto", "critico"]           # orden = gravedad
NOMBRE_ESTADO = {"prevencion": "Prevención", "alto": "Alto", "critico": "Crítico"}

C = settings.TAMANO_CELDA


# ---------------------------------------------------------------------------
# Tablas del pipeline (se cargan una sola vez)
# ---------------------------------------------------------------------------
_tablas: dict = {}


def _leer(ruta) -> pd.DataFrame:
    """Lee un Parquet con DuckDB (en este equipo Windows bloquea el lector Parquet de pyarrow)."""
    return duckdb.sql(f"SELECT * FROM read_parquet('{ruta.as_posix()}')").df()


def _cargar_tablas():
    if _tablas:
        return _tablas
    celdas = _leer(settings.CELDAS_REGION).set_index(["cx", "cy"])
    _tablas["celdas"] = celdas
    _tablas["clima_sem"] = _leer(settings.CLIMA_SEMANAL).set_index(["region_id", "semana"])
    _tablas["frecuencia"] = _leer(settings.FRECUENCIA).set_index(["cx", "cy", "mes"]).frecuencia
    # Contexto (poblados y áreas protegidas): opcional hasta que exista el paso 05_contexto.py.
    # Columnas esperadas: cx, cy, dist_poblado_km, pob_5km, zona ("estricta" | "anp" | "amortiguamiento" | "cerca" | null)
    ctx = settings.CONTEXTO_CELDAS
    _tablas["contexto"] = _leer(ctx).set_index(["cx", "cy"]) if ctx.exists() else None
    return _tablas


# ---------------------------------------------------------------------------
# 1. Agrupar focos en eventos (enlace simple a <= 2 km)
# ---------------------------------------------------------------------------
def agrupar(focos: pd.DataFrame, radio_km: float) -> np.ndarray:
    """Devuelve un número de grupo por foco. Dos focos a <= radio_km quedan en el mismo grupo,
    y si A toca a B y B toca a C, los tres son un solo evento."""
    n = len(focos)
    if n == 0:
        return np.array([], dtype=int)
    lat0 = np.radians(focos.lat.mean())
    x = focos.lon.to_numpy() * 111.32 * np.cos(lat0)       # km (aproximación plana, suficiente a 2 km)
    y = focos.lat.to_numpy() * 110.57
    padre = np.arange(n)

    def raiz(i):
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    # Cada foco cae en una "caja" de 2x2 km; solo se compara con las cajas vecinas (rápido).
    cajas: dict[tuple, list] = {}
    for i, (bx, by) in enumerate(zip((x // radio_km).astype(int), (y // radio_km).astype(int))):
        cajas.setdefault((bx, by), []).append(i)
    for (bx, by), miembros in cajas.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for j in cajas.get((bx + dx, by + dy), []):
                    for i in miembros:
                        if i < j and (x[i] - x[j]) ** 2 + (y[i] - y[j]) ** 2 <= radio_km ** 2:
                            padre[raiz(i)] = raiz(j)
    return np.array([raiz(i) for i in range(n)])


# ---------------------------------------------------------------------------
# 2. Factores
# ---------------------------------------------------------------------------
def conteo(focos: pd.DataFrame) -> tuple[int, float]:
    """Número de focos y FRP total "sin contar doble".
    Hoy hay 3 satélites VIIRS: el mismo fuego aparece 3 veces. Por eso se toma el satélite que
    más focos vio. Se usan focos VIIRS (375 m, mejor resolución); MODIS solo si no hay VIIRS."""
    return conteo_rapido(_arreglos(focos), np.ones(len(focos), dtype=bool))


def _arreglos(ev: pd.DataFrame) -> dict:
    """Columnas del evento como arreglos numpy: filtrar arreglos es ~100 veces más rápido que filtrar
    DataFrames, y cada evento se evalúa 9 veces (una por foto)."""
    return {"momento": ev.momento.dt.tz_convert(None).to_numpy(),   # UTC sin zona horaria
            "viirs": (ev.sensor == "VIIRS").to_numpy(),
            "sat": pd.factorize(ev.satelite)[0], "frp": ev.frp.to_numpy(dtype=float),
            "baja": ev.confianza_baja.to_numpy(dtype=bool),
            "inusual": (ev.frecuencia < 0.10).to_numpy(), "estricta": (ev.zona == "estricta").to_numpy()}


def conteo_rapido(x: dict, mascara: np.ndarray) -> tuple[int, float]:
    if not mascara.any():
        return 0, 0.0
    if (mascara & x["viirs"]).any():
        mascara = mascara & x["viirs"]
    n = np.bincount(x["sat"][mascara])
    frp = np.bincount(x["sat"][mascara], weights=x["frp"][mascara])
    return int(n.max()), float(frp.max())


def factor_a(n: int, frp: float) -> int:
    if n >= 30 or frp >= 500:
        return 25
    if n >= 10:
        return 18
    if n >= 3:
        return 10
    return 0


def factor_b(n: int, n_previo: int) -> tuple[int, float]:
    # Evento nuevo (nada en las 24 h previas): se compara contra 1 foco, para no premiar 1 foco aislado.
    razon = n / max(n_previo, 1)
    if razon > 2:
        return 15, razon
    if razon >= 1.5:
        return 8, razon
    return 0, razon


def factor_c(valor: float, clima: pd.Series | None) -> int | None:
    if clima is None:
        return None
    if valor > clima.p95:
        return 20
    if valor > clima.p90:
        return 15
    if valor > clima.p75:
        return 10
    return 0          # la política no da puntos entre la mediana y el P75


def factor_d(frecuencia: float | None) -> int | None:
    if frecuencia is None:
        return None
    if frecuencia < 0.10:
        return 10
    if frecuencia < 0.30:
        return 5
    return 0


def factor_e(dist_km: float | None, pob_5km: float | None) -> int | None:
    if dist_km is None:
        return None
    if dist_km < 2 or (pob_5km or 0) > 1000:
        return 15
    if dist_km < 5:
        return 10
    if dist_km <= 10:
        return 5
    return 0


def factor_f(zona: str | None, hay_contexto: bool) -> int | None:
    if not hay_contexto:
        return None
    return {"estricta": 15, "anp": 12, "amortiguamiento": 8, "cerca": 8}.get(zona, 0)


GRAVEDAD_ZONA = {"estricta": 4, "anp": 3, "amortiguamiento": 2, "cerca": 1}


# ---------------------------------------------------------------------------
# Factor C: focos de la provincia en 7 días vs la misma semana en la historia
# ---------------------------------------------------------------------------
def semana_del_anio(fecha) -> int:
    """Igual que el pipeline: semana 1 = días 1-7 del año; la 53 se suma a la 52."""
    return min((fecha.timetuple().tm_yday - 1) // 7 + 1, 52)


def anomalia_provincias(focos: pd.DataFrame, ahora: datetime) -> pd.DataFrame:
    """Días-celda VIIRS (confianza nominal/alta, como el histórico) de cada provincia en los últimos 7 días,
    comparados con los percentiles históricos de esa semana."""
    t = _cargar_tablas()
    v = focos[(focos.sensor == "VIIRS") & ~focos.confianza_baja
              & (focos.momento > ahora - timedelta(days=settings.DIAS_EN_VIVO))].copy()
    v["fecha"] = v.momento.dt.date
    v = v.join(t["celdas"].provincia_id, on=["cx", "cy"], how="inner")
    dias_celda = v.drop_duplicates(["cx", "cy", "fecha"]).groupby("provincia_id").size()
    semana = semana_del_anio(ahora)
    clima = t["clima_sem"].xs(semana, level="semana")
    out = clima[["region", "mediana", "p75", "p90", "p95"]].copy()
    out["dias_celda_7d"] = dias_celda.reindex(out.index).fillna(0)
    out["semana"] = semana
    out["puntos_c"] = [factor_c(r.dias_celda_7d, r) for r in out.itertuples()]
    return out


# ---------------------------------------------------------------------------
# 3. Evaluar un evento en un momento t (puntaje + reglas directas)
# ---------------------------------------------------------------------------
def _evaluar(x: dict, t: datetime, fijos: dict) -> dict | None:
    m = x["momento"]
    t64 = np.datetime64(t.replace(tzinfo=None))
    hasta_t = m <= t64
    if not hasta_t.any():
        return None              # el evento todavía no existía en t
    ultimas = hasta_t & (m > t64 - np.timedelta64(24, "h"))
    previas = (m > t64 - np.timedelta64(48, "h")) & (m <= t64 - np.timedelta64(24, "h"))
    n, frp = conteo_rapido(x, ultimas)
    n_prev, _ = conteo_rapido(x, previas)
    a = factor_a(n, frp)
    b, razon = factor_b(n, n_prev)
    c, d, e, f = fijos["c"], fijos["d"], fijos["e"], fijos["f"]
    puntaje = int(a + b + sum(x or 0 for x in (c, d, e, f)))

    por_confirmar = bool(hasta_t.sum() == 1 and x["baja"][hasta_t][0])
    confirmado = not por_confirmar
    zona = fijos["zona"]
    dist = fijos["dist_km"]
    n_inusual, _ = conteo_rapido(x, ultimas & x["inusual"])
    n_estricta, _ = conteo_rapido(x, ultimas & x["estricta"])

    critico, minimo_alto = [], []
    if n_estricta >= 3:
        critico.append("3 o más focos dentro de una zona de protección estricta o reserva PIACI")
    if dist is not None and dist < 2 and (n >= 10 or frp >= 300):
        critico.append("10 o más focos (o FRP ≥ 300 MW) a menos de 2 km de un centro poblado")
    if n >= 50:
        critico.append("50 o más focos en 24 h en un solo evento")
    if confirmado and zona in ("estricta", "anp", "amortiguamiento"):
        minimo_alto.append("Foco confirmado dentro de un ANP o su zona de amortiguamiento")
    if confirmado and dist is not None and dist < 2:
        minimo_alto.append("Evento confirmado a menos de 2 km de un centro poblado")
    if n_inusual >= 3:
        minimo_alto.append("3 o más focos en una zona inusual (arde en menos del 10 % de los años)")

    base = estado_por_puntaje(puntaje)
    if critico:
        base = "critico"
    elif minimo_alto and base == "prevencion":
        base = "alto"
    if por_confirmar:
        base = "prevencion"

    return {"t": t, "puntaje": puntaje, "base": base, "a": a, "b": b, "n": n, "n_prev": n_prev, "frp": frp,
            "razon": razon, "por_confirmar": por_confirmar, "reglas_critico": critico,
            "reglas_alto": minimo_alto, "hay_reglas": bool(critico or minimo_alto)}


def estado_por_puntaje(p: float) -> str:
    if p >= PARAMETROS["umbral_critico"]:
        return "critico"
    if p >= PARAMETROS["umbral_alto"]:
        return "alto"
    return "prevencion"


def _umbral_para_bajar(estado: str) -> float:
    """Puntaje bajo el cual se empieza a contar para bajar: 60 para dejar Crítico, 30 para dejar Alto."""
    umbral = PARAMETROS["umbral_critico"] if estado == "critico" else PARAMETROS["umbral_alto"]
    return umbral - PARAMETROS["margen_bajar"]


def aplicar_transiciones(fotos: list[dict]) -> tuple[str, list[dict]]:
    """Recorre las fotos de la más antigua a la más reciente.
    Sube al instante; baja un nivel solo tras 24 h seguidas bajo (umbral - 10) y sin reglas directas.
    Un evento "por confirmar" no tiene histéresis (siempre Prevención)."""
    estado, bajo_desde, historia = None, None, []
    for f in fotos:
        if estado is None or f["por_confirmar"]:
            estado, bajo_desde = f["base"], None
        elif ESTADOS.index(f["base"]) > ESTADOS.index(estado):
            estado, bajo_desde = f["base"], None                       # subir: al instante
        elif ESTADOS.index(f["base"]) < ESTADOS.index(estado):
            puede_bajar = f["puntaje"] < _umbral_para_bajar(estado) and not (
                f["reglas_critico"] or (estado == "alto" and f["reglas_alto"]))
            if not puede_bajar:
                bajo_desde = None
            else:
                bajo_desde = bajo_desde or f["t"]
                if f["t"] - bajo_desde >= timedelta(hours=PARAMETROS["horas_para_bajar"]):
                    estado = ESTADOS[ESTADOS.index(estado) - 1]         # un nivel a la vez
                    bajo_desde = None
        else:
            bajo_desde = None
        historia.append({"hora": f["t"].isoformat(), "puntaje": f["puntaje"], "estado": estado})
    return estado, historia


# ---------------------------------------------------------------------------
# 4. Todo junto
# ---------------------------------------------------------------------------
def _id_evento(ev: pd.DataFrame) -> str:
    primero = ev.iloc[0]
    clave = f"{primero.lat:.4f},{primero.lon:.4f},{primero.momento.isoformat()},{primero.satelite}"
    return "ev-" + hashlib.md5(clave.encode()).hexdigest()[:8]


def _fijos(ev: pd.DataFrame, prov: pd.DataFrame, t: dict) -> dict:
    """Factores que no cambian en 48 h: C (provincia), D (zona inusual), E (población), F (áreas protegidas)."""
    # Celda principal = la que tiene más focos
    cx, cy = ev.groupby(["cx", "cy"]).size().idxmax()
    ubic = t["celdas"].loc[(cx, cy)] if (cx, cy) in t["celdas"].index else None
    provincia_id = ubic.provincia_id if ubic is not None else None
    c = int(prov.puntos_c[provincia_id]) if provincia_id in prov.index else None

    # D: si la celda está en el Perú pero no aparece en la tabla, nunca ardió en ese mes -> 0 %
    frec = float(ev.loc[(ev.cx == cx) & (ev.cy == cy), "frecuencia"].iloc[0]) if ubic is not None else None
    d = factor_d(frec)

    hay_ctx = t["contexto"] is not None
    dist = pob = zona = None
    if hay_ctx:
        ctx = ev[["dist_poblado_km", "pob_5km", "zona"]]
        dist = None if ctx.dist_poblado_km.isna().all() else float(ctx.dist_poblado_km.min())
        pob = None if ctx.pob_5km.isna().all() else float(ctx.pob_5km.max())
        zonas = ctx.zona.dropna()
        zona = max(zonas, key=GRAVEDAD_ZONA.get) if len(zonas) else None
    return {"c": c, "d": d, "e": factor_e(dist, pob), "f": factor_f(zona, hay_ctx),
            "frecuencia": frec, "dist_km": dist, "pob_5km": pob, "zona": zona, "provincia_id": provincia_id,
            "provincia": ubic.provincia if ubic is not None else None,
            "departamento": ubic.departamento if ubic is not None else None}


def _preparar(focos: pd.DataFrame) -> pd.DataFrame:
    """Agrega a cada foco su celda de 0.1°, la frecuencia histórica y el contexto."""
    t = _cargar_tablas()
    f = focos.copy()
    f["cx"] = np.floor(f.lon / C).astype(int)
    f["cy"] = np.floor(f.lat / C).astype(int)
    f["mes"] = f.momento.dt.month
    f = f.join(t["frecuencia"], on=["cx", "cy", "mes"])
    en_peru = pd.MultiIndex.from_frame(f[["cx", "cy"]]).isin(t["celdas"].index)
    f["frecuencia"] = f.frecuencia.where(~(en_peru & f.frecuencia.isna()), 0.0)   # Perú sin registro = 0 %
    if t["contexto"] is not None:
        f = f.join(t["contexto"][["dist_poblado_km", "pob_5km", "zona"]], on=["cx", "cy"])
    else:
        f["dist_poblado_km"], f["pob_5km"], f["zona"] = np.nan, np.nan, None
    return f


def calcular_eventos(focos: pd.DataFrame, ahora: datetime) -> tuple[list[dict], pd.DataFrame, pd.DataFrame]:
    """Devuelve (eventos, focos de los eventos con su evento_id, anomalía por provincia)."""
    t = _cargar_tablas()
    focos = _preparar(focos)
    prov = anomalia_provincias(focos, ahora)

    recientes = focos[focos.momento > ahora - timedelta(hours=PARAMETROS["horas_cierre"])].reset_index(drop=True)
    recientes["grupo"] = agrupar(recientes, PARAMETROS["radio_km"])

    paso = PARAMETROS["paso_fotos_h"]
    momentos = [ahora - timedelta(hours=h) for h in range(PARAMETROS["horas_historia"], -1, -paso)]

    eventos, ids = [], {}
    for grupo, ev in recientes.groupby("grupo"):
        ev = ev.sort_values("momento")
        fijos = _fijos(ev, prov, t)
        arr = _arreglos(ev)
        fotos = [x for x in (_evaluar(arr, m, fijos) for m in momentos) if x]
        estado, historia = aplicar_transiciones(fotos)
        hoy = fotos[-1]
        ultima = ev.momento.max()
        id_ev = _id_evento(ev)
        ids[grupo] = id_ev

        reglas = hoy["reglas_critico"] + hoy["reglas_alto"]
        if hoy["por_confirmar"]:
            reglas = ["Un solo foco de confianza baja: queda en Prevención hasta confirmarse"]
        if estado != hoy["base"] and not hoy["por_confirmar"]:
            reglas.append(f"Mantiene {NOMBRE_ESTADO[estado]}: para bajar necesita 24 h seguidas bajo "
                          f"{_umbral_para_bajar(estado):.0f} puntos")

        pc = prov.loc[fijos["provincia_id"]] if fijos["provincia_id"] in prov.index else None
        eventos.append({
            "id": id_ev,
            "estado": estado,
            "estado_nombre": NOMBRE_ESTADO[estado],
            "puntaje": hoy["puntaje"],
            "en_observacion": bool(ultima <= ahora - timedelta(hours=PARAMETROS["horas_observacion"])),
            "por_confirmar": hoy["por_confirmar"],
            "lat": round(float(ev.lat.mean()), 4),
            "lon": round(float(ev.lon.mean()), 4),
            "limites": [round(float(ev.lon.min()), 4), round(float(ev.lat.min()), 4),
                        round(float(ev.lon.max()), 4), round(float(ev.lat.max()), 4)],
            "provincia": fijos["provincia"],
            "departamento": fijos["departamento"],
            "en_peru": fijos["provincia_id"] is not None,
            "focos_24h": hoy["n"],
            "focos_total": len(ev),
            "frp_24h": round(hoy["frp"], 1),
            "satelites": sorted(ev.satelite.unique().tolist()),
            "primera_deteccion": ev.momento.min().isoformat(),
            "ultima_deteccion": ultima.isoformat(),
            "factores": {
                "A": {"nombre": "Magnitud", "puntos": hoy["a"], "max": 25,
                      "detalle": f"{hoy['n']} focos y {hoy['frp']:.0f} MW de FRP en 24 h"},
                "B": {"nombre": "Crecimiento", "puntos": hoy["b"], "max": 15,
                      "detalle": f"{hoy['n']} focos vs {hoy['n_prev']} las 24 h previas"},
                "C": {"nombre": "Anomalía histórica", "puntos": fijos["c"], "max": 20,
                      "detalle": (f"Provincia: {pc.dias_celda_7d:.0f} días-celda en 7 días; "
                                  f"mediana {pc.mediana:.1f}, P90 {pc.p90:.1f} (semana {pc.semana})"
                                  if pc is not None else "Sin histórico (fuera del Perú)")},
                "D": {"nombre": "Zona inusual", "puntos": fijos["d"], "max": 10,
                      "detalle": (f"Ardió en el {100 * fijos['frecuencia']:.0f} % de los años en este mes"
                                  if fijos["frecuencia"] is not None else "Sin histórico (fuera del Perú)")},
                "E": {"nombre": "Cercanía a población", "puntos": fijos["e"], "max": 15,
                      "detalle": (f"Poblado a {fijos['dist_km']:.1f} km" if fijos["dist_km"] is not None
                                  else "Pendiente: faltan datos de centros poblados (INEI)")},
                "F": {"nombre": "Áreas protegidas", "puntos": fijos["f"], "max": 15,
                      "detalle": (fijos["zona"] or "Fuera de áreas protegidas") if fijos["f"] is not None
                                 else "Pendiente: faltan datos de SERNANP / Min. Cultura"},
            },
            "reglas": reglas,
            "historia": historia,
        })

    eventos.sort(key=lambda e: (-ESTADOS.index(e["estado"]), e["en_observacion"], -e["puntaje"]))
    recientes["evento_id"] = recientes.grupo.map(ids)
    return eventos, recientes, prov
