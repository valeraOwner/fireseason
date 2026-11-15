import { useMemo } from 'react'
import { COLOR, MESES, MESES_LARGOS, fmt } from '../../constantes'
import { EJE_BASE, TOOLTIP_BASE, useEChart } from './useEChart'

// Temporada crítica: barras = mediana histórica de cada mes (naranja = meses críticos)
// línea = el año elegido, para comparar "este año" contra lo normal.
export default function Climatologia({ clima, anio, valoresAnio }) {
  const opciones = useMemo(() => {
    if (!clima?.meses?.length) return null
    const criticos = new Set(clima.meses_criticos)
    const porMes = Object.fromEntries((valoresAnio ?? []).map((c) => [c.mes, c.valor]))

    return {
      animation: false,
      grid: { left: 56, right: 16, top: 40, bottom: 32 },
      legend: {
        top: 0, left: 0, textStyle: { color: COLOR.textoSecundario, fontSize: 12 }, itemWidth: 14, itemHeight: 10,
        data: [{ name: 'Mediana 2003–hoy', itemStyle: { color: COLOR.naranja } }, `Año ${anio}`],
      },
      tooltip: {
        ...TOOLTIP_BASE, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(255,255,255,.04)' } },
        formatter: (ps) => {
          const m = clima.meses[ps[0].dataIndex]
          const v = porMes[m.mes]
          return `<div style="font-weight:600;margin-bottom:4px">${MESES_LARGOS[m.mes - 1]}${criticos.has(m.mes) ? ' · temporada crítica' : ''}</div>
            <div>Mediana: <b>${fmt(m.mediana)}</b> (${fmt(m.porcentaje_del_anio, 1)} % del año)</div>
            <div style="color:${COLOR.textoSecundario}">P75: ${fmt(m.p75)} · P90: ${fmt(m.p90)}</div>
            ${v != null ? `<div style="margin-top:4px">${anio}: <b>${fmt(v)}</b></div>` : ''}`
        },
      },
      xAxis: { ...EJE_BASE, type: 'category', data: MESES, splitLine: { show: false } },
      yAxis: { ...EJE_BASE, type: 'value', name: 'días-celda', nameLocation: 'end' },
      series: [
        {
          name: 'Mediana 2003–hoy', type: 'bar', barWidth: '58%',
          data: clima.meses.map((m) => ({
            value: m.mediana,
            itemStyle: { color: criticos.has(m.mes) ? COLOR.naranja : COLOR.neutro, borderRadius: [4, 4, 0, 0] },
          })),
        },
        {
          name: `Año ${anio}`, type: 'line', data: clima.meses.map((m) => porMes[m.mes] ?? null),
          color: COLOR.azul, lineStyle: { width: 2 }, symbol: 'circle', symbolSize: 8,
          itemStyle: { borderColor: COLOR.superficie, borderWidth: 2 },
        },
      ],
    }
  }, [clima, anio, valoresAnio])

  const ref = useEChart(opciones)
  return <div ref={ref} style={{ height: 300 }} role="img" aria-label="Mediana mensual y año seleccionado" />
}
