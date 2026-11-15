import { useEffect, useMemo, useState } from 'react'
import Descarga from '../components/Descarga'
import Filtros from '../components/Filtros'
import Indicadores from '../components/Indicadores'
import Ranking from '../components/Ranking'
import CalendarioFuego from '../components/graficos/CalendarioFuego'
import Climatologia from '../components/graficos/Climatologia'
import SerieAnual from '../components/graficos/SerieAnual'
import { METRICAS } from '../constantes'
import { api } from '../services/api'

const ANIO_MAX = 2025    // último año completo en los datos (se confirma con el backend al cargar)

export default function Historico() {
  const [regiones, setRegiones] = useState([])
  const [filtros, setFiltros] = useState({ region: 'peru', desde: 2003, hasta: ANIO_MAX, metrica: 'dias_celda' })
  const [modo, setModo] = useState('actividad')
  const [anioElegido, setAnioComparado] = useState(ANIO_MAX)
  const [datos, setDatos] = useState(null)
  const [cargando, setCargando] = useState(true)
  const [error, setError] = useState(null)

  const cambiar = (cambios) => setFiltros((f) => ({ ...f, ...cambios }))

  // Lista de regiones (una sola vez)
  useEffect(() => {
    api.regiones().then(setRegiones).catch((e) => setError(e.message))
  }, [])

  // Datos de la región/periodo elegidos
  useEffect(() => {
    const { region, desde, hasta, metrica } = filtros
    const esPais = region === 'peru'
    const departamento = esPais ? undefined : region.split('__')[0]
    let vigente = true
    setCargando(true)
    Promise.all([
      api.calendario(region, desde, hasta, metrica),
      api.climatologia(region),
      api.serieAnual(region, desde, hasta, metrica),
      api.anomalia(region),
      api.ranking(esPais ? 'departamento' : 'provincia', desde, hasta, metrica, departamento),
    ])
      .then(([calendario, clima, serie, anomalia, ranking]) => {
        if (!vigente) return
        setDatos({ calendario, clima, serie, anomalia, ranking })
        setError(null)
      })
      .catch((e) => vigente && setError(e.message))
      .finally(() => vigente && setCargando(false))
    return () => { vigente = false }   // si el usuario cambia rápido, ignorar respuestas viejas
  }, [filtros])

  // El año comparado siempre dentro del rango elegido
  const anioComparado = Math.min(Math.max(anioElegido, filtros.desde), filtros.hasta)

  const valoresAnio = useMemo(
    () => datos?.calendario.celdas.filter((c) => c.anio === anioComparado) ?? [],
    [datos, anioComparado],
  )

  const nombreRegion = datos?.calendario.region.nombre ?? 'Perú'
  const tituloRanking = filtros.region === 'peru' ? 'Departamentos con más fuego' : 'Provincias con más fuego'

  if (error && !datos) {
    return (
      <div className="tarjeta aviso">
        <h2>No se pudo conectar con el backend</h2>
        <p>{error}</p>
        <p>Revisa que esté corriendo: en otra terminal, <code>cd backend</code> y <code>uvicorn app.main:app --reload</code>.</p>
      </div>
    )
  }

  return (
    <>
      <Filtros regiones={regiones} filtros={filtros} onCambiar={cambiar} anioMax={ANIO_MAX} />

      <h2 className="titulo-region">
        {nombreRegion}
        <span>{filtros.desde}–{filtros.hasta} · {METRICAS[filtros.metrica].nombre.toLowerCase()}</span>
        {cargando && <span className="cargando">actualizando…</span>}
      </h2>

      {datos && (
        <div className={`contenido ${cargando ? 'atenuado' : ''}`}>
          <Indicadores anomalia={datos.anomalia} clima={datos.clima} serieAnual={datos.serie.anios} />

          <div className="grilla">
            <section className="tarjeta calendario">
              <header>
                <div>
                  <h3>Calendario de fuego</h3>
                  <p>{modo === 'actividad'
                    ? 'Cantidad de fuego por mes. Clic en una celda para compararla con lo normal.'
                    : 'Cada mes comparado con su propia historia (mediana y percentiles 2003–hoy).'}</p>
                </div>
                <div className="segmentado compacto" role="radiogroup" aria-label="Color del calendario">
                  <div>
                    <button role="radio" aria-checked={modo === 'actividad'} className={modo === 'actividad' ? 'activo' : ''}
                      onClick={() => setModo('actividad')}>Actividad</button>
                    <button role="radio" aria-checked={modo === 'anomalia'} className={modo === 'anomalia' ? 'activo' : ''}
                      onClick={() => setModo('anomalia')}>Anomalía</button>
                  </div>
                </div>
              </header>
              <CalendarioFuego celdas={datos.calendario.celdas} metrica={filtros.metrica} modo={modo}
                onSeleccionar={(c) => setAnioComparado(c.anio)} />
              <p className="nota">* 2001–2002: solo satélite Terra, calidad baja. 2003–2011: MODIS calibrado a escala VIIRS.
                Desde 2012: VIIRS observado.</p>
            </section>

            <div className="columna">
              <section className="tarjeta">
                <header>
                  <div>
                    <h3>Temporada crítica</h3>
                    <p>Mediana de cada mes (naranja = meses críticos) frente al año
                      <select className="en-linea" value={anioComparado} onChange={(e) => setAnioComparado(Number(e.target.value))}>
                        {Array.from({ length: filtros.hasta - filtros.desde + 1 }, (_, i) => filtros.hasta - i)
                          .map((a) => <option key={a} value={a}>{a}</option>)}
                      </select>
                    </p>
                  </div>
                </header>
                <Climatologia clima={datos.clima} anio={anioComparado} valoresAnio={valoresAnio} />
              </section>

              <section className="tarjeta">
                <header>
                  <div>
                    <h3>{tituloRanking}</h3>
                    <p>Promedio anual {filtros.desde}–{filtros.hasta}. Clic para explorar.</p>
                  </div>
                </header>
                <Ranking datos={datos.ranking} seleccionada={filtros.region} onSeleccionar={(id) => cambiar({ region: id })} />
              </section>
            </div>
          </div>

          <section className="tarjeta">
            <header>
              <div>
                <h3>Actividad por año</h3>
                <p>Serie armonizada. La banda muestra el margen de error de la calibración MODIS → VIIRS.</p>
              </div>
            </header>
            <SerieAnual anios={datos.serie.anios} metrica={filtros.metrica} />
          </section>

          <section className="tarjeta">
            <header><div><h3>Descargar datos</h3></div></header>
            <Descarga region={filtros.region} nombreRegion={nombreRegion} anioMax={ANIO_MAX} />
          </section>
        </div>
      )}
    </>
  )
}
