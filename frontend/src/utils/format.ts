export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return v.toFixed(digits)
}

export function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`
}

export function fmtMv(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${v.toFixed(1)}亿`
}

export function pctClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return 'flat'
  if (v > 0) return 'up'
  if (v < 0) return 'down'
  return 'flat'
}

export function pctArrow(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  if (v > 0) return `▲ ${fmtPct(v)}`
  if (v < 0) return `▼ ${fmtPct(v)}`
  return `— ${fmtPct(v)}`
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return iso.replace('T', ' ').slice(0, 16)
}

export function todayStr(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
