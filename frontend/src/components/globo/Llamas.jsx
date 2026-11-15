import { useFrame } from '@react-three/fiber'
import { useLayoutEffect, useMemo, useRef } from 'react'
import { AdditiveBlending, Color, DoubleSide, InstancedBufferAttribute, Object3D, PlaneGeometry, Quaternion, Vector3 } from 'three'
import { ESTADOS } from '../../constantes'
import { aVector } from './geo'

/*
  Llamas de fuego sobre el globo, una por evento (docs/POLITICA_ESTADOS.md, "Cómo se ve cada estado"):
    Prevención  amarillo  1×    animación suave
    Alto        naranja   1.6×  animación media
    Crítico     rojo      2.3×  pulso rápido + halo
    En observación: color de su estado al 50 %, sin animación

  Se usa "InstancedMesh": una sola figura que la tarjeta de video dibuja N veces en una pasada,
  así miles de llamas no ponen lenta la página. La forma de la llama la dibuja un "shader"
  (programa de la tarjeta de video) con ruido animado.
*/

const RADIO = 1.002        // apenas sobre la superficie
const TAMANO = 0.018       // tamaño base de una llama (radio de la Tierra = 1)
const MIN_ANGULAR = 0.022  // de lejos, la llama no se achica más que esto (sigue visible)

const ANIMACION = { prevencion: 0.7, alto: 1.2, critico: 2.0 }

// ---------- Llama: un rectángulo que siempre mira a la cámara ----------
const vertexLlama = /* glsl */ `
  attribute vec3 aColor;
  attribute float aEscala, aFase, aVelocidad, aIntensidad, aPulso;
  uniform float uTiempo, uTamano, uMinAngular;
  varying vec2 vUv;
  varying vec3 vColor;
  varying float vIntensidad, vT;

  void main() {
    vUv = uv;
    vColor = aColor;
    vIntensidad = aIntensidad;
    vT = uTiempo * aVelocidad + aFase;

    vec4 base = modelViewMatrix * instanceMatrix * vec4(0.0, 0.0, 0.0, 1.0);
    vec4 centro = modelViewMatrix * vec4(0.0, 0.0, 0.0, 1.0);
    float dist = -base.z;
    float latido = 1.0 + aPulso * 0.2 * sin(uTiempo * 7.0 + aFase);
    float tam = max(uTamano, dist * uMinAngular) * aEscala * latido;

    // La llama apunta "hacia afuera" del globo tal como se ve en pantalla;
    // si la miramos desde arriba, apunta hacia arriba de la pantalla.
    vec2 radial = (base - centro).xy;
    float largo = length(radial);
    vec2 arriba = normalize(mix(vec2(0.0, 1.0), radial / max(largo, 1e-5), smoothstep(0.05, 0.35, largo)));
    vec2 derecha = vec2(arriba.y, -arriba.x);
    vec2 d = (derecha * position.x + arriba * position.y) * tam;

    gl_Position = projectionMatrix * vec4(base.xy + d, base.z + 0.01, 1.0);
  }
`

const fragmentLlama = /* glsl */ `
  varying vec2 vUv;
  varying vec3 vColor;
  varying float vIntensidad, vT;

  float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float ruido(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
  }
  float fbm(vec2 p) { return 0.55 * ruido(p) + 0.3 * ruido(p * 2.1) + 0.15 * ruido(p * 4.3); }

  void main() {
    vec2 p = vec2(vUv.x - 0.5, vUv.y);
    float n = fbm(vec2(p.x * 4.0, p.y * 3.0 - vT * 1.6));
    // Ancho: lleno abajo, se angosta hacia la punta; el ruido la hace "lamer" hacia los lados
    float ancho = 0.34 * pow(1.0 - p.y, 0.8) * (0.7 + 0.6 * n);
    float x = p.x + (n - 0.5) * 0.22 * p.y;
    float d = abs(x) / max(ancho, 0.001);
    float alto = smoothstep(1.0, 0.45, p.y + (n - 0.5) * 0.35);
    float forma = smoothstep(1.0, 0.35, d) * alto * smoothstep(0.0, 0.05, p.y);
    float nucleo = smoothstep(0.75, 0.0, d) * smoothstep(0.85, 0.1, p.y);

    vec3 color = mix(vColor, vec3(1.0, 0.96, 0.78), nucleo * 0.85);
    float a = forma * vIntensidad;
    if (a < 0.02) discard;
    gl_FragColor = vec4(color, a);
  }
`

// ---------- Brillo en el suelo + halo de los críticos ----------
const vertexBase = /* glsl */ `
  attribute vec3 aColor;
  attribute float aEscala, aFase, aIntensidad, aPulso;
  uniform float uDistCamara;
  varying vec2 vUv;
  varying vec3 vColor;
  varying float vIntensidad, vPulso, vFase;
  void main() {
    vUv = uv; vColor = aColor; vIntensidad = aIntensidad; vPulso = aPulso; vFase = aFase;
    float tam = max(0.02, (uDistCamara - 1.0) * 0.035) * aEscala;
    gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position * tam, 1.0);
  }
`

