import { fmt } from '../constantes'

// Lista de regiones con más actividad. Clic en una fila -> se selecciona esa región.
export default function Ranking({ datos, seleccionada, onSeleccionar, max = 10 }) {
  if (!datos?.regiones?.length) return <p className="vacio">Sin datos.</p>
  const filas = datos.regiones.slice(0, max)
  const tope = filas[0].promedio_anual || 1

  return (
    <ol className="ranking">
      {filas.map((r) => (
        <li key={r.id}>
          <button className={r.id === seleccionada ? 'activo' : ''} onClick={() => onSeleccionar(r.id)}
            title={`Ver ${r.nombre}`}>
            <span className="puesto">{r.puesto}</span>
            <span className="nombre">{r.nombre.replace(/ \(.*\)$/, '')}</span>
            <span className="barra"><span style={{ width: `${(100 * r.promedio_anual) / tope}%` }} /></span>
            <span className="valor">{fmt(r.promedio_anual)}</span>
            <span className="pct">{fmt(r.porcentaje, 1)} %</span>
          </button>
        </li>
      ))}
    </ol>
  )
}
