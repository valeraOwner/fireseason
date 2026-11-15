import { useCallback, useEffect, useState } from 'react'
import FichaEvento from '../components/envivo/FichaEvento'
import PanelAlertas from '../components/envivo/PanelAlertas'
import Globo3D from '../components/globo/Globo3D'
import IconoLlama from '../components/globo/IconoLlama'
import { ESTADOS, ORDEN_ESTADOS, hace } from '../constantes'
import { api } from '../services/api'

const REFRESCO_MS = 5 * 60 * 1000

// Página del globo 3D: los mismos eventos "en vivo", dibujados como llamas.
export default function Globo() {
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState(null)
  const [seleccionado, setSeleccionado] = useState(null)
  const [hover, setHover] = useState(null)
  const [filtro, setFiltro] = useState(ORDEN_ESTADOS)
  const [verObservacion, setVerObservacion] = useState(false)

  useEffect(() => {
    const cargar = () => api.enVivo()
      .then((d) => { setDatos(d); setError(null) })
      .catch((e) => setError(e.message))
    cargar()
    const reloj = setInterval(cargar, REFRESCO_MS)
    return () => clearInterval(reloj)
  }, [])

  const onHover = useCallback((h) => setHover(h), [])

  if (error && !datos) {
    return (
      <div className="tarjeta aviso">
        <h2>No se pudieron obtener los incendios en vivo</h2>
        <p>{error}</p>
      </div>
    )
  }

  const eventos = datos?.eventos ?? []
  const visibles = eventos.filter((e) => filtro.includes(e.estado) && (verObservacion || !e.en_observacion))

  return (
    <>
      <h2 className="titulo-region">
        Globo de incendios
        <span>{datos ? `Perú y zona fronteriza · actualizado ${hace(datos.actualizado)}` : 'Consultando NASA FIRMS…'}</span>
      </h2>

      <div className="grilla en-vivo">
        <section className="tarjeta contenedor-globo">
          <Globo3D eventos={visibles} seleccionado={seleccionado} onSeleccionar={setSeleccionado} onHover={onHover} />

          {/* Leyenda: el estado se lee por color, tamaño y texto */}
          <div className="leyenda-globo" aria-label="Leyenda">
            {ORDEN_ESTADOS.map((id) => (
              <div key={id}>
                <IconoLlama color={ESTADOS[id].color} escala={ESTADOS[id].escala} />
                <strong>{ESTADOS[id].nombre}</strong>
                <span>{datos?.resumen[id] ?? '—'}</span>
              </div>
            ))}
            <p><IconoLlama color={ESTADOS.alto.color} atenuada /> Tenue y quieta = en observación (sin focos nuevos en 24 h)</p>
          </div>

          <p className="ayuda-globo">Arrastra para girar · rueda para acercar · clic en una llama para ver su ficha</p>

          {hover && (
            <div className="tooltip-globo" style={{ left: hover.x, top: hover.y, '--estado': ESTADOS[hover.evento.estado].color }}>
              <strong>{ESTADOS[hover.evento.estado].icono} {ESTADOS[hover.evento.estado].nombre}</strong> · {hover.evento.puntaje} pts<br />
              {hover.evento.provincia ? `${hover.evento.provincia}, ${hover.evento.departamento}` : 'Fuera del Perú'}<br />
              {hover.evento.focos_24h} focos en 24 h · último {hace(hover.evento.ultima_deteccion)}
            </div>
          )}
        </section>

        <div className="columna">
          {seleccionado && <FichaEvento id={seleccionado} onCerrar={() => setSeleccionado(null)} />}
          <PanelAlertas eventos={eventos} filtro={filtro} onFiltro={setFiltro}
            verObservacion={verObservacion} onVerObservacion={setVerObservacion}
            seleccionado={seleccionado} onSeleccionar={setSeleccionado} />
        </div>
      </div>
      {datos && <p className="aviso-nrt" style={{ marginTop: 12 }}>⚠️ {datos.aviso}</p>}
    </>
  )
}
