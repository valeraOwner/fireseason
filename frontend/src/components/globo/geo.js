import { Vector3 } from 'three'

// Latitud/longitud (grados) -> punto 3D sobre una esfera de radio r.
// Coincide con cómo Three.js pega una imagen equirectangular en SphereGeometry
// (longitud 0 en +X, 90° O en +Z, norte en +Y).
export function aVector(lat, lon, r = 1) {
  const la = (lat * Math.PI) / 180
  const lo = (lon * Math.PI) / 180
  return new Vector3(r * Math.cos(la) * Math.cos(lo), r * Math.sin(la), -r * Math.cos(la) * Math.sin(lo))
}

// GeoJSON (Polygon / MultiPolygon) -> lista plana de coordenadas xyz para LineSegments
export function lineasDeGeojson(geojson, r = 1.0015) {
  const xyz = []
  const anillo = (coords) => {
    for (let i = 0; i < coords.length - 1; i++) {
      const a = aVector(coords[i][1], coords[i][0], r)
      const b = aVector(coords[i + 1][1], coords[i + 1][0], r)
      xyz.push(a.x, a.y, a.z, b.x, b.y, b.z)
    }
  }
  for (const f of geojson.features) {
    const g = f.geometry
    if (!g) continue
    const poligonos = g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : []
    poligonos.forEach((p) => p.forEach(anillo))
  }
  return new Float32Array(xyz)
}
