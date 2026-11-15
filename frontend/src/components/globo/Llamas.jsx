import { useFrame } from '@react-three/fiber'
import { useLayoutEffect, useMemo, useRef } from 'react'
import { CanvasTexture, DoubleSide, InstancedBufferAttribute, LinearFilter, Object3D, PlaneGeometry, SRGBColorSpace } from 'three'
import { ESTADOS, ORDEN_ESTADOS } from '../../constantes'
import { aVector } from './geo'

/*
  Llamas sobre el globo, una por evento: un ícono plano animado "como un GIF" (4 cuadros).
  Según docs/POLITICA_ESTADOS.md:
    Prevención  amarillo  1×    animación lenta
    Alto        naranja   1.6×  animación media
    Crítico     rojo      2.3×  animación rápida + pulso de tamaño
    En observación: mismo color al 50 %, quieta

  Los íconos se dibujan una sola vez en un <canvas> (3 estados × 4 cuadros) y la tarjeta de video
  elige el cuadro según el tiempo. Se usa "InstancedMesh": todas las llamas en una sola pasada.
*/

const CUADROS = 4
const FILAS = ['prevencion', 'alto', 'critico']           // fila del atlas para cada estado
const CELDA_W = 64
const CELDA_H = 96
const TAMANO_PANTALLA = 0.03    // alto de una llama 1× ≈ 3 % de la distancia a la cámara (tamaño fijo en pantalla)
const CUADROS_POR_SEG = { prevencion: 4, alto: 6, critico: 9 }

// Variación de cada cuadro: inclinación de la punta y alto
const VARIACION = [[-0.1, 1], [0.04, 0.93], [0.12, 1.03], [-0.02, 0.96]]

// Silueta de llama con una "lengua" a la izquierda. (cx, base) = centro de la base; i = inclinación de la punta.
function dibujarLlama(ctx, cx, base, ancho, alto, i, lengua = true) {
  const P = (x, y) => [cx + x * ancho, base + y * alto]
  const curva = (...pts) => ctx.bezierCurveTo(...pts.flatMap(([x, y]) => P(x, y)))
  ctx.beginPath()
  ctx.moveTo(...P(i, -1))
  curva([0.1 + i * 0.3, -0.78], [0.52, -0.58], [0.48, -0.28])        // lado derecho
  curva([0.46, 0.02], [-0.46, 0.02], [-0.48, -0.28])                  // base redonda
  if (lengua) {
    curva([-0.5, -0.46], [-0.42, -0.58], [-0.34 - i * 0.4, -0.74])    // lengua izquierda
    curva([-0.2, -0.6], [-0.12, -0.56], [-0.06, -0.6])
    curva([-0.02, -0.78], [i * 0.5, -0.88], [i, -1])                  // de vuelta a la punta
  } else {
    curva([-0.52, -0.58], [-0.1 + i * 0.3, -0.78], [i, -1])
  }
  ctx.closePath()
}

// Atlas: filas = estados, columnas = cuadros de la animación
function crearAtlas() {
  const canvas = document.createElement('canvas')
  canvas.width = CELDA_W * CUADROS
  canvas.height = CELDA_H * FILAS.length
  const ctx = canvas.getContext('2d')
  FILAS.forEach((estado, fila) => {
    VARIACION.forEach(([incl, alto], c) => {
      const cx = c * CELDA_W + CELDA_W / 2
      const base = fila * CELDA_H + CELDA_H - 8
      // Cuerpo de la llama con borde oscuro (se lee bien sobre selva, sierra o mar)
      dibujarLlama(ctx, cx, base, 44, 80 * alto, incl)
      ctx.fillStyle = ESTADOS[estado].color
      ctx.fill()
      ctx.lineWidth = 3
      ctx.strokeStyle = 'rgba(20, 12, 8, 0.75)'
      ctx.stroke()
      // Centro claro
      dibujarLlama(ctx, cx, base - 3, 22, 40 * alto, -incl * 0.6, false)
      ctx.fillStyle = '#fff1b8'
      ctx.fill()
    })
  })
  const textura = new CanvasTexture(canvas)
  textura.colorSpace = SRGBColorSpace
  textura.generateMipmaps = false          // sin mipmaps: evita que se mezclen cuadros vecinos
  textura.minFilter = LinearFilter
  return textura
}

