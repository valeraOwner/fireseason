import { useEffect, useState } from 'react'
import GraficoValidacion from '../components/metodologia/GraficoValidacion'
import { fmt } from '../constantes'
import { api } from '../services/api'

const PASOS = [
  { titulo: 'Una misma cuadrícula', texto: 'Cada foco se ubica en una celda de ~11 km y se cuentan los días con fuego en cada celda. Así los dos sensores se miden con la misma regla.' },
  { titulo: 'Un factor de conversión', texto: 'Entre 2012 y 2021 funcionan ambos sensores. Comparándolos se calcula cuánto VIIRS equivale a 1 de MODIS, mes por mes.' },
  { titulo: 'Una sola serie', texto: 'Desde 2012 se usa VIIRS; antes, MODIS convertido con ese factor. Resultado: una serie comparable de 2001 a hoy.' },
]

const MODULOS = [
  ['Histórico', 'Calendario de fuego, temporada crítica y anomalías por departamento y provincia.'],
  ['En vivo', 'Incendios de las últimas 72 h con estado Prevención, Alto o Crítico según tamaño, anomalía, cercanía a poblados y áreas protegidas.'],
  ['Globo 3D', 'Los mismos incendios en vivo, como llamas sobre la Tierra.'],
  ['Predicción', 'Riesgo esperado de las próximas 12 semanas a partir de 13 años de datos.'],
]

const FUENTES = [
  ['NASA FIRMS', 'Focos MODIS y VIIRS (histórico y en vivo)', 'https://firms.modaps.eosdis.nasa.gov/'],
  ['NASA GIBS', 'Imagen Blue Marble del globo', 'https://gibs.earthdata.nasa.gov/'],
  ['SERNANP', 'Áreas naturales protegidas', 'https://www.gob.pe/sernanp'],
  ['GeoNames', 'Centros poblados', 'https://www.geonames.org/'],
]

const LIMITACIONES = [
  'Cuenta días con fuego, no hectáreas quemadas.',
  '2001–2002 tienen menos precisión: solo había un satélite MODIS.',
  'Los datos en vivo son preliminares y no ven fuego bajo nubes o humo.',
  'Es una herramienta de apoyo: no reemplaza las alertas oficiales de SERFOR, SERNANP o INDECI.',
]

export default function Metodologia() {
  const [factores, setFactores] = useState(null)
  const [validacion, setValidacion] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.metodologiaFactores().then(setFactores).catch((e) => setError(e.message))
    api.metodologiaValidacion().then(setValidacion).catch((e) => setError(e.message))
  }, [])

  if (error && !factores) {
    return <div className="tarjeta aviso"><h2>No se pudo cargar la metodología</h2><p>{error}</p></div>
  }

  const modis = (factores ?? []).filter((x) => x.base === 'MODIS' && x.metrica === 'dias_celda')
  const factorMedio = modis.length ? modis.reduce((s, x) => s + x.factor, 0) / modis.length : null
  const resumen = validacion?.nacional_resumen?.find((x) => x.metrica === 'dias_celda')

  return (
    <div className="metodologia">
      <h2 className="titulo-region">
        Metodología
        <span>Cómo unimos los datos de dos satélites de la NASA</span>
      </h2>

      <div className="indicadores tres">
        <article className="tarjeta indicador">
          <h3>Focos analizados</h3>
          <p className="cifra">1.87 M</p>
          <p className="detalle">Perú, 2001–2025</p>
        </article>
        <article className="tarjeta indicador">
          <h3>VIIRS ve más que MODIS</h3>
          <p className="cifra">{factorMedio ? `${fmt(factorMedio, 1)}×` : '—'}</p>
          <p className="detalle">días con fuego, en promedio</p>
        </article>
        <article className="tarjeta indicador">
          <h3>Error de la armonización</h3>
          <p className="cifra">{resumen ? `${fmt(resumen.error_abs_medio_pct, 1)} %` : '—'}</p>
          <p className="detalle">al reconstruir VIIRS a partir de MODIS</p>
        </article>
      </div>

      <section className="tarjeta bloque">
        <h3>El problema</h3>
        <p>
          MODIS observa incendios desde 2001 y VIIRS desde 2012, pero VIIRS tiene mejor resolución y detecta muchos
          más fuegos pequeños. Si se juntan tal cual, parece que el fuego se multiplicó en 2012, cuando solo llegó un sensor más fino.
        </p>
        <div className="sensores">
          <div>
            <h4>MODIS</h4>
            <ul><li>Píxel de 1 km</li><li>Datos desde 2001</li></ul>
          </div>
          <div>
            <h4>VIIRS</h4>
            <ul><li>Píxel de 375 m</li><li>Datos desde 2012</li></ul>
          </div>
        </div>
      </section>

      <section className="tarjeta bloque">
        <h3>Cómo lo resolvimos</h3>
        <ol className="pasos">
          {PASOS.map((p, i) => (
            <li key={p.titulo}>
              <span className="numero">{i + 1}</span>
              <div><strong>{p.titulo}</strong><p>{p.texto}</p></div>
            </li>
          ))}
        </ol>
      </section>

      <section className="tarjeta">
        <header><div>
          <h3>¿Funciona?</h3>
          <p>Para cada año se calculó el factor sin usar ese año y se comparó MODIS convertido con lo que VIIRS realmente vio.
            Las dos curvas casi coinciden.</p>
        </div></header>
        <GraficoValidacion anios={validacion?.nacional_por_anio} />
      </section>

      <section className="tarjeta bloque">
        <h3>Qué ofrece FireSeason</h3>
        <ul className="modulos">
          {MODULOS.map(([n, t]) => <li key={n}><strong>{n}</strong><span>{t}</span></li>)}
        </ul>
      </section>

      <div className="grilla mitades">
        <section className="tarjeta bloque">
          <h3>Fuentes de datos</h3>
          <ul className="fuentes">
            {FUENTES.map(([n, u, url]) => (
              <li key={n}><a href={url} target="_blank" rel="noreferrer">{n}</a><span>{u}</span></li>
            ))}
          </ul>
        </section>
        <section className="tarjeta bloque">
          <h3>Limitaciones</h3>
          <ul className="lista">{LIMITACIONES.map((l) => <li key={l}>{l}</li>)}</ul>
        </section>
      </div>
    </div>
  )
}
