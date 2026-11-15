import { useMemo } from 'react'
import { COLOR, fmt } from '../../constantes'
import { EJE_BASE, TOOLTIP_BASE, useEChart } from '../graficos/useEChart'

// Validación "dejando un año fuera": para cada año 2012–2021 se calcula el factor SIN ese año,
// se convierte MODIS a escala VIIRS y se compara con lo que VIIRS vio de verdad.
export default function GraficoValidacion({ anios }) {
  const opciones = useMemo(() => {
    const a = (anios ?? []).filter((x) => x.metrica === 'dias_celda')
    if (!a.length) return null
    return {
      animation: false,
      grid: { left: 64, right: 16, top: 40, bottom: 32 },
      legend: {
        top: 0, left: 0, textStyle: { color: COLOR.textoSecundario, fontSize: 12 }, itemWidth: 14, itemHeight: 10,
        data: [{ name: 'VIIRS observado', itemStyle: { color: COLOR.neutro } }, 'MODIS calibrado (predicción)'],
      },
      tooltip: {
        ...TOOLTIP_BASE, trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: 'rgba(255,255,255,.04)' } },
        formatter: (ps) => {
          const x = a[ps[0].dataIndex]
          return `<div style="font-weight:600;margin-bottom:4px">${x.anio}</div>
            <div>VIIRS observado: <b>${fmt(x.viirs_observado)}</b></div>
            <div>MODIS calibrado: <b>${fmt(x.pred_factor_mensual)}</b></div>
            <div style="color:${COLOR.textoSecundario}">Error: ${x.error_pct_mensual > 0 ? '+' : ''}${fmt(x.error_pct_mensual, 1)} % · R² mensual ${fmt(x.r2_meses, 2)}</div>`
        },
      },
      xAxis: { ...EJE_BASE, type: 'category', data: a.map((x) => String(x.anio)), splitLine: { show: false } },
      yAxis: { ...EJE_BASE, type: 'value', name: 'días-celda', nameLocation: 'end' },
      series: [
        {
          name: 'VIIRS observado', type: 'bar', barWidth: '58%',
          data: a.map((x) => ({ value: x.viirs_observado, itemStyle: { color: COLOR.neutro, borderRadius: [4, 4, 0, 0] } })),
        },
        {
          name: 'MODIS calibrado (predicción)', type: 'line', data: a.map((x) => x.pred_factor_mensual),
          color: COLOR.azul, lineStyle: { width: 2 }, symbol: 'circle', symbolSize: 8,
          itemStyle: { borderColor: COLOR.superficie, borderWidth: 2 },
        },
      ],
    }
  }, [anios])

  const ref = useEChart(opciones)
  return <div ref={ref} style={{ height: 280 }} role="img" aria-label="VIIRS observado frente a MODIS calibrado, por año" />
}