const fragmentBase = /* glsl */ `
  uniform float uTiempo;
  varying vec2 vUv;
  varying vec3 vColor;
  varying float vIntensidad, vPulso, vFase;
  void main() {
    float r = length(vUv - 0.5) * 2.0;
    float brillo = smoothstep(1.0, 0.0, r) * 0.55;
    // Halo: un anillo que se expande y se desvanece (solo críticos)
    float onda = fract(uTiempo * 0.7 + vFase * 0.1);
    float anillo = vPulso * smoothstep(0.09, 0.0, abs(r - onda)) * (1.0 - onda);
    float a = (brillo + anillo) * vIntensidad;
    if (a < 0.01) discard;
    gl_FragColor = vec4(vColor, a);
  }
`

const geoLlama = new PlaneGeometry(0.7, 1.4).translate(0, 0.7, 0)   // base de la llama en el punto del evento
const geoBase = new PlaneGeometry(1, 1)

export default function Llamas({ eventos }) {
  const llamas = useRef()
  const bases = useRef()
  const n = eventos.length

  const uniformsLlama = useMemo(() => ({ uTiempo: { value: 0 }, uTamano: { value: TAMANO }, uMinAngular: { value: MIN_ANGULAR } }), [])
  const uniformsBase = useMemo(() => ({ uTiempo: { value: 0 }, uDistCamara: { value: 3 } }), [])

  // Atributos por llama: color, tamaño, animación
  const atributos = useMemo(() => {
    const color = new Float32Array(n * 3)
    const escala = new Float32Array(n)
    const fase = new Float32Array(n)
    const velocidad = new Float32Array(n)
    const intensidad = new Float32Array(n)
    const pulso = new Float32Array(n)
    const c = new Color()
    eventos.forEach((ev, i) => {
      const est = ESTADOS[ev.estado]
      c.set(est.color).toArray(color, i * 3)
      escala[i] = est.escala
      fase[i] = (i * 7.31) % 6.28
      velocidad[i] = ev.en_observacion ? 0 : ANIMACION[ev.estado]
      intensidad[i] = ev.en_observacion ? 0.5 : 1
      pulso[i] = ev.estado === 'critico' && !ev.en_observacion ? 1 : 0
    })
    return { color, escala, fase, velocidad, intensidad, pulso }
  }, [eventos, n])

  // Geometrías propias de esta malla (se crean una vez por cantidad de eventos)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- a propósito: una geometría nueva cuando cambia n
  const geometrias = useMemo(() => ({ llama: geoLlama.clone(), base: geoBase.clone() }), [n])

  useLayoutEffect(() => {
    if (!n || !llamas.current || !bases.current) return
    const o = new Object3D()
    const q = new Quaternion()
    const z = new Vector3(0, 0, 1)
    eventos.forEach((ev, i) => {
      const p = aVector(ev.lat, ev.lon, RADIO)
      o.position.copy(p)
      o.quaternion.identity()
      o.updateMatrix()
      llamas.current.setMatrixAt(i, o.matrix)
      // La mancha de brillo se acuesta sobre la superficie
      o.quaternion.copy(q.setFromUnitVectors(z, p.clone().normalize()))
      o.updateMatrix()
      bases.current.setMatrixAt(i, o.matrix)
    })
    for (const malla of [llamas.current, bases.current]) {
      malla.instanceMatrix.needsUpdate = true
      malla.geometry.setAttribute('aColor', new InstancedBufferAttribute(atributos.color, 3))
      malla.geometry.setAttribute('aEscala', new InstancedBufferAttribute(atributos.escala, 1))
      malla.geometry.setAttribute('aFase', new InstancedBufferAttribute(atributos.fase, 1))
      malla.geometry.setAttribute('aVelocidad', new InstancedBufferAttribute(atributos.velocidad, 1))
      malla.geometry.setAttribute('aIntensidad', new InstancedBufferAttribute(atributos.intensidad, 1))
      malla.geometry.setAttribute('aPulso', new InstancedBufferAttribute(atributos.pulso, 1))
    }
  }, [eventos, atributos, n])

  // En Three.js los "uniforms" se actualizan así en cada cuadro (es la forma normal, aunque el linter avise)
  useFrame(({ clock, camera }) => {
    uniformsLlama.uTiempo.value = clock.elapsedTime
    uniformsBase.uTiempo.value = clock.elapsedTime
    uniformsBase.uDistCamara.value = camera.position.length()
  })

  if (n === 0) return null
  return (
    <>
      {/* key={n}: si cambia la cantidad de eventos se crea una malla nueva del tamaño justo */}
      <instancedMesh key={`b${n}`} ref={bases} args={[geometrias.base, undefined, n]} frustumCulled={false} renderOrder={1}>
        <shaderMaterial vertexShader={vertexBase} fragmentShader={fragmentBase} uniforms={uniformsBase}
          transparent depthWrite={false} blending={AdditiveBlending} side={DoubleSide} />
      </instancedMesh>
      <instancedMesh key={`l${n}`} ref={llamas} args={[geometrias.llama, undefined, n]} frustumCulled={false} renderOrder={2}>
        <shaderMaterial vertexShader={vertexLlama} fragmentShader={fragmentLlama} uniforms={uniformsLlama}
          transparent depthWrite={false} side={DoubleSide} />
      </instancedMesh>
    </>
  )
}
