import { OrbitControls, Stars, useTexture } from '@react-three/drei'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { AdditiveBlending, BackSide, BufferAttribute, BufferGeometry, SRGBColorSpace, Vector3 } from 'three'
import { ESTADOS } from '../../constantes'
import { aVector, lineasDeGeojson } from './geo'
import Llamas from './Llamas'

const INICIO = aVector(-9, -70, 2.6)       // la cámara arranca mirando al Perú y la Amazonía
const DIST_EVENTO = 1.45                   // distancia de la cámara al enfocar un evento
const RADIO_CLIC_PX = 18

// ---------- La Tierra (imagen NASA Blue Marble vía GIBS) ----------
function Tierra() {
  const textura = useTexture('/texturas/tierra_bluemarble_8k.jpg', (t) => {
    t.colorSpace = SRGBColorSpace   // colores reales de la foto
    t.anisotropy = 8                // más nítida cuando se ve inclinada (cerca del borde)
  })
  return (
    <mesh>
      <sphereGeometry args={[1, 128, 128]} />
      <meshBasicMaterial map={textura} color="#d8d8d8" />
    </mesh>
  )
}

// ---------- Brillo azul de la atmósfera en el borde ----------
function Atmosfera() {
  return (
    <mesh scale={1.035}>
      <sphereGeometry args={[1, 64, 64]} />
      <shaderMaterial transparent blending={AdditiveBlending} side={BackSide} depthWrite={false}
        vertexShader={`varying vec3 vN; void main(){ vN = normalize(normalMatrix * normal);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`}
        fragmentShader={`varying vec3 vN; void main(){ float i = pow(max(0.72 - dot(vN, vec3(0.0, 0.0, 1.0)), 0.0), 3.0);
          gl_FragColor = vec4(0.35, 0.6, 1.0, 1.0) * i; }`} />
    </mesh>
  )
}

// ---------- Límites de departamentos del Perú ----------
function Limites() {
  const [geom, setGeom] = useState(null)
  useEffect(() => {
    let vigente = true
    fetch('/api/regiones/geojson/departamentos').then((r) => r.json()).then((gj) => {
      if (!vigente) return
      const g = new BufferGeometry()
      g.setAttribute('position', new BufferAttribute(lineasDeGeojson(gj), 3))
      setGeom(g)
    }).catch(() => {})
    return () => { vigente = false }
  }, [])
  if (!geom) return null
  return (
    <lineSegments geometry={geom}>
      <lineBasicMaterial color="#f2efe6" transparent opacity={0.28} depthWrite={false} />
    </lineSegments>
  )
}

// ---------- Vuelo suave de la cámara hacia el evento elegido ----------
function Vuelo({ destino, controles }) {
  const { camera } = useThree()
  const activo = useRef(false)

  useEffect(() => { activo.current = Boolean(destino) }, [destino])

  // Si la persona arrastra el globo, se cancela el vuelo
  useEffect(() => {
    const c = controles.current
    if (!c) return
    const cancelar = () => { activo.current = false }
    c.addEventListener('start', cancelar)
    return () => c.removeEventListener('start', cancelar)
  }, [controles])

  useFrame(() => {
    if (!activo.current || !destino) return
    const dirActual = camera.position.clone().normalize()
    const dirDestino = destino.clone().normalize()
    const dist = camera.position.length()
    const nuevaDir = dirActual.lerp(dirDestino, 0.07).normalize()
    const nuevaDist = dist + (DIST_EVENTO - dist) * 0.07
    camera.position.copy(nuevaDir.multiplyScalar(nuevaDist))
    camera.lookAt(0, 0, 0)
    controles.current?.update()
    if (dirActual.angleTo(dirDestino) < 0.002 && Math.abs(nuevaDist - DIST_EVENTO) < 0.005) activo.current = false
  })
  return null
}

// ---------- Sensibilidad según la altura (como Google Earth) ----------
// OrbitControls gira siempre los mismos grados por píxel: de cerca, el suelo "volaba" bajo el mouse.
// Aquí el giro y el zoom se hacen más finos mientras más cerca está la cámara de la superficie.
function SensibilidadAdaptativa({ controles }) {
  const { camera } = useThree()
  useFrame(() => {
    const c = controles.current
    if (!c) return
    const dist = camera.position.length()
    const altura = dist - 1                                   // radio de la Tierra = 1
    c.rotateSpeed = 0.5 * Math.min(1, Math.max(0.025, altura / 1.6))
    c.zoomSpeed = 0.8 * Math.min(1, Math.max(0.12, (altura / dist) * 2.2))
  })
  return null
}

