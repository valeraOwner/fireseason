import Historico from './pages/Historico'

export default function App() {
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
          <a className="activo" href="#">Histórico</a>
          <a className="pronto" title="Próximamente">En vivo</a>
          <a className="pronto" title="Próximamente">Predicción</a>
          <a className="pronto" title="Próximamente">Metodología</a>
        </nav>
      </header>
      <main>
        <Historico />
      </main>
      <footer className="pie">
        Datos: NASA FIRMS (MODIS C6.1, VIIRS 375 m) · Límites: IGN Perú vía geoBoundaries ·
        Herramienta de apoyo, no reemplaza alertas oficiales.
      </footer>
    </div>
  )
}
