import type { ReactNode } from 'react'
import { pctArrow, pctClass } from '../../utils/format'
import type { PoolStatus } from '../../types'

const STATUS_LABEL: Record<PoolStatus, string> = { keep: '保留', watch: '观察', drop: '淘汰' }

export function StatusBadge({ status }: { status: PoolStatus }) {
  return (
    <span className={`badge-soft status-${status}`}>
      <span className="status-dot" style={{ background: 'currentColor' }} />
      {STATUS_LABEL[status]}
    </span>
  )
}

export function Tag({ children, accent }: { children: ReactNode; accent?: boolean }) {
  return <span className={`badge-soft${accent ? ' badge-accent' : ''}`}>{children}</span>
}

export function Change({ value }: { value: number | null | undefined }) {
  return <span className={`num ${pctClass(value)}`}>{pctArrow(value)}</span>
}

export function GateStatus({ status }: { status: 'pass' | 'fail' | 'skipped' | 'unavailable' }) {
  const map = {
    pass: { text: '通过', cls: 'status-keep' },
    fail: { text: '淘汰', cls: 'status-drop' },
    skipped: { text: '未启用', cls: 'muted' },
    unavailable: { text: '待确认', cls: 'status-watch' },
  }[status]
  return <span className={map.cls} style={{ fontSize: 12, fontWeight: 600 }}>{map.text}</span>
}
