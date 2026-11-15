import { useMemo } from 'react'
import { CATEGORIAS, COLOR, MESES, MESES_LARGOS, METRICAS, RAMPA_FUEGO, fmt } from '../../constantes'
import { EJE_BASE, TOOLTIP_BASE, useEChart } from './useEChart'

// Calendario de fuego: filas = años (el más reciente arriba), columnas = meses.
// modo 'actividad' -> color según cantidad de fuego
// modo 'anomalia'  -> color según cuánto se aleja de lo normal para ESE mes
export default function CalendarioFuego({ celdas, metrica, modo, onSeleccionar }) {
  const opciones = useMemo(() => {
    if (!celdas?.length) return null
    const anios = [...new Set(celdas.map((c) => c.anio))].sort((a, b) => a - b)
    const etiquetaAnio = (a) => {
      const c = celdas.find((x) => x.anio === a)
      return c?.calidad === 'baja' ? `${a}*` : String(a)
    }
    const indiceCategoria = Object.fromEntries(CATEGORIAS.map((c, i) => [c.id, i]))

    // [mes, fila, valor, categoría, índice en celdas]
    const datos = celdas.map((c, i) => [c.mes - 1, anios.indexOf(c.anio), c.valor, indiceCategoria[c.categoria] ?? 0, i])

    return {
      animation: false,
      grid: { left: 56, right: 16, top: 8, bottom: 84 },
      tooltip: { ...TOOLTIP_BASE, formatter: (p) => tooltip(celdas[p.data[4]], metrica) },
      xAxis: { ...EJE_BASE, type: 'category', data: MESES, position: 'top', splitLine: { show: false },
        axisLine: { show: false } },
      yAxis: { ...EJE_BASE, type: 'category', data: anios.map(etiquetaAnio), splitLine: { show: false },
        axisLine: { show: false } },
      visualMap: modo === 'anomalia' ? leyendaAnomalia() : leyendaActividad(celdas, metrica),
      series: [{
        type: 'heatmap',
        data: datos,
        itemStyle: { borderColor: COLOR.superficie, borderWidth: 2, borderRadius: 3 },
        emphasis: { itemStyle: { borderColor: COLOR.texto, borderWidth: 2 } },
      }],
    }
  }, [celdas, metrica, modo])

  const ref = useEChart(opciones, (p) => {
    const c = celdas[p.data?.[4]]
    if (c) onSeleccionar?.(c)
  })
  const filas = celdas?.length ? new Set(celdas.map((c) => c.anio)).size : 20
  return <div ref={ref} style={{ height: filas * 24 + 100 }} role="img"
    aria-label="Calendario de fuego por año y mes" />
}

// Leyenda por tramos según la cantidad (tramos calculados con los propios datos)
function leyendaActividad(celdas, metrica) {
  const valores = celdas.map((c) => c.valor).filter((v) => v > 0).sort((a, b) => a - b)
  const q = (p) => valores[Math.min(valores.length - 1, Math.floor(p * valores.length))] ?? 0
  const cortes = [...new Set([0.25, 0.5, 0.7, 0.85, 0.95].map(q).map(redondear))].filter((v) => v > 0)
  const tramos = [{ value: 0, label: '0', color: '#242322' }]
  let inicio = 0
  cortes.forEach((fin, i) => {
    tramos.push({ gt: inicio, lte: fin, label: `${fmt(inicio)} – ${fmt(fin)}`, color: RAMPA_FUEGO[i] })
    inicio = fin
  })
  tramos.push({ gt: inicio, label: `> ${fmt(inicio)}`, color: RAMPA_FUEGO[RAMPA_FUEGO.length - 1] })
  return {
    type: 'piecewise', dimension: 2, pieces: tramos, orient: 'horizontal', left: 'center', bottom: 8,
    itemWidth: 14, itemHeight: 14, itemGap: 10, textStyle: { color: COLOR.textoSecundario, fontSize: 11 },
    text: [METRICAS[metrica].corto, ''], showLabel: true,
  }
}

function leyendaAnomalia() {
  return {
    type: 'piecewise', dimension: 3, orient: 'horizontal', left: 'center', bottom: 8,
    pieces: CATEGORIAS.map((c, i) => ({ value: i, label: c.etiqueta, color: c.color })),
    itemWidth: 14, itemHeight: 14, itemGap: 10, textStyle: { color: COLOR.textoSecundario, fontSize: 11 },
  }
}

function redondear(v) {
  if (v < 10) return Math.ceil(v)
  const m = 10 ** Math.floor(Math.log10(v))
  return Math.ceil(v / (m / 2)) * (m / 2)
}

function tooltip(c, metrica) {
  if (!c) return ''
  const signo = c.anomalia_pct > 0 ? '+' : ''
  const anomalia = c.anomalia_pct == null ? '—' : `${signo}${fmt(c.anomalia_pct)} %`
  const cat = CATEGORIAS.find((x) => x.id === c.categoria)
  return `
    <div style="font-weight:600;margin-bottom:4px">${MESES_LARGOS[c.mes - 1]} ${c.anio}</div>
    <div><b>${fmt(c.valor)}</b> ${METRICAS[metrica].corto}</div>
    <div style="color:${COLOR.textoSecundario}">Mediana histórica del mes: ${fmt(c.mediana)}</div>
    <div style="color:${COLOR.textoSecundario}">Diferencia: ${anomalia} · percentil ${fmt(c.percentil)}</div>
    <div style="margin-top:4px">${cat ? cat.etiqueta : ''}</div>
    <div style="color:${COLOR.textoTenue};font-size:11px;margin-top:4px">${c.fuente} · calidad ${c.calidad}</div>`
}
