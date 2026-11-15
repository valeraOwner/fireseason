import { useState } from 'react'
import { urlDescargaCSV } from '../services/api'

// Descarga de los focos de la región elegida, en un rango de fechas.
export default function Descarga({ region, nombreRegion, anioMax }) {
  const [desde, setDesde] = useState(`${anioMax}-08-01`)
  const [hasta, setHasta] = useState(`${anioMax}-10-31`)
  const valido = desde && hasta && desde <= hasta

  return (
    <div className="descarga">
      <p>Focos de calor de <b>{nombreRegion}</b> (MODIS + VIIRS, solo vegetación), con fecha, hora,
        coordenadas, sensor, confianza e intensidad (FRP).</p>
      <div className="fila">
        <label><span>Desde</span>
          <input type="date" value={desde} min="2001-01-01" max={`${anioMax}-12-31`} onChange={(e) => setDesde(e.target.value)} />
        </label>
        <label><span>Hasta</span>
          <input type="date" value={hasta} min="2001-01-01" max={`${anioMax}-12-31`} onChange={(e) => setHasta(e.target.value)} />
        </label>
        <a className={`boton ${valido ? '' : 'deshabilitado'}`} href={valido ? urlDescargaCSV(region, desde, hasta) : undefined}
          aria-disabled={!valido}>
          Descargar CSV
        </a>
      </div>
    </div>
  )
}
