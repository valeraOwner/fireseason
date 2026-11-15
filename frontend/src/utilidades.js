import { MESES } from './constantes'

// Resumen de la temporada crítica: 'Ago – Oct' y qué % del año representa.
export function resumenTemporada(clima) {
  if (!clima?.meses_criticos?.length) return null
  const meses = clima.meses_criticos
  const pct = clima.meses.filter((m) => meses.includes(m.mes)).reduce((s, m) => s + m.porcentaje_del_anio, 0)
  const nombres = meses.map((m) => MESES[m - 1])
  const seguidos = meses.every((m, i) => i === 0 || m === meses[i - 1] + 1)
  const texto = seguidos && nombres.length > 2 ? `${nombres[0]} – ${nombres.at(-1)}` : nombres.join(', ')
  return { texto, pct, meses }
}

