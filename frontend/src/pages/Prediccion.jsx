import { useEffect, useState } from 'react'
import MapaPrediccion from '../components/prediccion/MapaPrediccion'
import SemanasPrediccion from '../components/prediccion/SemanasPrediccion'
import { fmt, rangoFechas } from '../constantes'
import { api } from '../services/api'

const VELOCIDAD_MS = 1300     // reproducción automática: una semana cada 1.3 s

export default function Prediccion() {
  const [h, setH] = useState(1)
  const [region, setRegion] = useState('peru')
  const [regiones, setRegiones] = useState([])
  const [semanas, setSemanas] = useState(null)
  const [celdas, setCeldas] = useState(null)
  const [ranking, setRanking] = useState(null)
  const [modelo, setModelo] = useState(null)
  const [reproduciendo, setReproduciendo] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    api.regiones().then((r) => setRegiones(r.filter((x) => x.nivel !== 'provincia'))).catch(() => {})
    api.predModelo().then(setModelo).catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    let vigente = true
    api.predSemanas(region).then((d) => vigente && setSemanas(d)).catch((e) => vigente && setError(e.message))
    return () => { vigente = false }
  }, [region])

  useEffect(() => {
    let vigente = true
    api.predCeldas(h, region).then((d) => vigente && setCeldas(d)).catch((e) => vigente && setError(e.message))
    api.predRanking(h, 'provincia', 10).then((d) => vigente && setRanking(d)).catch(() => {})
    return () => { vigente = false }
  }, [h, region])

  // Reproducir: avanza la barra de tiempo sola y vuelve a empezar al llegar a +12
  useEffect(() => {
    if (!reproduciendo) return
    const reloj = setInterval(() => setH((x) => (x % 12) + 1), VELOCIDAD_MS)
    return () => clearInterval(reloj)
  }, [reproduciendo])

  if (error && !semanas) {
    return (
      <div className="tarjeta aviso">
        <h2>No se pudo cargar la predicción</h2>
        <p>{error}</p>
      </div>
    )
  }
  if (!semanas) return <p className="vacio">Cargando predicción…</p>

  const s = semanas.semanas[h - 1]
  const cambio = s.normal > 0 ? Math.round(100 * (s.esperado / s.normal - 1)) : null
  const nombreRegion = region === 'peru' ? 'Perú' : regiones.find((r) => r.id === region)?.nombre ?? region
  const ultimo = modelo?.por_horizonte?.[0]

  return (
    <>
      <h2 className="titulo-region">
        Predicción de riesgo
        <span>Próximas 12 semanas · riesgo estacional esperado, no certeza</span>
      </h2>

      {/* Barra de tiempo */}
      <section className="tarjeta barra-tiempo">
        <button className="boton reproducir" onClick={() => setReproduciendo((x) => !x)}
          aria-label={reproduciendo ? 'Pausar' : 'Reproducir las 12 semanas'}>
          {reproduciendo ? '❚❚' : '▶'}
        </button>
        <div className="deslizador">
          <label htmlFor="semana">
            <strong>Semana +{h}</strong> · {rangoFechas(s.inicio, s.fin)} {s.anio}
          </label>
          <input id="semana" type="range" min="1" max="12" value={h}
            onChange={(e) => { setReproduciendo(false); setH(Number(e.target.value)) }} />
          <div className="marcas" aria-hidden="true">
            {semanas.semanas.map((x) => <span key={x.h}>{rangoFechas(x.inicio, x.inicio).split(' – ')[0]}</span>)}
          </div>
        </div>
        <label className="selector-region">
          <span>Región</span>
          <select value={region} onChange={(e) => setRegion(e.target.value)}>
            <option value="peru">Perú</option>
            {regiones.filter((r) => r.nivel === 'departamento').map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>)}
          </select>
        </label>
      </section>

      <div className="indicadores">
        <article className="tarjeta indicador">
          <h3>Celdas con fuego esperadas</h3>
          <p className="cifra">{fmt(s.esperado)}</p>
          <p className="detalle">{nombreRegion}, semana +{h}</p>
        </article>
        <article className="tarjeta indicador">
          <h3>Frente a lo normal</h3>
          <p className="cifra">{cambio == null ? '—' : `${cambio > 0 ? '+' : ''}${cambio} %`}</p>
          <p className="detalle">Normal: {fmt(s.normal)} (promedio 2013–2025)</p>
        </article>
        <article className="tarjeta indicador">
          <h3>Celdas en riesgo alto o muy alto</h3>
          <p className="cifra">{fmt(s.celdas_alto_riesgo)}</p>
          <p className="detalle">35 % o más de probabilidad</p>
        </article>
        <article className="tarjeta indicador">
          <h3>Qué tan bien predice</h3>
          <p className="cifra">{modelo ? `AUC ${fmt(modelo.auc_climatologia, 2)}` : '—'}</p>
          <p className="detalle">Probado en {modelo?.anios_prueba.join('–')}, años que no vio</p>
        </article>
      </div>

      <div className="grilla en-vivo">
        <section className="tarjeta contenedor-mapa">
          <MapaPrediccion datos={celdas} />
        </section>

        <div className="columna">
          <section className="tarjeta">
            <header>
              <div>
                <h3>Próximas 12 semanas · {nombreRegion}</h3>
                <p>Clic en una barra para verla en el mapa.</p>
              </div>
            </header>
            <SemanasPrediccion semanas={semanas.semanas} h={h} onElegir={(x) => { setReproduciendo(false); setH(x) }} />
          </section>

          <section className="tarjeta">
            <header>
              <div>
                <h3>Provincias con más riesgo · semana +{h}</h3>
                <p>Perú completo. Cambio frente a lo normal por la actividad de estos días.</p>
              </div>
            </header>
            <ol className="ranking-pred">
              {ranking?.regiones.map((r, i) => (
                <li key={r.id}>
                  <span className="puesto">{i + 1}</span>
                  <span className="nombre">{r.nombre} <small>{r.departamento}</small></span>
                  <span className="valor">{fmt(r.esperado, 1)}</span>
                  <span className={`cambio ${r.cambio_pct > 5 ? 'sube' : r.cambio_pct < -5 ? 'baja' : ''}`}>
                    {r.cambio_pct == null ? '' : `${r.cambio_pct > 0 ? '▲ +' : r.cambio_pct < 0 ? '▼ ' : ''}${fmt(r.cambio_pct)} %`}
                  </span>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>

      <section className="tarjeta metodo-pred">
        <h3>Cómo se calcula</h3>
        <p>
          Para cada celda de ~11 km y cada semana del año, el modelo cuenta en qué fracción de los años
          {' '}{modelo?.anios_climatologia.join('–')} hubo al menos un foco VIIRS (climatología). Luego la ajusta
          levemente según cuánto fuego tuvo la provincia en los últimos 7 días, frente a lo normal.
        </p>
        {ultimo && (
          <p>
            <strong>Validación honesta</strong> en {modelo.anios_prueba.join('–')} (años que el modelo no usó):
            la climatología mejora en <strong>{fmt(ultimo.skill_climatologia_pct, 1)} %</strong> el puntaje de Brier
            frente a adivinar con una probabilidad fija, y separa bien las celdas que arden de las que no
            (AUC {fmt(modelo.auc_climatologia, 2)}). El ajuste por los últimos 7 días aporta poco
            ({ultimo.mejora_ajuste_pct > 0 ? '+' : ''}{fmt(ultimo.mejora_ajuste_pct, 1)} % en la semana +1):
            el fuego en el Perú es sobre todo <strong>estacional</strong>.
          </p>
        )}
        <p className="nota">{semanas.ajuste} {semanas.aviso}</p>
      </section>
    </>
  )
}
