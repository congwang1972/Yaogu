import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { PoolItem, PoolStats, PoolStatus } from '../types'
import { Button, Card, CardHead, Change, DataTable, Modal, StatusBadge, useToast, type Column } from '../components/ui'
import { fmtMv, fmtNum, fmtTime } from '../utils/format'

type Filter = 'all' | PoolStatus

const REASON_PRESETS = ['跟风位，无梯队', '缩量一字，易断板', '涨幅过大，接近异动红线', '题材退潮', '手动剔除']

export function WatchPool() {
  const [items, setItems] = useState<PoolItem[]>([])
  const [stats, setStats] = useState<PoolStats | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [loading, setLoading] = useState(true)
  const [target, setTarget] = useState<PoolItem | null>(null)
  const [nextStatus, setNextStatus] = useState<PoolStatus>('drop')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const toast = useToast()
  const navigate = useNavigate()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [list, s] = await Promise.all([
        api.pool(filter === 'all' ? undefined : filter),
        api.poolStats(),
      ])
      setItems(list.items)
      setStats(s)
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '加载失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [filter, toast])

  useEffect(() => { load() }, [load])

  const openChange = (item: PoolItem, status: PoolStatus) => {
    setTarget(item)
    setNextStatus(status)
    setReason('')
  }

  const submit = async () => {
    if (!target) return
    if (!reason.trim()) {
      toast('请填写变更理由', 'warn')
      return
    }
    setSaving(true)
    try {
      await api.changePoolStatus(target.id, nextStatus, reason.trim())
      toast(`${target.code} 状态已更新`)
      setTarget(null)
      await load()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '更新失败', 'error')
    } finally {
      setSaving(false)
    }
  }

  const columns: Column<PoolItem>[] = [
    {
      key: 'code', title: '代码 / 名称', width: '160px',
      render: (r) => (
        <div>
          <div className="num" style={{ fontWeight: 600 }}>{r.code}</div>
          <div className="caption">{r.name ?? '—'}</div>
        </div>
      ),
    },
    { key: 'total_mv', title: '总市值', align: 'right', render: (r) => <span className="num">{fmtMv(r.total_mv)}</span> },
    { key: 'close', title: '现价', align: 'right', render: (r) => <span className="num">{fmtNum(r.close)}</span> },
    { key: 'pct_chg', title: '涨跌', align: 'right', render: (r) => <Change value={r.pct_chg} /> },
    {
      key: 'theme_side', title: '题材方向',
      render: (r) => <span className="caption">{r.theme_side === 'main' ? '主线' : r.theme_side === 'branch' ? '支线' : '未标注'}</span>,
    },
    { key: 'first_board_date', title: '首板日期', render: (r) => <span className="num caption">{r.first_board_date ?? '—'}</span> },
    {
      key: 'tier', title: '梯队',
      render: (r) => <span className="caption">{r.tier === 'leader' ? '龙头' : r.tier === 'follower' ? '跟风' : '—'}</span>,
    },
    { key: 'total_score', title: '评分', align: 'right', render: (r) => <span className="num">{fmtNum(r.total_score, 0)}</span> },
    { key: 'status', title: '状态', render: (r) => <StatusBadge status={r.status} /> },
    { key: 'updated_at', title: '最近变更', render: (r) => <span className="micro">{fmtTime(r.updated_at)}</span> },
    {
      key: 'op', title: '操作', width: '200px',
      render: (r) => (
        <div style={{ display: 'flex', gap: 4 }} onClick={(e) => e.stopPropagation()}>
          {r.status !== 'keep' && <Button variant="ghost" onClick={() => openChange(r, 'keep')}>保留</Button>}
          {r.status !== 'watch' && <Button variant="ghost" onClick={() => openChange(r, 'watch')}>观察</Button>}
          {r.status !== 'drop' && (
            <Button variant="ghost" onClick={() => openChange(r, 'drop')}
              style={{ color: 'var(--feedback-error)' }}>淘汰</Button>
          )}
        </div>
      ),
    },
  ]

  const counts = stats?.counts
  const pct = stats ? Math.min(100, Math.round((stats.active / Math.max(1, stats.capacity)) * 100)) : 0

  return (
    <>
      <div className="actionbar">
        <h1 className="page-title">观察池</h1>
        <a className="btn-dark" style={{ display: 'inline-flex', alignItems: 'center', textDecoration: 'none' }}
          href="/api/v1/export/watch-pool.csv">导出 CSV</a>
        {stats && (
          <span className="caption">
            当前 {stats.active} / 容量 {stats.capacity}
            {stats.stage ? ` · ${stats.stage.name}目标 ${stats.target} 只` : ''}
            {stats.gap > 0 ? ` · 还需淘汰 ${stats.gap} 只` : ''}
          </span>
        )}
      </div>

      {stats && (
        <Card className="card-body" >
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, padding: 16 }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                <span className="caption">池容量</span>
                <span className="num caption">{stats.active} / {stats.capacity}</span>
              </div>
              <div style={{ height: 6, background: 'var(--bg-surface-3)', borderRadius: 999 }}>
                <div style={{
                  width: `${pct}%`, height: '100%', borderRadius: 999,
                  background: stats.active >= stats.capacity ? 'var(--feedback-warn)' : 'var(--accent)',
                }} />
              </div>
            </div>
            {counts && (
              <div style={{ display: 'flex', gap: 16 }}>
                <Metric label="保留" value={counts.keep} cls="status-keep" />
                <Metric label="观察" value={counts.watch} cls="status-watch" />
                <Metric label="淘汰" value={counts.drop} cls="status-drop" />
              </div>
            )}
          </div>
        </Card>
      )}

      <Card className="card-body" >
        <CardHead
          title={
            <div style={{ display: 'flex', gap: 12 }}>
              {(['all', 'keep', 'watch', 'drop'] as Filter[]).map((f) => (
                <button key={f} className="btn-ghost"
                  style={filter === f ? { color: 'var(--text-primary)', fontWeight: 600 } : undefined}
                  onClick={() => setFilter(f)}>
                  {{ all: '全部', keep: '保留', watch: '观察', drop: '淘汰' }[f]}
                </button>
              ))}
            </div>
          }
        />
        <div style={{ margin: '0 -16px' }}>
          <DataTable
            columns={columns}
            rows={items}
            rowKey={(r) => r.id}
            loading={loading}
            onRowClick={(r) => navigate(`/stocks/${r.code}`)}
            empty="观察池为空，去工作台选股吧"
          />
        </div>
      </Card>

      <Modal
        open={!!target}
        title={nextStatus === 'drop' ? '标记淘汰' : nextStatus === 'keep' ? '标记保留' : '标记观察'}
        onClose={() => setTarget(null)}
        footer={
          <>
            <Button onClick={() => setTarget(null)}>取消</Button>
            <Button variant={nextStatus === 'drop' ? 'danger' : 'primary'} loading={saving} onClick={submit}>
              确认
            </Button>
          </>
        }
      >
        <p className="caption" style={{ marginBottom: 8 }}>
          {target?.code} {target?.name} · 淘汰必须填写理由，便于日后复盘
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
          {REASON_PRESETS.map((r) => (
            <button key={r} className="badge-soft" style={{ cursor: 'pointer', border: 'none' }}
              onClick={() => setReason(r)}>{r}</button>
          ))}
        </div>
        <textarea
          className="input-dark"
          rows={3}
          placeholder="请填写变更理由（必填）"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </Modal>
    </>
  )
}

function Metric({ label, value, cls }: { label: string; value: number; cls: string }) {
  return (
    <div style={{ textAlign: 'right' }}>
      <div className="micro">{label}</div>
      <div className={`num ${cls}`} style={{ fontSize: 18, fontWeight: 600 }}>{value}</div>
    </div>
  )
}
