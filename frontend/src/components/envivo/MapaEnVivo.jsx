import 'leaflet/dist/leaflet.css'
import { useEffect, useState } from 'react'
import { CircleMarker, GeoJSON, MapContainer, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { ESTADOS, ORDEN_ESTADOS, hace } from '../../constantes'

const CENTRO_PERU = [-9.2, -75.0]
const RADIO_BASE = 6   // px; se multiplica por la escala del estado (1× / 1.6× / 2.3×)

// Cuando se elige un evento, el mapa se acerca a él
function Enfocar({ evento }) {
  const map = useMap()
  useEffect(() => {
    if (!evento) return
    const [o, s, e, n] = evento.limites
    const margen = 0.15
    map.flyToBounds([[s - margen, o - margen], [n + margen, e + margen]], { maxZoom: 11, duration: 0.8 })
  }, [evento?.id, map])   // solo al cambiar de evento, no en cada actualización de datos
  return null
}

export default function MapaEnVivo({ eventos, focos, seleccionado, onSeleccionar }) {
  const [limites, setLimites] = useState(null)

  // Límites de departamentos (solo como referencia, línea tenue)
  useEffect(() => {
    fetch('/api/regiones/geojson/departamentos').then((r) => r.json()).then(setLimites).catch(() => {})
  }, [])

  // Los más graves se dibujan al final para que queden encima
  const ordenados = [...eventos].sort(
    (a, b) => ORDEN_ESTADOS.indexOf(b.estado) - ORDEN_ESTADOS.indexOf(a.estado) || a.puntaje - b.puntaje,
  )

  return (
    <MapContainer center={CENTRO_PERU} zoom={5} minZoom={4} className="mapa" preferCanvas={false}>
      {/* Mapa base oscuro de Esri (no pide clave; CARTO ahora la exige y mostraba "API KEY REQUIRED") */}
      <TileLayer
        url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        attribution='Mapa base &copy; <a href="https://www.esri.com/">Esri</a>, HERE, Garmin, &copy; OpenStreetMap'
        maxNativeZoom={16}
      />
      {limites && (
        <GeoJSON data={limites} interactive={false}
          style={{ color: '#8a8880', weight: 0.8, fill: false, opacity: 0.6 }} />
      )}
      {/* Nombres de ciudades y países (capa transparente sobre el mapa base, debajo de los incendios) */}
      <TileLayer
        url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
        maxNativeZoom={16} zIndex={5}
      />

      {/* Cada foco detectado: punto pequeño */}
      {focos.map((f, i) => (
        <CircleMarker key={i} center={[f.lat, f.lon]} radius={2} interactive={false}
          pathOptions={{ stroke: false, fillColor: '#fcd3b8', fillOpacity: 0.55 }} />
      ))}

      {/* Cada evento: círculo con tamaño y color según su estado */}
      {ordenados.map((ev) => {
        const est = ESTADOS[ev.estado]
        const activo = seleccionado === ev.id
        return (
          <CircleMarker key={ev.id} center={[ev.lat, ev.lon]}
            radius={RADIO_BASE * est.escala}
            className={ev.estado === 'critico' && !ev.en_observacion ? 'pulso' : ''}
            eventHandlers={{ click: () => onSeleccionar(ev.id) }}
            pathOptions={{
              color: activo ? '#ffffff' : est.color,
              weight: activo ? 3 : 1.5,
              fillColor: est.color,
              fillOpacity: ev.en_observacion ? 0.25 : 0.7,   // en observación: atenuado
              dashArray: ev.por_confirmar ? '3 3' : null,     // por confirmar: borde punteado
            }}>
            <Tooltip direction="top" offset={[0, -6]}>
              <strong>{est.icono} {est.nombre}</strong> · {ev.puntaje} pts<br />
              {ev.provincia ? `${ev.provincia}, ${ev.departamento}` : 'Fuera del Perú'}<br />
              {ev.focos_24h} focos en 24 h · último {hace(ev.ultima_deteccion)}
              {ev.en_observacion && <><br />En observación</>}
            </Tooltip>
          </CircleMarker>
        )
      })}

      <Enfocar evento={eventos.find((e) => e.id === seleccionado)} />
    </MapContainer>
  )
}