// ---------- Clic y "hover": se busca la llama más cercana al puntero en pantalla ----------
function Seleccion({ eventos, onSeleccionar, onHover }) {
  const { camera, gl } = useThree()
  const posiciones = useMemo(() => eventos.map((e) => aVector(e.lat, e.lon, 1.002)), [eventos])

  useEffect(() => {
    const el = gl.domElement
    let abajo = null

    const buscar = (evento) => {
      const r = el.getBoundingClientRect()
      const mx = evento.clientX - r.left
      const my = evento.clientY - r.top
      const cam = camera.position
      let mejor = null
      let mejorD = RADIO_CLIC_PX
      const v = new Vector3()
      posiciones.forEach((p, i) => {
        if (p.dot(v.copy(cam).sub(p)) <= 0) return       // está del otro lado del globo
        v.copy(p).project(camera)
        const x = ((v.x + 1) / 2) * r.width
        const y = ((1 - v.y) / 2) * r.height
        // la llama se dibuja hacia arriba desde su base: el clic vale en toda su altura
        const altoLlama = 0.03 / (2 * Math.tan((camera.fov * Math.PI) / 360)) * r.height * ESTADOS[eventos[i].estado].escala
        const arriba = y - my
        const d = Math.hypot(mx - x, arriba > 0 ? Math.max(0, arriba - altoLlama * 0.8) : arriba)
        if (d < mejorD) { mejorD = d; mejor = { i, x, y } }
      })
      return mejor
    }

    const mover = (e) => {
      const m = buscar(e)
      el.style.cursor = m ? 'pointer' : 'grab'
      onHover(m ? { evento: eventos[m.i], x: m.x, y: m.y } : null)
    }
    const bajar = (e) => { abajo = [e.clientX, e.clientY] }
    const subir = (e) => {
      if (!abajo || Math.hypot(e.clientX - abajo[0], e.clientY - abajo[1]) > 5) return   // fue un arrastre
      const m = buscar(e)
      if (m) onSeleccionar(eventos[m.i].id)
    }
    const salir = () => onHover(null)

    el.addEventListener('pointermove', mover)
    el.addEventListener('pointerdown', bajar)
    el.addEventListener('pointerup', subir)
    el.addEventListener('pointerleave', salir)
    return () => {
      el.removeEventListener('pointermove', mover)
      el.removeEventListener('pointerdown', bajar)
      el.removeEventListener('pointerup', subir)
      el.removeEventListener('pointerleave', salir)
    }
  }, [camera, gl, posiciones, eventos, onSeleccionar, onHover])
  return null
}

export default function Globo3D({ eventos, seleccionado, onSeleccionar, onHover }) {
  const controles = useRef()
  const elegido = eventos.find((e) => e.id === seleccionado)
  // Solo cambia cuando cambia el evento elegido (no en cada actualización de datos)
  const destino = useMemo(
    () => (elegido ? aVector(elegido.lat, elegido.lon, 1) : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [elegido?.id],
  )

  return (
    <Canvas camera={{ position: INICIO.toArray(), fov: 40, near: 0.01, far: 100 }} dpr={[1, 2]}
      gl={{ antialias: true }} style={{ cursor: 'grab' }}>
      <color attach="background" args={['#07080c']} />
      <Stars radius={60} depth={40} count={4000} factor={3} saturation={0} fade />
      <Suspense fallback={null}>
        <Tierra />
      </Suspense>
      <Atmosfera />
      <Limites />
      <Llamas eventos={eventos} />
      <OrbitControls ref={controles} makeDefault enablePan={false} minDistance={1.12} maxDistance={6}
        rotateSpeed={0.5} zoomSpeed={0.8} enableDamping dampingFactor={0.08} />
      <SensibilidadAdaptativa controles={controles} />
      <Vuelo destino={destino} controles={controles} />
      <Seleccion eventos={eventos} onSeleccionar={onSeleccionar} onHover={onHover} />
    </Canvas>
  )
}
