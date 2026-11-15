import * as echarts from 'echarts'
import { useEffect, useRef } from 'react'
import { COLOR } from '../../constantes'

// Hook que conecta un <div> con un gráfico de ECharts.
// Uso:  const ref = useEChart(opciones, onClick);  return <div ref={ref} style={{height: 400}} />
export function useEChart(opciones, onClick) {
  const ref = useRef(null)
  const grafico = useRef(null)
  const clickRef = useRef(onClick)
  useEffect(() => { clickRef.current = onClick }, [onClick])

  // Crear el gráfico una sola vez y adaptarlo al tamaño del contenedor
  useEffect(() => {
    grafico.current = echarts.init(ref.current, null, { renderer: 'canvas' })
    grafico.current.on('click', (p) => clickRef.current?.(p))
    const observador = new ResizeObserver(() => grafico.current?.resize())
    observador.observe(ref.current)
    return () => {
      observador.disconnect()
      grafico.current?.dispose()
    }
  }, [])

  // Actualizar cuando cambian los datos/opciones
  useEffect(() => {
    if (grafico.current && opciones) grafico.current.setOption(opciones, { notMerge: true })
  }, [opciones])

  return ref
}

// Estilo base compartido (tema oscuro, ejes discretos)

export const TOOLTIP_BASE = {
  backgroundColor: '#262624',
  borderColor: COLOR.eje,
  textStyle: { color: COLOR.texto, fontSize: 12 },
  extraCssText: 'box-shadow: 0 4px 16px rgba(0,0,0,.4); border-radius: 6px;',
}

export const EJE_BASE = {
  axisLine: { lineStyle: { color: COLOR.eje } },
  axisTick: { show: false },
  axisLabel: { color: COLOR.textoSecundario, fontSize: 11 },
  splitLine: { lineStyle: { color: COLOR.grilla } },
  nameTextStyle: { color: COLOR.textoTenue, fontSize: 11 },
}
