# FireSeason — Política de estados de riesgo (llamas)

Nov 14, 2026 · @Jeanpier

## Propósito y alcance

Cada incendio activo recibe un puntaje de riesgo de 0 a 100 y uno de tres estados: **Prevención (0–39)**, **Alto (40–69)** o **Crítico (70–100)**. Esta política fija cómo se calcula ese puntaje, qué reglas fuerzan un estado sin importar el puntaje, y cuándo un incendio sube, baja o se cierra.

- **Dónde se aplica:** módulo En vivo (Perú y países vecinos, datos NRT de FIRMS) y panel de alertas.
- **Qué no decide:** el globo 3D solo dibuja el estado que esta política asigna (tamaño y color de la llama).
- **Límite:** es una herramienta de apoyo a la decisión. No reemplaza las alertas oficiales de SERFOR, SERNANP o INDECI.

## Fuentes de datos

Sí: la política necesita INEI y SERNANP, además de FIRMS. Las reservas para pueblos indígenas en aislamiento ("zonas intangibles") no son de SERNANP sino del Ministerio de Cultura, así que van como fuente aparte.

| Fuente | Dato | Uso en la política | Cobertura |
| --- | --- | --- | --- |
| NASA FIRMS – archivo (MODIS C6.1, VIIRS 375 m) | Focos 2001–hoy, armonizados | Mediana y percentiles por semana; frecuencia histórica por celda | Sudamérica |
| NASA FIRMS – API NRT | Focos de las últimas 24–48 h | Eventos en vivo, tamaño, intensidad (FRP), crecimiento | Perú y vecinos |
| INEI | Centros poblados con población (censo más reciente); límites de departamentos, provincias y distritos | Factor cercanía a población; agrupar por región | Perú |
| SERNANP | Áreas Naturales Protegidas (nacionales, regionales, privadas), zonas de amortiguamiento, zonificación interna | Factor áreas protegidas | Perú |
| Ministerio de Cultura | Reservas indígenas y territoriales (PIACI) | Factor áreas protegidas, nivel máximo | Perú |
| WDPA (Protected Planet) y GeoNames | Áreas protegidas y poblados de países vecinos | Mismos factores fuera del Perú | Sudamérica |

**Cómo se adecuan al mapa de incendios:**

1. Todo se convierte a coordenadas WGS84 (EPSG:4326), el mismo sistema que usa FIRMS.
2. Las distancias se calculan en metros con una proyección UTM (zonas 17S, 18S y 19S para el Perú).
3. El pipeline (`05_contexto.py`) descarga las capas y agrega una franja de 5 km alrededor de cada ANP y reserva PIACI.
4. En vivo, el backend calcula **foco por foco** (con un índice espacial, en milisegundos): si cae dentro de un ANP, zona de amortiguamiento, zona de protección estricta o reserva PIACI; la distancia al poblado más cercano; y los habitantes a menos de 5 km.

**Fuentes usadas en la versión actual (verificadas el 15-nov-2026):**

- SERNANP, servicio oficial `geoservicios.sernanp.gob.pe/.../sernanp_visor/servicio_descarga/MapServer`: capas 1 (ANP nacionales), 2 (zonas reservadas), 3 (ACR), 4 (ACP), 8 (zonas de amortiguamiento), 9 (zonificación; solo "Zona de Protección Estricta") y 32 (reservas PIACI, que el mismo servicio publica con datos del Ministerio de Cultura). De las reservas PIACI solo se usan las ya creadas (Reserva Indígena o Territorial), no las solicitudes.
- Centros poblados: **GeoNames** (46 772 poblados del Perú). La capa de centros poblados del INEI (sdmr.inei.gob.pe) solo cubre una zona del VRAEM, así que no sirve para todo el país. Limitación: GeoNames conoce la población de solo ~11 000 poblados, así que "habitantes a menos de 5 km" se subestima. Si se consigue el shapefile del Censo 2017 (INEI), puede reemplazar a `poblados.csv` sin cambiar el backend.

## Unidad de evaluación: el evento

El estado se asigna a un **evento**, no a cada foco suelto. Un evento es un grupo de focos que probablemente pertenecen al mismo incendio.

