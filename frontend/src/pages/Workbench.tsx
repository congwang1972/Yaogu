import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import type { Candidate, GateRow, Run, SystemStatus } from '../types'
import { Button, Card, CardHead, Change, DataTable, Tag, useToast, type Column } from '../components/ui'
import { fmtMv, fmtNum, fmtTime } from '../utils/format'

type Tab = 'candidates' | 'rejected'

export function Workbench() {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const [run, setRun] = useState<Run | null>(null)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [rejected, setRejected] = useState<GateRow[]>([])
  const [tab, setTab] = useState<Tab>('candidates')
  const [starting, setStarting] = useState(false)
  const toast = useToast()
  const navigate = useNavigate()

  const loadLatest = useCallback(async () => {
    const [s, runs] = await Promise.all([api.systemStatus(), api.listRuns(1, 1)])
    setStatus(s)
    const latest = runs.items[0]
    if (!latest) return
    setRun(latest)
    if (latest.status === 'success' || latest.status === 'partial') {
      const [c, r] = await Promise.all([
        api.candidates(latest.id, 1, 100),
        api.results(latest.id, 'hard_gate', false, 1, 100),
      ])
      setCandidates(c.items)
      setRejected(r.items)
    }
  }, [])

  useEffect(() => {
    loadLatest().catch(() => toast('加载失败，请刷新重试', 'error'))
  }, [loadLatest, toast])

  // 轮询批次进度：3 分钟内通常结束，仍 running 时前端继续显示进度而不是取消
  useEffect(() => {
    if (!run || run.status !== 'running') return
    const timer = window.setInterval(async () => {
      try {
        const next = await api.getRun(run.id)
        setRun(next)
        if (next.status !== 'running') {
          window.clearInterval(timer)
          setStarting(false)
          const [c, r] = await Promise.all([
            api.candidates(next.id, 1, 100),
            api.results(next.id, 'hard_gate', false, 1, 100),
          ])
          setCandidates(c.items)
          setRejected(r.items)
          const stats = next.stats
          toast(
            next.status === 'success'
              ? `筛选完成 · 候选 ${stats?.candidates ?? c.total} 只 · ${((stats?.elapsed_ms ?? 0) / 1000).toFixed(0)}s`
              : '筛选完成，但部分数据源失败，结果可能不完整',
            next.status === 'success' ? 'info' : 'warn',
          )
          api.systemStatus().then(setStatus).catch(() => undefined)
        }
      } catch {
        window.clearInterval(timer)
        setStarting(false)
        toast('进度查询失败', 'error')
      }
    }, 1500)
    return () => window.clearInterval(timer)
  }, [run, toast])

  const start = async () => {
    setStarting(true)
    try {
      const { run_id } = await api.startRun({ scope: 'all', with_theme: true })
      const next = await api.getRun(run_id)
      setRun(next)
      toast('已开始筛选，正在抓取行情…')
    } catch (err) {
      setStarting(false)
      toast(err instanceof ApiError ? err.message : '启动失败', 'error')
    }
  }

  const addToPool = async (code: string) => {
    try {
      await api.addPool({ code })
      toast(`${code} 已加入观察池`)
      setStatus(await api.systemStatus())
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '加入失败', 'error')
    }
  }

  const candidateColumns: Column<Candidate>[] = [
    {
      key: 'code', title: '代码 / 名称', width: '160px',
      render: (r) => (
        <div>
          <div className="num" style={{ fontWeight: 600 }}>{r.code}</div>
          <div className="caption">{r.name}</div>
        </div>
      ),
    },
    { key: 'total_mv', title: '总市值', align: 'right', render: (r) => <span className="num">{fmtMv(r.total_mv)}</span> },
    { key: 'close', title: '现价', align: 'right', render: (r) => <span className="num">{fmtNum(r.close)}</span> },
    { key: 'pct_chg', title: '涨跌', align: 'right', render: (r) => <Change value={r.pct_chg} /> },
    {
      key: 'themes', title: '题材', render: (r) =>
        r.themes.length ? <Tag accent>{r.themes.slice(0, 2).join(' / ')}</Tag> : <span className="muted">未命中</span>,
    },
    {
      key: 'score', title: '评分', align: 'right', width: '90px',
      render: (r) => <span className="num" style={{ fontWeight: 600 }}>{fmtNum(r.total_score, 0)}</span>,
    },
    {
      key: 'op', title: '操作', width: '110px',
      render: (r) => (
        <Button variant="ghost" onClick={(e) => { e.stopPropagation(); addToPool(r.code) }}>
          加入观察池
        </Button>
      ),
    },
  ]

  const rejectedColumns: Column<GateRow>[] = [
    { key: 'code', title: '代码', width: '100px', render: (r) => <span className="num">{r.code}</span> },
    { key: 'gate', title: '门槛', render: (r) => r.gate },
    { key: 'actual_value', title: '实测值', align: 'right', render: (r) => <span className="num">{r.actual_value ?? '—'}</span> },
    { key: 'threshold', title: '阈值' },
    { key: 'reason', title: '说明', render: (r) => <span className="muted">{r.reason ?? '—'}</span> },
  ]

  const stats = run?.stats
  const running = run?.status === 'running'

  return (
    <>
      <div className="actionbar">
        <h1 className="page-title">选股工作台</h1>
        <Button variant="primary" onClick={start} loading={starting || running}>
          {running ? '筛选中…' : '执行筛选'}
        </Button>
        {run && (
          <span className="caption">
            批次 #{run.id} · {run.status === 'running'
              ? `已处理 ${stats?.processed ?? 0}/${stats?.total ?? '—'}`
              : fmtTime(run.finished_at ?? run.started_at)}
          </span>
        )}
        <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          {run && (run.status === 'success' || run.status === 'partial') && (
            <a className="btn-dark" style={{ display: 'inline-flex', alignItems: 'center', textDecoration: 'none' }}
              href={`/api/v1/export/screening/${run.id}.csv`}>
              导出 CSV
            </a>
          )}
        </span>
      </div>

      <div className="notice" style={{ marginBottom: 16 }}>
        ⚠ 本期未校验机构持仓与利空事件，加入观察池前请人工核对。
      </div>

      {run?.status === 'failed' && (
        <div className="notice notice-error" style={{ marginBottom: 16 }}>
          筛选失败：{stats?.error ?? '数据源不可用'}。请前往「数据源」页检查后重试。
        </div>
      )}
      {run?.status === 'partial' && (
        <div className="notice" style={{ marginBottom: 16 }}>
          部分数据源失败：{(stats?.failures ?? []).join('；') || '结果可能不完整'}
        </div>
      )}

      <Card>
        <CardHead
          title={
            <div style={{ display: 'flex', gap: 16 }}>
              <button className={`btn-ghost${tab === 'candidates' ? ' active' : ''}`}
                style={tab === 'candidates' ? { color: 'var(--text-primary)', fontWeight: 600 } : undefined}
                onClick={() => setTab('candidates')}>
                候选池 ({candidates.length})
              </button>
              <button className="btn-ghost"
                style={tab === 'rejected' ? { color: 'var(--text-primary)', fontWeight: 600 } : undefined}
                onClick={() => setTab('rejected')}>
                落选明细 ({rejected.length})
              </button>
            </div>
          }
          extra={<span className="micro">数据来源：{stats?.source ?? '—'} · 抓取于 {fmtTime(run?.finished_at ?? null)}</span>}
        />
        {tab === 'candidates' ? (
          <DataTable
            columns={candidateColumns}
            rows={candidates}
            rowKey={(r) => r.code}
            loading={starting || running}
            onRowClick={(r) => navigate(`/stocks/${r.code}`)}
            empty={run ? '当前条件下无候选，可在设置中放宽阈值' : '尚未执行筛选'}
          />
        ) : (
          <DataTable
            columns={rejectedColumns}
            rows={rejected}
            rowKey={(r) => r.id}
            loading={starting || running}
            empty="暂无落选记录"
          />
        )}
      </Card>

      {status?.last_job && (
        <p className="micro" style={{ marginTop: 12 }}>
          最近任务：{status.last_job.job} · {status.last_job.status} · {fmtTime(status.last_job.started_at)}
        </p>
      )}
    </>
  )
}
