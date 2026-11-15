// Valores compartidos por toda la interfaz.

export const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Set', 'Oct', 'Nov', 'Dic']
export const MESES_LARGOS = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
  'agosto', 'setiembre', 'octubre', 'noviembre', 'diciembre']

export const METRICAS = {
  dias_celda: {
    nombre: 'Días-celda con fuego',
    corto: 'días-celda',
    ayuda: 'Celdas de ~11 km que registraron fuego cada día. Es la medida armonizada recomendada.',
  },
  focos: {
    nombre: 'Focos de calor',
    corto: 'focos',
    ayuda: 'Número de focos equivalentes a VIIRS (375 m).',
  },
}

// Colores (tema oscuro). Las variables CSS equivalentes están en index.css.
export const COLOR = {
  superficie: '#1a1a19',
  texto: '#ecebe7',
  textoSecundario: '#a5a49e',
  textoTenue: '#77766f',
  grilla: '#2e2e2b',
  eje: '#4a4945',
  azul: '#3987e5',      // serie armonizada (categórico 1)
  naranja: '#d95926',   // destacado / temporada crítica (categórico 2)
  neutro: '#55534d',    // barras no destacadas
}

// Rampa secuencial de un solo tono (naranja) para el tema oscuro:
// poca actividad se funde con el fondo, mucha actividad brilla.
export const RAMPA_FUEGO = ['#2e2420', '#5a2c18', '#8a3816', '#c04d1f', '#e8703c', '#f6a57a', '#fcd3b8']

// Categorías de anomalía (del backend) -> paso de la rampa
export const CATEGORIAS = [
  { id: 'normal o menor', etiqueta: 'Normal o menor', color: RAMPA_FUEGO[0] },
  { id: 'levemente sobre la mediana', etiqueta: 'Levemente sobre la mediana', color: RAMPA_FUEGO[2] },
  { id: 'sobre lo normal', etiqueta: 'Sobre lo normal (> P75)', color: RAMPA_FUEGO[3] },
  { id: 'muy alto', etiqueta: 'Muy alto (> P90)', color: RAMPA_FUEGO[5] },
  { id: 'extremo', etiqueta: 'Extremo (> P95)', color: RAMPA_FUEGO[6] },
]

export const fmt = (n, dec = 0) =>
  n == null || Number.isNaN(n) ? '—' : Number(n).toLocaleString('es-PE', { maximumFractionDigits: dec })