- **Agrupación:** focos a 2 km o menos entre sí, detectados en las últimas 24 h, forman un evento.
- **Seguimiento:** un foco nuevo a 2 km o menos de un evento abierto, dentro de 48 h, se suma a ese evento.
- **Confirmación:** un evento de un solo foco con confianza baja queda "Por confirmar". Se confirma con una segunda detección (otro pase u otro satélite).
- **Mezcla de sensores:** los focos VIIRS y MODIS cuentan igual para agrupar. Para el tamaño del evento se usan los focos VIIRS, que tienen mejor resolución (375 m).

Un evento abierto se recalcula con cada consulta a la API (cada 15–30 min). En la práctica cambia con cada pase de satélite, varias veces al día.

## Cálculo del puntaje (0–100)

El puntaje es la suma de seis factores. Cada factor tiene un máximo, y los máximos suman 100.

```latex
R = A + B + C + D + E + F
```

| Factor | Máx. | 0 puntos | Puntos intermedios | Máximo |
| --- | --- | --- | --- | --- |
| **A. Magnitud** (poco manejable) | 25 | 1–2 focos | 3–9 focos: 10 · 10–29 focos: 18 | 30 focos o más, o FRP total de 500 MW o más |
| **B. Crecimiento** en 24 h | 15 | Igual o menos focos que las 24 h previas | De 1.5 a 2 veces más: 8 | Más del doble de focos |
| **C. Anomalía histórica** (focos de la provincia en 7 días vs. la misma semana 2001–hoy) | 20 | Igual o bajo la mediana | Sobre P75: 10 · sobre P90: 15 | Sobre P95 |
| **D. Zona inusual** (años con fuego en esa celda y mes) | 10 | 30 % de los años o más | Entre 10 % y 30 %: 5 | Menos del 10 % (casi nunca arde) |
| **E. Cercanía a población** | 15 | Poblado a más de 10 km | 5–10 km: 5 · 2–5 km: 10 | Menos de 2 km, o más de 1 000 habitantes a menos de 5 km |
| **F. Áreas protegidas** | 15 | Fuera y a más de 5 km | Zona de amortiguamiento o a menos de 5 km: 8 · dentro de un ANP: 12 | Dentro de una zona de protección estricta o una reserva PIACI |

- C y D salen del **histórico armonizado**. Por eso la armonización MODIS–VIIRS es la base de todo el sistema de alertas.
- A y B salen de la **API en vivo**. E y F salen de **INEI, SERNANP y el Ministerio de Cultura**.
- Los pesos son una propuesta inicial y se ajustan con la validación de la última sección.

## Estados y reglas directas

El puntaje define el estado base. Algunas situaciones son tan graves que fuerzan un estado aunque el puntaje sea bajo; esas reglas directas siempre ganan.

| Estado | Puntaje | Qué significa | Acción sugerida |
| --- | --- | --- | --- |
| **Prevención** | 0–39 | Actividad dentro de lo normal para la zona y la época | Monitoreo; sin alerta |
| **Alto** | 40–69 | Fuera de lo normal, o cerca de personas o áreas sensibles | Aviso en el panel; revisar en cada pase de satélite |
| **Crítico** | 70–100 | Grande, creciendo o amenazando personas o áreas protegidas | Alerta prioritaria; derivar a las autoridades competentes |

**Pasa directo a Crítico** (si se cumple cualquiera):

- Tres focos o más dentro de una zona de protección estricta o una reserva PIACI.
- Diez focos o más, o FRP total de 300 MW o más, a menos de 2 km de un centro poblado.
- Cincuenta focos o más en 24 h en un solo evento.

**Como mínimo Alto** (si se cumple cualquiera):

- Cualquier foco confirmado dentro de un ANP o de su zona de amortiguamiento.
- Un evento confirmado de 3 focos o más a menos de 2 km de un centro poblado. *(Ajuste del 15-nov-2026: con "cualquier evento", el 42 % de los eventos reales quedaba en Alto, porque la mitad de los focos del Perú está a menos de 2.3 km de algún caserío.)*
- Tres focos o más en una zona inusual (menos del 10 % de los años con fuego).

**Como máximo Prevención:**

- Un evento "Por confirmar" (un solo foco de confianza baja). Se recalcula sin este límite en cuanto se confirma.

## Reglas de transición

Un incendio sube de estado al instante y baja solo con margen y tiempo. Así la alerta no parpadea entre estados con cada pase de satélite.

&#91;embedded content: transiciones de estado · 3 estados, observación y cierre\]

