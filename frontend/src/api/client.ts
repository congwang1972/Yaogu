import type {
  Candidate, GateRow, HistoryItem, ManualMetric, PageData, PoolItem, PoolStats,
  Quote, Run, Score, Settings, SourceItem, StockDetail, SystemStatus,
} from '../types'

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    credentials: 'include',
    headers: init.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...init,
  })
  if (res.status === 204) return undefined as T
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) {
    const err = data?.error
    throw new ApiError(res.status, err?.code ?? `HTTP_${res.status}`, err?.message ?? '请求失败')
  }
  return data as T
}

function json(body: unknown): RequestInit {
  return { method: 'POST', body: JSON.stringify(body) }
}

export const api = {
  login: (password: string) => request<void>('/auth/login', json({ password })),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  me: () => request<{ logged_in: boolean }>('/auth/me'),
  changePassword: (old_password: string, new_password: string) =>
    request<void>('/auth/password', json({ old_password, new_password })),

  systemStatus: () => request<SystemStatus>('/system/status'),

  startRun: (body: { scope: string; board?: string | null; with_theme?: boolean }) =>
    request<{ run_id: number }>('/screening/runs', json(body)),
  listRuns: (page = 1, size = 20) => request<PageData<Run>>(`/screening/runs?page=${page}&size=${size}`),
  getRun: (id: number) => request<Run>(`/screening/runs/${id}`),
  candidates: (id: number, page = 1, size = 50) =>
    request<PageData<Candidate>>(`/screening/runs/${id}/candidates?page=${page}&size=${size}`),
  results: (id: number, stage?: string, passed?: boolean, page = 1, size = 50) => {
    const q = new URLSearchParams({ page: String(page), size: String(size) })
    if (stage) q.set('stage', stage)
    if (passed !== undefined) q.set('passed', String(passed))
    return request<PageData<GateRow>>(`/screening/runs/${id}/results?${q}`)
  },

  stock: (code: string) => request<StockDetail>(`/stocks/${code}`),
  quotes: (code: string, days = 60) => request<{ items: Quote[] }>(`/stocks/${code}/quotes?days=${days}`),
  gates: (code: string, runId?: number | null) =>
    request<{ run_id: number | null; items: GateRow[] }>(
      `/stocks/${code}/gates${runId ? `?run_id=${runId}` : ''}`,
    ),
  score: (code: string, runId?: number | null) =>
    request<Score>(`/stocks/${code}/score${runId ? `?run_id=${runId}` : ''}`),

  pool: (status?: string) => request<{ items: PoolItem[] }>(`/watch-pool${status ? `?status=${status}` : ''}`),
  poolStats: () => request<PoolStats>('/watch-pool/stats'),
  addPool: (body: { code: string; theme_side?: string | null; first_board_date?: string | null; tier?: string | null }) =>
    request<{ id: number }>('/watch-pool', json(body)),
  changePoolStatus: (id: number, status: string, reason: string) =>
    request<PoolItem>(`/watch-pool/${id}`, { method: 'PATCH', body: JSON.stringify({ status, reason }) }),
  removePool: (id: number, reason: string) =>
    request<PoolItem>(`/watch-pool/${id}`, { method: 'DELETE', body: JSON.stringify({ reason }) }),
  history: (id: number) => request<{ items: HistoryItem[] }>(`/watch-pool/${id}/history`),

  metrics: (code: string) => request<{ items: ManualMetric[] }>(`/manual-metrics/${code}`),
  saveMetric: (code: string, body: { trade_date: string; metric: string; value: number | null }) =>
    request<void>(`/manual-metrics/${code}`, { method: 'PUT', body: JSON.stringify(body) }),
  importMetrics: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ imported: number; skipped: number }>('/manual-metrics/import', { method: 'POST', body: form })
  },

  sources: () => request<{ items: SourceItem[] }>('/data-sources'),
  patchSource: (name: string, body: { enabled?: boolean; priority?: number }) =>
    request<void>(`/data-sources/${name}`, { method: 'PATCH', body: JSON.stringify(body) }),
  testSource: (name: string) =>
    request<{ source: string; ok: boolean; latency_ms: number | null; error: string | null }>(
      `/data-sources/${name}/test`,
      { method: 'POST' },
    ),

  settings: () => request<Settings>('/settings'),
  saveSettings: (body: Partial<Settings>) =>
    request<Settings>('/settings', { method: 'PUT', body: JSON.stringify(body) }),
}
