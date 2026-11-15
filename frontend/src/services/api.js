// Funciones para hablar con el backend FastAPI.
// Vite reenvía /api a http://127.0.0.1:8000 (ver vite.config.js).

async function pedir(ruta, params = {}) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ''),
  )
  const url = `/api${ruta}${query.size ? `?${query}` : ''}`
  const respuesta = await fetch(url)
  if (!respuesta.ok) {
    const cuerpo = await respuesta.json().catch(() => ({}))
    throw new Error(typeof cuerpo.detail === 'string' ? cuerpo.detail : `Error ${respuesta.status} en ${url}`)
  }
  return respuesta.json()
}

export const api = {
  regiones: (nivel) => pedir('/regiones', { nivel }),
  calendario: (region, desde, hasta, metrica) => pedir('/historico/calendario', { region, desde, hasta, metrica }),
  climatologia: (region) => pedir('/historico/climatologia', { region }),
  serieAnual: (region, desde, hasta, metrica) => pedir('/historico/serie-anual', { region, desde, hasta, metrica }),
  anomalia: (region, anio, mes) => pedir('/historico/anomalia', { region, anio, mes }),
  enVivo: (actualizar) => pedir('/en-vivo', { actualizar: actualizar || undefined }),
  evento: (id) => pedir(`/en-vivo/eventos/${id}`),
  ranking: (nivel, desde, hasta, metrica, departamento) =>
    pedir('/historico/ranking', { nivel, desde, hasta, metrica, departamento }),
}

export const urlDescargaCSV = (region, desde, hasta) =>
  `/api/descargar/focos.csv?${new URLSearchParams({ region, desde, hasta })}`
