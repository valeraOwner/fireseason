import { METRICAS } from '../constantes'

// Fila de filtros: región (departamento -> provincia), rango de años y métrica.
export default function Filtros({ regiones, filtros, onCambiar, anioMax }) {
  const deps = regiones.filter((r) => r.nivel === 'departamento')
  const depActual = filtros.region === 'peru' ? '' : filtros.region.split('__')[0]
  const provs = regiones.filter((r) => r.nivel === 'provincia' && r.departamento_id === depActual)
  const anios = Array.from({ length: anioMax - 2001 + 1 }, (_, i) => 2001 + i)

  return (
    <div className="filtros">
      <label>
        <span>Departamento</span>
        <select value={depActual} onChange={(e) => onCambiar({ region: e.target.value || 'peru' })}>
          <option value="">Todo el Perú</option>
          {deps.map((d) => <option key={d.id} value={d.id}>{d.nombre}</option>)}
        </select>
      </label>

      <label>
        <span>Provincia</span>
        <select value={filtros.region.includes('__') ? filtros.region : ''} disabled={!depActual}
          onChange={(e) => onCambiar({ region: e.target.value || depActual })}>
          <option value="">{depActual ? 'Todas' : '—'}</option>
          {provs.map((p) => <option key={p.id} value={p.id}>{p.nombre.replace(/ \(.*\)$/, '')}</option>)}
        </select>
      </label>

      <label>
        <span>Desde</span>
        <select value={filtros.desde} onChange={(e) => onCambiar({ desde: Number(e.target.value) })}>
          {anios.filter((a) => a <= filtros.hasta).map((a) => <option key={a} value={a}>{a}{a < 2003 ? ' *' : ''}</option>)}
        </select>
      </label>

      <label>
        <span>Hasta</span>
        <select value={filtros.hasta} onChange={(e) => onCambiar({ hasta: Number(e.target.value) })}>
          {anios.filter((a) => a >= filtros.desde).map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
      </label>

      <div className="segmentado" role="radiogroup" aria-label="Métrica">
        <span>Métrica</span>
        <div>
          {Object.entries(METRICAS).map(([id, m]) => (
            <button key={id} role="radio" aria-checked={filtros.metrica === id} title={m.ayuda}
              className={filtros.metrica === id ? 'activo' : ''} onClick={() => onCambiar({ metrica: id })}>
              {m.nombre}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
