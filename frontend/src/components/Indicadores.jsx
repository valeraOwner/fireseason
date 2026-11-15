import { CATEGORIAS, MESES_LARGOS, fmt } from '../constantes'
import { resumenTemporada } from '../utilidades'

// Cifras clave arriba de los gráficos.
export default function Indicadores({ anomalia, clima, serieAnual }) {
  const temporada = resumenTemporada(clima)
  const confiables = (serieAnual ?? []).filter((a) => a.calidad_minima !== 'baja')
  const pico = confiables.reduce((max, a) => (!max || a.valor > max.valor ? a : max), null)
  const promedio = confiables.length ? confiables.reduce((s, a) => s + a.valor, 0) / confiables.length : null
  const cat = CATEGORIAS.find((c) => c.id === anomalia?.categoria)
  const signo = anomalia?.anomalia_pct > 0 ? '+' : ''

  return (
    <div className="indicadores">
      <article className="tarjeta indicador">
        <h3>Último mes ({anomalia ? `${MESES_LARGOS[anomalia.mes - 1]} ${anomalia.anio}` : '—'})</h3>
        <p className="cifra">{anomalia?.anomalia_pct == null ? '—' : `${signo}${fmt(anomalia.anomalia_pct)} %`}</p>
        <p className="detalle">
          {fmt(anomalia?.valor)} días-celda vs. mediana {fmt(anomalia?.mediana)}
        </p>
        {cat && <span className="chip" style={{ '--chip': cat.color }}>{cat.etiqueta}</span>}
      </article>

      <article className="tarjeta indicador">
        <h3>Temporada crítica</h3>
        <p className="cifra">{temporada?.texto ?? '—'}</p>
        <p className="detalle">{temporada ? `${fmt(temporada.pct)} % de la actividad de un año típico` : ''}</p>
      </article>

      <article className="tarjeta indicador">
        <h3>Año más activo</h3>
        <p className="cifra">{pico?.anio ?? '—'}</p>
        <p className="detalle">{pico ? `${fmt(pico.valor)} (${fmt(100 * (pico.valor / promedio - 1))} % sobre el promedio)` : ''}</p>
      </article>

      <article className="tarjeta indicador">
        <h3>Promedio anual</h3>
        <p className="cifra">{fmt(promedio)}</p>
        <p className="detalle">{confiables.length ? `${confiables[0].anio}–${confiables.at(-1).anio}` : ''}</p>
      </article>
    </div>
  )
}
