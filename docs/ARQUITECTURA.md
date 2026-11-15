# FireSeason — Arquitectura (v2)

Plataforma web para analizar, monitorear en vivo y anticipar la actividad de incendios en **Sudamérica**,
con **foco detallado en el Perú**, armonizando los focos de calor **MODIS** (2001→) y **VIIRS** (2012→) de NASA FIRMS.

Reto: NASA Space Apps — *Harmonization of MODIS and VIIRS Hot Spots*.

---

## 1. Visión general

```
                 FUENTES                                 BACKEND (FastAPI)                     FRONTEND (React)
 ┌───────────────────────────────┐        ┌──────────────────────────────────┐      ┌──────────────────────────────┐
 │ FIRMS archivo (CSV, estándar) │──┐     │  /historico  calendario, anomal. │      │ 🌎 Globo 3D (Three.js)        │
 │ MODIS 2001→ / VIIRS 2012→     │  │     │  /en-vivo    focos últimas 24 h  │ ───► │    llamas por estado          │
 └───────────────────────────────┘  ▼     │  /riesgo     estado por zona     │      │ 📅 Calendario de fuego        │
                              PIPELINE ──►│  /prediccion riesgo por semana   │      │ 🔴 En vivo (Perú y vecinos)   │
 ┌───────────────────────────────┐  ▲     │  /descargar  CSV                 │      │ ⚠️ Panel de alertas/detalle   │
 │ Contexto: centros poblados,   │──┘     └──────────────┬───────────────────┘      │ 🔮 Predicción + barra tiempo  │
 │ áreas protegidas (ANP/WDPA)   │                       │                          └──────────────────────────────┘
 └───────────────────────────────┘                       │ cada 15–30 min
                                          ┌──────────────▼───────────────┐
                                          │ FIRMS API (NRT, tiempo real) │
                                          └──────────────────────────────┘
```

- **CSV histórico** → armonización → calendario, climatología, anomalías, modelo de predicción.
- **API FIRMS (NRT)** → focos en vivo → se comparan con el histórico armonizado para asignar el **estado de riesgo**.
- La MAP_KEY de FIRMS vive **solo en el backend** (nunca en el navegador). El backend guarda en caché las respuestas.

---

## 2. Estructura de carpetas

```
fireseason/
├── data/
│   ├── raw/modis/            CSV FIRMS MODIS por país/año (Sudamérica)
│   ├── raw/viirs/            CSV FIRMS VIIRS (S-NPP, NOAA-20, NOAA-21)
│   ├── regiones/             límites: países, departamentos del Perú (GeoJSON)
│   ├── contexto/             centros poblados, áreas protegidas / zonas intangibles
│   └── processed/            Parquet armonizados + modelo entrenado
│
├── pipeline/                 Python, se ejecuta en orden
│   ├── config.py                 rutas, bbox Sudamérica/Perú, umbrales
│   ├── 01_descargar.py           archivo histórico FIRMS
│   ├── 02_limpiar.py             type=0, confianza válida, recorte geográfico
│   ├── 03_armonizar.py           rejilla común + calibración MODIS↔VIIRS
│   ├── 04_agregar.py             tablas día/semana/mes/año por celda y región
│   ├── 05_contexto.py            áreas protegidas (SERNANP) y centros poblados (GeoNames)
│   └── 06_modelo_riesgo.py       climatología + modelo de predicción por celda-semana
│
├── backend/app/
│   ├── main.py
│   ├── routers/                  historico.py, en_vivo.py, riesgo.py, prediccion.py, descarga.py
│   └── services/
│       ├── firms_client.py       llamadas a la API FIRMS + caché
│       ├── consultas.py          DuckDB sobre Parquet
│       ├── riesgo.py             cálculo de estado (prevención / alto / crítico)
│       └── prediccion.py         carga el modelo y responde por semana
│
├── frontend/src/
│   ├── pages/                    Inicio (globo), Historico, EnVivo, Prediccion, Metodologia
│   ├── components/
│   │   ├── globo/                Globo3D, Llama3D (Three.js / React Three Fiber)
│   │   ├── mapa/                 Mapa2D (Leaflet + dibujo de área)
│   │   ├── graficos/             CalendarioFuego, Climatologia, Anomalias (ECharts)
│   │   ├── PanelAlertas          lista de zonas por estado + ficha de detalle
│   │   └── BarraTiempo           slider de semanas para la predicción
│   └── services/api.js
│
└── docs/
```

---

## 3. Módulos

