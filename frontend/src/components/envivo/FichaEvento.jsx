import { useEffect, useState } from 'react'
import { ESTADOS, fmt, hace, horaPeru } from '../../constantes'
import { api } from '../../services/api'

// Detalle de un evento: por qué tiene ese estado (los 6 factores y las reglas).
export default function FichaEvento({ id, onCerrar }) {
  const [ficha, setFicha] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let vigente = true
    setFicha(null)
    setError(null)
    api.evento(id).then((f) => vigente && setFicha(f)).catch((e) => vigente && setError(e.message))
    return () => { vigente = false }
  }, [id])

  if (error) return <section className="tarjeta ficha"><p>{error}</p><button className="cerrar" onClick={onCerrar}>Cerrar</button></section>
  if (!ficha) return <section className="tarjeta ficha"><p className="vacio">Cargando ficha…</p></section>

  const est = ESTADOS[ficha.estado]
  return (
    <section className="tarjeta ficha" style={{ '--estado': est.color }}>
      <header>
        <div>
          <span className="insignia grande">{est.icono} {est.nombre}</span>
          <h3>{ficha.provincia ? `${ficha.provincia}, ${ficha.departamento}` : 'Zona fronteriza (fuera del Perú)'}</h3>
          <p>{ficha.lat.toFixed(3)}, {ficha.lon.toFixed(3)} · {est.accion}</p>
        </div>
        <button className="cerrar" onClick={onCerrar} aria-label="Cerrar ficha">✕</button>
      </header>

      <div className="ficha-cifras">
        <div><span>Puntaje</span><strong>{ficha.puntaje}<small>/100</small></strong></div>
        <div><span>Focos 24 h</span><strong>{ficha.focos_24h}</strong></div>
        <div><span>FRP 24 h</span><strong>{fmt(ficha.frp_24h)}<small> MW</small></strong></div>
        <div><span>Última detección</span><strong className="chico">{hace(ficha.ultima_deteccion)}</strong></div>
      </div>

      {(ficha.en_observacion || ficha.por_confirmar) && (
        <p className="etiqueta-estado">
          {ficha.en_observacion && 'En observación: sin focos nuevos en 24 h (puede estar oculto por nubes o humo). '}
          {ficha.por_confirmar && 'Por confirmar: un solo foco de confianza baja.'}
        </p>
      )}

      <h4>Factores del puntaje</h4>
      <ul className="factores">
        {Object.entries(ficha.factores).map(([letra, f]) => (
          <li key={letra} className={f.puntos == null ? 'pendiente' : ''}>
            <span className="letra">{letra}</span>
            <span className="nombre">{f.nombre}</span>
            <span className="barra"><span style={{ width: `${100 * (f.puntos ?? 0) / f.max}%` }} /></span>
            <span className="valor">{f.puntos ?? '—'}<small>/{f.max}</small></span>
            <span className="detalle">{f.detalle}</span>
          </li>
        ))}
      </ul>

      {ficha.reglas.length > 0 && (
        <>
          <h4>Reglas aplicadas</h4>
          <ul className="reglas">{ficha.reglas.map((r) => <li key={r}>{r}</li>)}</ul>
        </>
      )}

      <h4>Últimas 48 h</h4>
      <ol className="historia">
        {ficha.historia.map((h) => (
          <li key={h.hora} style={{ '--estado': ESTADOS[h.estado].color }} title={`${horaPeru(h.hora)}: ${h.puntaje} pts, ${ESTADOS[h.estado].nombre}`}>
            <span className="punto" style={{ height: `${Math.max(h.puntaje, 4)}%` }} />
            <small>{horaPeru(h.hora).split(',').pop()}</small>
          </li>
        ))}
      </ol>
      <p className="nota">
        Detectado por {ficha.satelites.join(', ')} · primera detección {horaPeru(ficha.primera_deteccion)} (hora de Perú).
      </p>
    </section>
  )
}
