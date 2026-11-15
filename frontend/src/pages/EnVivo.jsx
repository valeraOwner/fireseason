import { useCallback, useEffect, useState } from 'react'
import FichaEvento from '../components/envivo/FichaEvento'
import MapaEnVivo from '../components/envivo/MapaEnVivo'
import PanelAlertas from '../components/envivo/PanelAlertas'
import { ESTADOS, ORDEN_ESTADOS, hace, horaPeru } from '../constantes'
import { api } from '../services/api'

const REFRESCO_MS = 5 * 60 * 1000   // la página pregunta cada 5 min; el backend renueva FIRMS cada 15 min

export default function EnVivo() {
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState(null)
  const [cargando, setCargando] = useState(true)
  const [seleccionado, setSeleccionado] = useState(null)
  const [filtro, setFiltro] = useState(ORDEN_ESTADOS)
  const [verObservacion, setVerObservacion] = useState(false)

  const cargar = useCallback((actualizar = false) => {
    setCargando(true)
    api.enVivo(actualizar)
      .then((d) => { setDatos(d); setError(null) })
      .catch((e) => setError(e.message))
      .finally(() => setCargando(false))
  }, [])

  useEffect(() => {
    cargar()
    const reloj = setInterval(() => cargar(), REFRESCO_MS)
    return () => clearInterval(reloj)
  }, [cargar])

  if (error && !datos) {
    return (
      <div className="tarjeta aviso">
        <h2>No se pudieron obtener los incendios en vivo</h2>
        <p>{error}</p>
        <p>Revisa que el backend esté corriendo y que el archivo <code>.env</code> tenga tu <code>FIRMS_MAP_KEY</code>.</p>
      </div>
    )
  }
  if (!datos) return <p className="vacio">Consultando satélites de NASA FIRMS…</p>

  const { resumen } = datos
  // En el mapa se muestran los mismos eventos que en el panel (mismos filtros)
  const visibles = datos.eventos.filter((e) => filtro.includes(e.estado) && (verObservacion || !e.en_observacion))
  const idsVisibles = new Set(visibles.map((e) => e.id))
  const focosVisibles = datos.focos.filter((f) => idsVisibles.has(f.evento_id))

  return (
    <>
      <h2 className="titulo-region">
        Incendios en vivo
        <span>Perú y zona fronteriza · últimas 72 h · actualizado {hace(datos.actualizado)} ({horaPeru(datos.actualizado)})</span>
        <button className="boton secundario" onClick={() => cargar(true)} disabled={cargando}>
          {cargando ? 'Actualizando…' : 'Actualizar'}
        </button>
      </h2>

      <p className="aviso-nrt">⚠️ {datos.aviso}</p>
      {datos.advertencias.length > 0 && <p className="aviso-nrt">{datos.advertencias.join(' · ')}</p>}

      <div className="indicadores">
        {ORDEN_ESTADOS.map((id) => (
          <article key={id} className="tarjeta indicador estado" style={{ '--estado': ESTADOS[id].color }}>
            <h3><span aria-hidden="true">{ESTADOS[id].icono}</span> {ESTADOS[id].nombre}</h3>
            <p className="cifra">{resumen[id]}</p>
            <p className="detalle">Activos · {ESTADOS[id].accion}</p>
          </article>
        ))}
        <article className="tarjeta indicador">
          <h3>En observación</h3>
          <p className="cifra">{resumen.en_observacion}</p>
          <p className="detalle">Sin focos nuevos en 24 h; conservan su último estado</p>
        </article>
      </div>

      <div className="grilla en-vivo">
        <section className="tarjeta contenedor-mapa">
          <MapaEnVivo eventos={visibles} focos={focosVisibles} seleccionado={seleccionado} onSeleccionar={setSeleccionado} />
          <p className="nota">
            Tamaño y color = estado. Borde punteado = por confirmar. Atenuado = en observación. Puntos claros = focos individuales.
            Satélites: VIIRS (S-NPP, NOAA-20, NOAA-21) y MODIS (Terra, Aqua).
          </p>
        </section>

        <div className="columna">
          {seleccionado && <FichaEvento id={seleccionado} onCerrar={() => setSeleccionado(null)} />}
          <PanelAlertas eventos={datos.eventos} filtro={filtro} onFiltro={setFiltro}
            verObservacion={verObservacion} onVerObservacion={setVerObservacion}
            seleccionado={seleccionado} onSeleccionar={setSeleccionado} />
        </div>
      </div>
    </>
  )
}