### 3.1 Histórico armonizado (el núcleo del reto)
Limpieza → rejilla común (0.1°) → conteo de **días-celda con fuego** → factor VIIRS/MODIS calculado en el
periodo común (2012→) por mes y región → serie única 2001→hoy.
Salidas: **calendario de fuego** mes × año, climatología (mediana, P75, P90 por mes), anomalías, ranking de zonas, CSV.

### 3.2 En vivo (Perú y alrededores)
- Backend consulta FIRMS API cada 15–30 min: `VIIRS_NOAA20_NRT`, `VIIRS_NOAA21_NRT`, `VIIRS_SNPP_NRT`, `MODIS_NRT`, últimas 24–48 h.
- Focos cercanos se agrupan en **eventos** (clusters) → cada evento recibe un estado de riesgo.
- Etiqueta "datos preliminares (NRT)".

### 3.3 Estados de riesgo: Prevención / Alto / Crítico
Puntaje 0–100 por evento o celda, combinando factores:

| Factor | Cómo se mide | Fuente |
|---|---|---|
| **Anomalía** | actividad actual vs mediana histórica de esa celda y semana | histórico armonizado |
| **Zona inusual** | la celda casi nunca registra fuego (frecuencia histórica baja) | histórico armonizado |
| **Difícil de manejar** | tamaño del cluster (n° focos), FRP total, crecimiento en 24 h | API en vivo |
| **Cerca de población** | distancia al centro poblado más cercano | INEI / GeoNames |
| **Cerca de zona protegida / intangible** | dentro o a < X km de ANP, reservas indígenas | SERNANP / WDPA (Protected Planet) |

| Estado | Regla orientativa | Visual |
|---|---|---|
| 🟡 **Prevención** | puntaje < 40 | llama pequeña, amarilla |
| 🟠 **Alto** | 40–70 | llama mediana, naranja |
| 🔴 **Crítico** | > 70, o zona protegida + anomalía | llama grande, roja, animada |

Accesibilidad: el estado se comunica con **tamaño + color + ícono/texto**, no solo color.

### 3.4 Predicción con barra de tiempo
- Para cada celda y semana del año: **probabilidad histórica de fuego** = fracción de años en que hubo fuego.
- Mejora opcional: modelo (Random Forest / LightGBM) con mes, actividad de semanas previas, tendencia del año,
  distancia a poblados/ANP; opcional clima (NASA POWER / Open-Meteo).
- La barra de tiempo mueve las próximas 1–12 semanas y el mapa/globo muestra el riesgo esperado.
- Se presenta como **riesgo estacional esperado**, no como certeza de que ocurra un incendio.

### 3.5 Visualización 3D (Three.js)
- **React Three Fiber** (Three.js para React) + **drei**; globo terráqueo centrado en Sudamérica.
- Llamas como sprites/shaders con `InstancedMesh` (miles de llamas sin perder fluidez).
- Se dibujan **celdas/eventos agregados**, no millones de puntos.
- Clic en una llama → abre su ficha en el **Panel de alertas**.
- Mapa 2D (Leaflet) para tareas precisas: dibujar área, ingresar lat/lon.

---

## 4. API

| Endpoint | Devuelve |
|---|---|
| `GET /api/historico/calendario?region=&desde=&hasta=` | matriz mes × año armonizada |
| `GET /api/historico/climatologia?region=` | mediana/percentiles por mes |
| `GET /api/historico/anomalias?region=&mes=` | actual vs mediana |
| `GET /api/en-vivo?bbox=&horas=24` | eventos activos con estado de riesgo |
| `GET /api/riesgo/{evento_id}` | ficha detallada: factores y puntaje |
| `GET /api/prediccion?semana=&region=` | probabilidad por celda |
| `GET /api/descargar.csv?...` | focos de la búsqueda |

---

## 5. Tecnologías

| Capa | Tecnología |
|---|---|
| Datos | NASA FIRMS (archivo + API NRT), SERNANP/WDPA, INEI/GeoNames |
| Pipeline | Python, pandas, GeoPandas, DuckDB, Parquet, scikit-learn / LightGBM |
| Backend | FastAPI (+ caché en memoria, tarea periódica para el "en vivo") |
| Frontend | React + Vite, **Three.js (React Three Fiber + drei)**, Leaflet, ECharts |
| Despliegue | Render/Railway (API) + Vercel/Netlify (web) |

---

## 6. Prioridades (MVP → extras)

1. **Armonización + calendario de fuego** (lo que evalúan los jueces).
2. **En vivo** con estados de riesgo + panel de alertas.
3. **Globo 3D con llamas.**
4. **Predicción** con barra de tiempo.
5. Descarga CSV, metodología, pulido visual.
