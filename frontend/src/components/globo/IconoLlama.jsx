// La misma llama plana del globo, en SVG (para la leyenda).
const d = (cx, base, w, h, lengua) => {
  const P = (x, y) => `${(cx + x * w).toFixed(1)} ${(base + y * h).toFixed(1)}`
  const c = (a, b, e) => ` C ${P(...a)}, ${P(...b)}, ${P(...e)}`
  let s = `M ${P(0, -1)}` + c([0.1, -0.78], [0.52, -0.58], [0.48, -0.28]) + c([0.46, 0.02], [-0.46, 0.02], [-0.48, -0.28])
  s += lengua
    ? c([-0.5, -0.46], [-0.42, -0.58], [-0.34, -0.74]) + c([-0.2, -0.6], [-0.12, -0.56], [-0.06, -0.6]) + c([-0.02, -0.78], [0, -0.88], [0, -1])
    : c([-0.52, -0.58], [-0.1, -0.78], [0, -1])
  return s + ' Z'
}
const CUERPO = d(32, 88, 44, 80, true)
const CENTRO = d(32, 85, 22, 40, false)

export default function IconoLlama({ color, escala = 1, atenuada = false }) {
  const alto = 14 * escala
  return (
    <svg viewBox="0 0 64 96" width={(alto * 64) / 96} height={alto} aria-hidden="true" style={{ opacity: atenuada ? 0.5 : 1 }}>
      <path d={CUERPO} fill={color} stroke="rgba(20,12,8,.75)" strokeWidth="3" />
      <path d={CENTRO} fill="#fff1b8" />
    </svg>
  )
}