const vertex = /* glsl */ `
  attribute float aFila, aEscala, aFase, aVelocidad, aAlfa, aPulso;
  uniform float uTiempo, uTamano;
  varying vec2 vUv;
  varying float vFila, vCuadro, vAlfa;

  void main() {
    vUv = uv;
    vFila = aFila;
    vAlfa = aAlfa;
    vCuadro = mod(floor(uTiempo * aVelocidad + aFase), ${CUADROS}.0);   // salta de cuadro como un GIF

    vec4 base = modelViewMatrix * instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0);
    vec4 centro = modelViewMatrix * vec4(0.0, 0.0, 0.0, 1.0);
    float pulso = 1.0 + aPulso * 0.15 * step(0.0, sin(uTiempo * 6.0));      // crítico: late
    float tam = -base.z * uTamano * aEscala * pulso;                         // tamaño fijo en pantalla

    // La llama apunta "hacia afuera" del globo tal como se ve en pantalla
    vec2 radial = (base - centro).xy;
    float largo = length(radial);
    vec2 arriba = normalize(mix(vec2(0.0, 1.0), radial / max(largo, 1e-5), smoothstep(0.05, 0.35, largo)));
    vec2 derecha = vec2(arriba.y, -arriba.x);
    vec2 d = (derecha * position.x + arriba * position.y) * tam;

    gl_Position = projectionMatrix * vec4(base.xy + d, base.z + 0.002, 1.0);
  }
`

const fragment = /* glsl */ `
  uniform sampler2D uAtlas;
  varying vec2 vUv;
  varying float vFila, vCuadro, vAlfa;
  void main() {
    vec2 uv = vec2((vCuadro + vUv.x) / ${CUADROS}.0, (${FILAS.length - 1}.0 - vFila + vUv.y) / ${FILAS.length}.0);
    vec4 c = texture2D(uAtlas, uv);
    if (c.a < 0.1) discard;
    gl_FragColor = vec4(c.rgb, c.a * vAlfa);
  }
`

const geoLlama = new PlaneGeometry(CELDA_W / CELDA_H, 1).translate(0, 0.5, 0)   // la base de la llama en el punto

export default function Llamas({ eventos }) {
  const malla = useRef()
  const atlas = useMemo(crearAtlas, [])
  const uniforms = useMemo(() => ({ uTiempo: { value: 0 }, uTamano: { value: TAMANO_PANTALLA }, uAtlas: { value: atlas } }), [atlas])

  // Los más graves al final, para que se dibujen encima
  const ordenados = useMemo(
    () => [...eventos].sort((a, b) => ORDEN_ESTADOS.indexOf(b.estado) - ORDEN_ESTADOS.indexOf(a.estado)),
    [eventos],
  )
  const n = ordenados.length
  // eslint-disable-next-line react-hooks/exhaustive-deps -- a propósito: una geometría nueva cuando cambia n
  const geometria = useMemo(() => geoLlama.clone(), [n])

  useLayoutEffect(() => {
    if (!n || !malla.current) return
    const o = new Object3D()
    const fila = new Float32Array(n)
    const escala = new Float32Array(n)
    const fase = new Float32Array(n)
    const velocidad = new Float32Array(n)
    const alfa = new Float32Array(n)
    const pulso = new Float32Array(n)
    ordenados.forEach((ev, i) => {
      o.position.copy(aVector(ev.lat, ev.lon, 1.001))
      o.updateMatrix()
      malla.current.setMatrixAt(i, o.matrix)
      fila[i] = FILAS.indexOf(ev.estado)
      escala[i] = ESTADOS[ev.estado].escala
      fase[i] = (i * 1.37) % CUADROS                       // cada llama arranca en un cuadro distinto
      velocidad[i] = ev.en_observacion ? 0 : CUADROS_POR_SEG[ev.estado]
      alfa[i] = ev.en_observacion ? 0.5 : 1
      pulso[i] = ev.estado === 'critico' && !ev.en_observacion ? 1 : 0
    })
    malla.current.instanceMatrix.needsUpdate = true
    const g = malla.current.geometry
    g.setAttribute('aFila', new InstancedBufferAttribute(fila, 1))
    g.setAttribute('aEscala', new InstancedBufferAttribute(escala, 1))
    g.setAttribute('aFase', new InstancedBufferAttribute(fase, 1))
    g.setAttribute('aVelocidad', new InstancedBufferAttribute(velocidad, 1))
    g.setAttribute('aAlfa', new InstancedBufferAttribute(alfa, 1))
    g.setAttribute('aPulso', new InstancedBufferAttribute(pulso, 1))
  }, [ordenados, n])

  // En Three.js los "uniforms" se actualizan así en cada cuadro (es la forma normal, aunque el linter avise)
  useFrame(({ clock }) => { uniforms.uTiempo.value = clock.elapsedTime })

  if (n === 0) return null
  return (
    // key={n}: si cambia la cantidad de eventos se crea una malla nueva del tamaño justo
    <instancedMesh key={n} ref={malla} args={[geometria, undefined, n]} frustumCulled={false} renderOrder={2}>
      <shaderMaterial vertexShader={vertex} fragmentShader={fragment} uniforms={uniforms}
        transparent depthWrite={false} side={DoubleSide} />
    </instancedMesh>
  )
}
