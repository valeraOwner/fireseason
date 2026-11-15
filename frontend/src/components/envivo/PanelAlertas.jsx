import { ESTADOS, ORDEN_ESTADOS, hace } from '../../constantes'

const ZONA_CORTA = { estricta: 'reserva / protección estricta', anp: 'dentro de ANP', amortiguamiento: 'zona de amortiguamiento' }

// Lista de eventos ordenados por gravedad, con filtros por estado.
export default function PanelAlertas({ eventos, filtro, onFiltro, verObservacion, onVerObservacion, seleccionado, onSeleccionar }) {
  const visibles = eventos.filter((e) => filtro.includes(e.estado) && (verObservacion || !e.en_observacion))

  const alternar = (estado) =>
    onFiltro(filtro.includes(estado) ? filtro.filter((x) => x !== estado) : [...filtro, estado])

  return (
    <section className="tarjeta panel-alertas">
      <header>
        <div>
          <h3>Panel de alertas</h3>
          <p>{visibles.length} de {eventos.length} eventos</p>
        </div>
      </header>

      <div className="filtro-estados" role="group" aria-label="Filtrar por estado">
        {ORDEN_ESTADOS.map((id) => (
          <button key={id} aria-pressed={filtro.includes(id)} className={filtro.includes(id) ? 'activo' : ''}
            style={{ '--estado': ESTADOS[id].color }} onClick={() => alternar(id)}>
            <span aria-hidden="true">{ESTADOS[id].icono}</span> {ESTADOS[id].nombre}
          </button>
        ))}
        <label className="casilla">
          <input type="checkbox" checked={verObservacion} onChange={(e) => onVerObservacion(e.target.checked)} />
          En observación
        </label>
      </div>

      <ul className="lista-eventos">
        {visibles.length === 0 && <li className="vacio">No hay eventos con estos filtros.</li>}
        {visibles.slice(0, 200).map((ev) => {
          const est = ESTADOS[ev.estado]
          return (
            <li key={ev.id}>
              <button className={`${seleccionado === ev.id ? 'activo' : ''} ${ev.en_observacion ? 'atenuado' : ''}`}
                style={{ '--estado': est.color }} onClick={() => onSeleccionar(ev.id)}>
                <span className="insignia">{est.icono} {est.nombre}</span>
                <span className="lugar">
                  {ev.provincia ? <>{ev.provincia} <small>{ev.departamento}</small></> : <>Zona fronteriza <small>fuera del Perú</small></>}
                </span>
                <span className="puntaje">{ev.puntaje}</span>
                <span className="meta">
                  {ev.focos_24h} focos/24 h · {hace(ev.ultima_deteccion)}
                  {ZONA_CORTA[ev.zona_protegida] && ` · ${ZONA_CORTA[ev.zona_protegida]}`}
                  {ev.en_observacion && ' · en observación'}
                  {ev.por_confirmar && ' · por confirmar'}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
      {visibles.length > 200 && <p className="nota">Se muestran los 200 más graves.</p>}
    </section>
  )
}
