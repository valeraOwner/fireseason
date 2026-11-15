import 'leaflet/dist/leaflet.css'
import { useEffect, useMemo, useState } from 'react'
import { GeoJSON, MapContainer, Rectangle, TileLayer, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { NIVELES_RIESGO, fmt, nivelDe } from '../../constantes'

const CENTRO_PERU = [-9.2, -75.0]
const renderizador = L.canvas({ padding: 0.3 })   // miles de celdas: canvas es mucho más rápido que SVG

// Con el mouse sobre el mapa se busca la celda bajo el puntero (más liviano que un tooltip por celda)
function Puntero({ indice, tamano, onCelda }) {
  useMapEvents({
    mousemove: (e) => {
      const cx = Math.floor(e.latlng.lng / tamano)
      const cy = Math.floor(e.latlng.lat / tamano)
      onCelda(indice.get(`${cx},${cy}`) ?? null)
    },
    mouseout: () => onCelda(null),
  })
  return null
}

export default function MapaPrediccion({ datos }) {
  const [limites, setLimites] = useState(null)
  const [celda, setCelda] = useState(null)

  useEffect(() => {
    fetch('/api/regiones/geojson/departamentos').then((r) => r.json()).then(setLimites).catch(() => {})
  }, [])

  const t = datos?.tamano_celda ?? 0.1
  const celdas = useMemo(() => (datos?.celdas ?? []).map(([cx, cy, p, normal]) => ({ cx, cy, p, normal, nivel: nivelDe(p) })), [datos])
  const indice = useMemo(() => new Map(celdas.map((c) => [`${c.cx},${c.cy}`, c])), [celdas])

  return (
    <div className="mapa-prediccion">
      <MapContainer center={CENTRO_PERU} zoom={5} minZoom={4} className="mapa">
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
          attribution='Mapa base &copy; <a href="https://www.esri.com/">Esri</a>, HERE, Garmin, &copy; OpenStreetMap'
          maxNativeZoom={16}
        />
        {celdas.map((c) => c.nivel && (
          <Rectangle key={`${c.cx},${c.cy}`} renderer={renderizador} interactive={false}
            bounds={[[c.cy * t, c.cx * t], [(c.cy + 1) * t, (c.cx + 1) * t]]}
            pathOptions={{ stroke: false, fillColor: c.nivel.color, fillOpacity: 0.85 }} />
        ))}
        {limites && (
          <GeoJSON data={limites} interactive={false} style={{ color: '#a5a49e', weight: 0.8, fill: false, opacity: 0.55 }} />
        )}
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}"
          maxNativeZoom={16} zIndex={5}
        />
        <Puntero indice={indice} tamano={t} onCelda={setCelda} />
      </MapContainer>

      {/* Leyenda: rampa de un solo tono, de menos a más */}
      <div className="leyenda-mapa">
        <strong>Probabilidad de fuego en la semana</strong>
        {[...NIVELES_RIESGO].reverse().map((n) => (
          <span key={n.nombre}><i style={{ background: n.color }} />{n.nombre} <small>{n.detalle}</small></span>
        ))}
        <small>Celda ≈ 11 km. Sin color: menos de 3 %.</small>
      </div>

      {celda && (
        <div className="info-celda">
          <strong>{fmt(100 * celda.p)} %</strong> de probabilidad de fuego
          <br />Normal para esta semana: {fmt(100 * celda.normal)} %
          <br /><small>{(celda.cy * t).toFixed(1)}°, {(celda.cx * t).toFixed(1)}°</small>
        </div>
      )}
    </div>
  )
}
