import { useMemo } from 'react'
import { COLOR, fmt, rangoFechas } from '../../constantes'
import { EJE_BASE, TOOLTIP_BASE, useEChart } from '../graficos/useEChart'

// Próximas 12 semanas: barras = fuego esperado por el modelo (la semana elegida en naranja),
// línea = lo normal según la climatología. Clic en una barra para elegir la semana.
export default function SemanasPrediccion({ semanas, h, onElegir }) {
  const opciones = useMemo(() => {
    if (!semanas?.length) return null
    return {
      animation: false,
      grid: { left: 52, right: 16, top: 40, bottom: 44 },
      legend: {
        top: 0, left: 0, textStyle: { color: COLOR.textoSecundario, fontSize: 12 }, itemWidth: 14, itemHeight: 10,
        data: [{ name: 'Esperado (modelo)', itemStyle: { color: COLOR.naranja } }, 'Normal (2013–2025)'],
      },
      tooltip: {
        ...TOOLTIP_BASE, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(255,255,255,.04)' } },
        formatter: (ps) => {
          const s = semanas[ps[0].dataIndex]
          const cambio = s.normal > 0 ? Math.round(100 * (s.esperado / s.normal - 1)) : null
          return `<div style="font-weight:600;margin-bottom:4px">Semana ${s.semana} · ${rangoFechas(s.inicio, s.fin)}</div>
            <div>Esperado: <b>${fmt(s.esperado)}</b> celdas con fuego</div>
            <div>Normal: ${fmt(s.normal)}${cambio != null ? ` (${cambio > 0 ? '+' : ''}${cambio} %)` : ''}</div>
            <div style="color:${COLOR.textoSecundario}">${fmt(s.celdas_alto_riesgo)} celdas con riesgo alto o muy alto</div>`
        },
      },
      xAxis: {
        ...EJE_BASE, type: 'category', splitLine: { show: false },
        data: semanas.map((s) => `+${s.h}`),
        name: 'semanas hacia adelante', nameLocation: 'middle', nameGap: 28,
      },
      yAxis: { ...EJE_BASE, type: 'value', name: 'celdas con fuego', nameLocation: 'end' },
      series: [
        {
          name: 'Esperado (modelo)', type: 'bar', barWidth: '58%',
          data: semanas.map((s) => ({
            value: s.esperado,
            itemStyle: { color: s.h === h ? COLOR.naranja : COLOR.neutro, borderRadius: [4, 4, 0, 0] },
          })),
        },
        {
          name: 'Normal (2013–2025)', type: 'line', data: semanas.map((s) => s.normal),
          color: COLOR.azul, lineStyle: { width: 2 }, symbol: 'circle', symbolSize: 8,
          itemStyle: { borderColor: COLOR.superficie, borderWidth: 2 },
        },
      ],
    }
  }, [semanas, h])

  const ref = useEChart(opciones, (p) => onElegir(semanas[p.dataIndex].h))
  return <div ref={ref} style={{ height: 260, cursor: 'pointer' }} role="img"
    aria-label="Celdas con fuego esperadas en las próximas 12 semanas frente a lo normal" />
}
