export interface PageData<T> {
  items: T[]
  total: number
  page: number
  size: number
}

export interface RunStats {
  total?: number
  processed?: number
  passed_hard?: number
  candidates?: number
  source?: string
  failures?: string[]
  elapsed_ms?: number
  error?: string
}

export interface Run {
  id: number
  started_at: string
  finished_at: string | null
  status: 'running' | 'success' | 'partial' | 'failed'
  params: { scope?: string; board?: string | null; with_theme?: boolean }
  stats: RunStats | null
}

export interface Candidate {
  code: string
  name: string
  is_st: number
  close: number | null
  pct_chg: number | null
  total_mv: number | null
  turnover_rate: number | null
  trade_date: string | null
  total_score: number
  themes: string[]
}

export interface GateRow {
  id: number
  run_id: number
  code: string
  stage: 'hard_gate' | 'theme' | 'pattern'
  gate: string
  passed: number
  actual_value: string | null
  threshold: string | null
  reason: string | null
}

export interface ScoreDetail {
  key: string
  label: string
  type: 'add' | 'minus'
  delta: number
  weight: number
  source: string
  available: boolean
  met: boolean
  evidence: string | null
  points: number
}

export interface Score {
  run_id: number | null
  code?: string
  total_score: number | null
  details: ScoreDetail[]
  calculated_at?: string
}

export type PoolStatus = 'keep' | 'watch' | 'drop'

export interface PoolItem {
  id: number
  code: string
  status: PoolStatus
  theme_side: 'main' | 'branch' | null
  first_board_date: string | null
  tier: 'leader' | 'follower' | null
  added_at: string
  updated_at: string
  name: string | null
  is_st: number | null
  close: number | null
  pct_chg: number | null
  total_mv: number | null
  turnover_rate: number | null
  total_score: number
}

export interface PoolStage {
  name: string
  start: string
  end: string
  target: number
}

export interface PoolStats {
  capacity: number
  active: number
  counts: Record<PoolStatus, number>
  stage: PoolStage | null
  target: number
  gap: number
}

export interface SystemStatus {
  sources: { total: number; enabled: number; healthy: number }
  last_run: { id: number; status: string; started_at: string; finished_at: string | null; stats: RunStats | null } | null
  last_job: { id: number; job: string; status: string; started_at: string; finished_at: string | null; error: string | null } | null
  pool: PoolStats
}

export interface SourceItem {
  name: string
  enabled: number
  priority: number
  last_success_at: string | null
  last_error: string | null
  last_health: { checked_at: string; ok: number; latency_ms: number | null; error: string | null } | null
}

export interface Quote {
  code: string
  trade_date: string
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  pre_close: number | null
  pct_chg: number | null
  turnover_rate: number | null
  total_mv: number | null
}

export interface StockDetail {
  stock: { code: string; name: string; market: string; is_st: number; status: string }
  quote: Quote | null
  themes: { id: number; name: string; branch: string; source: string }[]
  watch_pool: PoolItem | null
}

export interface ManualMetric {
  id: number
  code: string
  trade_date: string
  metric: string
  value: number | null
  entered_at: string
}

export interface HistoryItem {
  id: number
  from_status: string | null
  to_status: string
  reason: string
  created_at: string
}

export interface Settings {
  thresholds: Record<string, number | boolean>
  scoring: { base: number; items: { key: string; label: string; type: string; delta: number; weight: number; source: string }[] }
  pool: { capacity: number; stages: PoolStage[] }
  schedule: { enabled: boolean; refresh_time: string }
}
