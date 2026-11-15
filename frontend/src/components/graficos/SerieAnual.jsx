import { useMemo } from 'react'
import { COLOR, METRICAS, fmt } from '../../constantes'
import { EJE_BASE, TOOLTIP_BASE, useEChart } from './useEChart'

// Total por año. La banda clara es el margen de error de la calibración (solo antes de 2012).
export default function SerieAnual({ anios, metrica }) {
  const opciones = useMemo(() => {
    if (!anios?.length) return null
    const x = anios.map((a) => String(a.anio))
    return {
      animation: false,
      grid: { left: 64, right: 24, top: 24, bottom: 32 },
      tooltip: {
        ...TOOLTIP_BASE, trigger: 'axis',
        formatter: (ps) => {
          const a = anios[ps[0].dataIndex]
          const banda = a.ic90_bajo !== a.ic90_alto
            ? `<div style="color:${COLOR.textoSecundario}">Rango 90 %: ${fmt(a.ic90_bajo)} – ${fmt(a.ic90_alto)}</div>` : ''
          return `<div style="font-weight:600;margin-bottom:4px">${a.anio}</div>
            <div><b>${fmt(a.valor)}</b> ${METRICAS[metrica].corto}</div>${banda}
            <div style="color:${COLOR.textoTenue};font-size:11px;margin-top:4px">
              ${a.anio >= 2012 ? 'VIIRS observado' : 'MODIS calibrado'} · calidad ${a.calidad_minima}</div>`
        },
      },
      xAxis: { ...EJE_BASE, type: 'category', data: x, boundaryGap: false, splitLine: { show: false } },
      yAxis: { ...EJE_BASE, type: 'value', name: METRICAS[metrica].corto, min: 0 },
      series: [
        // Banda de incertidumbre = base invisible + diferencia apilada
        { type: 'line', data: anios.map((a) => a.ic90_bajo), stack: 'ic', symbol: 'none', lineStyle: { opacity: 0 },
          tooltip: { show: false }, silent: true },
        { type: 'line', data: anios.map((a) => a.ic90_alto - a.ic90_bajo), stack: 'ic', symbol: 'none',
          lineStyle: { opacity: 0 }, areaStyle: { color: COLOR.azul, opacity: 0.18 }, silent: true },
        {
          name: 'Serie armonizada', type: 'line', color: COLOR.azul, lineStyle: { width: 2 },
          symbol: 'circle', symbolSize: 7, itemStyle: { borderColor: COLOR.superficie, borderWidth: 2 },
          data: anios.map((a) => ({
            value: a.valor,
            // años de calidad baja (solo Terra): punto hueco
            itemStyle: a.calidad_minima === 'baja' ? { color: COLOR.superficie, borderColor: COLOR.azul } : undefined,
          })),
          markLine: x.includes('2012') ? {
            silent: true, symbol: 'none', lineStyle: { color: COLOR.textoTenue, type: 'dashed' },
            label: { color: COLOR.textoTenue, formatter: 'VIIRS desde 2012', position: 'insideEndTop', fontSize: 11 },
            data: [{ xAxis: '2012' }],
          } : undefined,
        },
      ],
    }
  }, [anios, metrica])

  const ref = useEChart(opciones)
  return <div ref={ref} style={{ height: 280 }} role="img" aria-label="Actividad de fuego por año" />
}