1. **Subir:** en cuanto el puntaje llega a 40 o a 70, o se cumple una regla directa. No se espera otra confirmación.
2. **Bajar:** el puntaje debe quedar 10 puntos bajo el umbral (bajo 60 para dejar Crítico, bajo 30 para dejar Alto) durante 24 h seguidas, sin ninguna regla directa activa.
3. **Un nivel a la vez:** Crítico baja a Alto, nunca directo a Prevención.
4. **En observación:** sin focos nuevos por 24 h, el evento conserva su estado y su llama se atenúa. Las nubes o el humo pueden ocultar el fuego al satélite.
5. **Cierre:** sin focos nuevos por 72 h, el evento se cierra, sale del mapa en vivo y pasa al histórico.
6. **Reactivación:** un foco a 2 km o menos de un evento en observación lo reactiva con su último estado. Después del cierre, un foco nuevo abre un evento nuevo.

## Ejemplos

Cuatro eventos hipotéticos muestran el puntaje y una regla directa en acción.

| Evento | A | B | C | D | E | F | Total | Estado |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1. Quema agrícola en un valle andino, agosto: 4 focos, sin crecimiento, bajo la mediana, zona que arde casi todos los años, poblado a 6 km | 10 | 0 | 0 | 0 | 5 | 0 | 15 | Prevención |
| 2. Selva baja, setiembre: 18 focos, 2.5 veces más que ayer, provincia sobre P90, arde el 20 % de los años, poblado a 12 km, en zona de amortiguamiento | 18 | 15 | 15 | 5 | 0 | 8 | 61 | Alto |
| 3. Bosque montano que casi nunca arde: 35 focos, 3 veces más que ayer, sobre P95, poblado a 3 km, dentro de un ANP | 25 | 15 | 20 | 10 | 10 | 12 | 92 | Crítico |
| 4. Dos focos confirmados a 1.5 km de un pueblo, zona y época normales | 0 | 0 | 0 | 0 | 15 | 0 | 15 | Alto (regla directa) |

**Cómo baja el evento 2:** al día siguiente deja de crecer (B = 0) y su puntaje cae a 46; sigue en Alto. Si luego baja a 8 focos y la provincia a P75, el puntaje es 33. Aún así no baja: no quedó bajo 30 y además está en zona de amortiguamiento, que lo mantiene como mínimo en Alto.

## Parámetros, visualización y validación

Todos los umbrales viven en un archivo de configuración del backend (`backend/app/services/riesgo.py` o `riesgo.yaml`). Así se ajustan sin tocar el código.

| Parámetro | Valor inicial |
| --- | --- |
| Umbral Alto / Crítico | 40 / 70 puntos |
| Margen para bajar (histéresis) | 10 puntos |
| Tiempo mínimo para bajar | 24 h |
| Radio de agrupación de focos | 2 km |
| Ventana de seguimiento | 48 h |
| Focos mínimos para la regla "a < 2 km de un poblado" | 3 |
| Paso a "En observación" / cierre | 24 h / 72 h sin focos |
| Frecuencia de consulta a la API FIRMS | cada 15–30 min |

**Cómo se ve cada estado en el globo 3D:**

| Estado | Color | Tamaño de la llama | Animación | Etiqueta |
| --- | --- | --- | --- | --- |
| Prevención | Amarillo | 1× | Suave | "Prevención" |
| Alto | Naranja | 1.6× | Media | "Alto" |
| Crítico | Rojo | 2.3× | Pulso rápido + halo | "Crítico" |
| En observación | Color de su estado al 50 % | Igual | Sin animación | "En observación" |

El estado nunca se comunica solo con color: tamaño, animación y texto lo hacen legible para personas con daltonismo.

**Validación antes de la demo:**

- [ ] Reproducir temporadas pasadas (2012–2025) con datos VIIRS como si fueran "en vivo" y contar cuántos eventos caen en cada estado.
- [ ] Revisar que Crítico sea poco frecuente (meta orientativa: 5–10 % de los eventos); si no, subir umbrales o pesos.
- [ ] Comprobar que temporadas severas conocidas, como setiembre de 2024 en la Amazonía peruana, aparezcan en Alto o Crítico.
- [ ] Si es posible, mostrar los pesos a un especialista (SERFOR, SERNANP o una universidad) y anotar sus ajustes.
