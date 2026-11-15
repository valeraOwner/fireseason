import { lazy, Suspense, useState } from 'react'
import EnVivo from './pages/EnVivo'
import Historico from './pages/Historico'
import Prediccion from './pages/Prediccion'

// Three.js pesa ~1 MB: el globo se descarga solo cuando se abre su pestaña
const Globo = lazy(() => import('./pages/Globo'))

const PAGINAS = {
  historico: { nombre: 'Histórico', componente: Historico },
  'en-vivo': { nombre: 'En vivo', componente: EnVivo },
  globo: { nombre: 'Globo 3D', componente: Globo },
  prediccion: { nombre: 'Predicción', componente: Prediccion },
}
const PRONTO = ['Metodología']

// La página activa se guarda en la URL (#en-vivo) para poder compartir el enlace
const paginaDeUrl = () => (PAGINAS[location.hash.slice(1)] ? location.hash.slice(1) : 'historico')

export default function App() {
  const [pagina, setPagina] = useState(paginaDeUrl)
  const Pagina = PAGINAS[pagina].componente

  const ir = (id) => {
    history.replaceState(null, '', `#${id}`)
    setPagina(id)
  }

  return (
    <div className="app">
      <header className="cabecera">
        <div className="marca">
          <span className="logo" aria-hidden="true">🔥</span>
          <div>
            <h1>FireSeason</h1>
            <p>Calendario de fuego armonizado MODIS + VIIRS · NASA FIRMS</p>
          </div>
        </div>
        <nav>
          {Object.entries(PAGINAS).map(([id, p]) => (
            <a key={id} href={`#${id}`} className={pagina === id ? 'activo' : ''}
              aria-current={pagina === id ? 'page' : undefined}
              onClick={(e) => { e.preventDefault(); ir(id) }}>
              {id === 'en-vivo' && <span className="punto-vivo" aria-hidden="true" />}{p.nombre}
            </a>
          ))}
          {PRONTO.map((n) => <a key={n} className="pronto" title="Próximamente">{n}</a>)}
        </nav>
      </header>
      <main>
        <Suspense fallback={<p className="vacio">Cargando…</p>}>
          <Pagina />
        </Suspense>
      </main>
      <footer className="pie">
        Datos: NASA FIRMS (MODIS C6.1, VIIRS 375 m) · Límites: IGN Perú vía geoBoundaries ·
        Herramienta de apoyo, no reemplaza alertas oficiales.
      </footer>
    </div>
  )
}
