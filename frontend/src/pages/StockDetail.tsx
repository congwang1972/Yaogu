import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import ReactECharts from 'echarts-for-react'
import type { EChartsOption } from 'echarts'
import { api, ApiError } from '../api/client'
import type { GateRow, HistoryItem, ManualMetric, Quote, Score, StockDetail as StockDetailData } from '../types'
import { Button, Card, CardHead, GateStatus, StatusBadge, Tag, useToast } from '../components/ui'
import { CHART_DOWN, CHART_THEME, CHART_UP } from '../charts/theme'
import { fmtMv, fmtNum, fmtPct, fmtTime, pctClass, todayStr } from '../utils/format'

const GATE_LABEL: Record<string, string> = {
  total_mv: '总市值',
  price: '收盘价',
  st_suspended: 'ST 与交易状态',
  float_mv: '流通市值',
  theme_match: '题材匹配',
  first_board: '近期首板涨停',
  one_word: '连续缩量一字',
  healthy_turnover: '换手率 15%–30%',
  ladder: '板块跟风梯队',
}

/** screening_results 只存 passed 0/1，未通过时用理由反推「未启用 / 数据缺失」。 */
function gateStatus(row: GateRow): 'pass' | 'fail' | 'skipped' | 'unavailable' {
  const reason = row.reason ?? ''
  // skipped 落库时 passed=1（不否决），所以要靠理由先分辨出来
  if (reason.includes('未启用')) return 'skipped'
  if (row.passed === 1) return 'pass'
  if (reason.includes('缺失') || reason.includes('不可得')) return 'unavailable'
  return 'fail'
}

const METRICS = [
  { key: 'pct_30d', label: '滚动 30 日涨幅', hint: '百分比数值，如 165 表示 +165%；评分阈值 ≥150%' },
  { key: 'touch_200', label: '触及 200 日新高', hint: '1 = 是，0 = 否' },
  { key: 'turnover_history', label: '历史换手活跃', hint: '1 = 是，0 = 否' },
  { key: 'name_recog', label: '名称辨识度', hint: '1 = 辨识度高，0 = 一般' },
  { key: 'event_catalyst', label: '年末催化事件', hint: '1 = 有，0 = 无' },
] as const

export function StockDetail() {
  const { code = '' } = useParams()
  const navigate = useNavigate()
  const toast = useToast()

  const [data, setData] = useState<StockDetailData | null>(null)
  const [quotes, setQuotes] = useState<Quote[]>([])
  const [gates, setGates] = useState<GateRow[]>([])
  const [score, setScore] = useState<Score | null>(null)
  const [metrics, setMetrics] = useState<ManualMetric[]>([])
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [notFound, setNotFound] = useState(false)
  const [adding, setAdding] = useState(false)

  const load = useCallback(async () => {
    try {
      const stock = await api.stock(code)
      setData(stock)
      const [q, g, s, m] = await Promise.all([
        api.quotes(code, 90),
        api.gates(code),
        api.score(code),
        api.metrics(code),
      ])
      setQuotes(q.items)
      setGates(g.items)
      setScore(s)
      setMetrics(m.items)
      if (stock.watch_pool) {
        const h = await api.history(stock.watch_pool.id)
        setHistory(h.items)
      } else {
        setHistory([])
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setNotFound(true)
      else toast(err instanceof ApiError ? err.message : '加载失败', 'error')
    }
  }, [code, toast])

  useEffect(() => { load() }, [load])

  const addToPool = async () => {
    setAdding(true)
    try {
      await api.addPool({ code })
      toast('已加入观察池')
      await load()
    } catch (err) {
      toast(
        err instanceof ApiError && err.status === 409 ? '该股票已在观察池中' : '加入失败',
        'error',
      )
    } finally {
      setAdding(false)
    }
  }

  const chartOption = useMemo<EChartsOption>(() => {
    const rows = quotes.filter((q) => q.close !== null).slice().reverse()
    const dates = rows.map((q) => q.trade_date)
    const candles = rows.map((q) => [q.open ?? q.close, q.close, q.low ?? q.close, q.high ?? q.close])
    return {
      animation: false,
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      legend: { show: false },
      grid: [
        { left: 52, right: 16, top: 16, height: 220 },
        { left: 52, right: 16, top: 268, height: 56 },
      ],
      xAxis: [
        { type: 'category', data: dates, boundaryGap: true },
        { type: 'category', gridIndex: 1, data: dates, boundaryGap: true, axisLabel: { show: false } },
      ],
      yAxis: [
        { scale: true, gridIndex: 0 },
        { gridIndex: 1, axisLabel: { show: false }, splitLine: { show: false } },
      ],
      dataZoom: [{ type: 'inside', xAxisIndex: [0, 1], start: 40, end: 100 }],
      series: [
        {
          name: 'K 线',
          type: 'candlestick',
          data: candles,
          itemStyle: { color: CHART_UP, color0: CHART_DOWN, borderColor: CHART_UP, borderColor0: CHART_DOWN },
        },
        {
          name: '换手率',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          // 免费源快照不含成交量，副图改用同一批快照里的换手率，口径一致
          data: rows.map((q) => q.turnover_rate),
          itemStyle: { color: 'rgba(76,141,255,0.5)' },
        },
      ],
    }
  }, [quotes])

  if (notFound) {
    return (
      <div className="empty-state">
        <p>未找到股票 {code}，可能尚未抓取到该标的行情。</p>
        <Button onClick={() => navigate('/workbench')}>返回工作台</Button>
      </div>
    )
  }

  if (!data) {
    return <div className="empty-state">加载中…</div>
  }

  const { stock, quote, themes, watch_pool: pooled } = data
  const latestMetric = new Map<string, number | null>()
  for (const m of metrics) {
    if (!latestMetric.has(m.metric)) latestMetric.set(m.metric, m.value)
  }

  return (
    <>
      <div className="actionbar">
        <button className="btn-ghost" onClick={() => navigate(-1)}>← 返回</button>
        <h1 className="page-title">{stock.name}</h1>
        <span className="num caption">{stock.code} · {stock.market}</span>
        {stock.is_st === 1 && <Tag>ST</Tag>}
        {themes.map((t) => <Tag key={t.id} accent>{t.name}</Tag>)}
        <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
          {pooled ? (
            <>
              <StatusBadge status={pooled.status} />
              <Button onClick={() => navigate('/pool')}>去观察池</Button>
            </>
          ) : (
            <Button variant="primary" loading={adding} onClick={addToPool}>加入观察池</Button>
          )}
        </span>
      </div>

      <div className="stat-strip">
        <Stat label="现价" value={fmtNum(quote?.close)} cls={pctClass(quote?.pct_chg)} sub={fmtPct(quote?.pct_chg)} />
        <Stat label="总市值" value={fmtMv(quote?.total_mv)} />
        <Stat label="换手率" value={quote?.turnover_rate == null ? '—' : `${quote.turnover_rate.toFixed(2)}%`} />
        <Stat label="数据日期" value={quote?.trade_date ?? '—'} />
      </div>

      <div className="detail-grid">
        <Card>
          <CardHead
            title="近 90 个交易日"
            extra={<span className="micro">K 线 + 换手率 · 来源见工作台批次信息</span>}
          />
          <div style={{ padding: 8 }}>
            {quotes.length ? (
              <ReactECharts option={chartOption} theme={CHART_THEME} style={{ height: 340 }} notMerge />
            ) : (
              <div className="empty-state">暂无历史行情</div>
            )}
          </div>
        </Card>

        <div style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
          <Card>
            <CardHead
              title="硬门槛与形态"
              extra={score?.run_id ? <span className="micro">批次 #{score.run_id}</span> : null}
            />
            <div className="card-body" style={{ display: 'grid', gap: 10 }}>
              {gates.length ? gates.map((g) => (
                <div key={g.id} style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                  <span style={{ minWidth: 112, fontSize: 13 }}>{GATE_LABEL[g.gate] ?? g.gate}</span>
                  <GateStatus status={gateStatus(g)} />
                  <span className="caption" style={{ flex: 1, textAlign: 'right' }}>
                    {g.actual_value ?? '—'}
                  </span>
                </div>
              )) : <p className="caption">尚未执行筛选，暂无判定记录。</p>}
              {gates.length > 0 && (
                <p className="micro" style={{ marginTop: 4 }}>
                  「待确认」表示数据源缺失，既不算通过也不算淘汰，需人工核对。
                </p>
              )}
            </div>
          </Card>

          <Card>
            <CardHead
              title="评分明细"
              extra={<span className="num" style={{ fontSize: 18, fontWeight: 600 }}>
                {fmtNum(score?.total_score, 0)}
              </span>}
            />
            <div className="card-body" style={{ display: 'grid', gap: 8 }}>
              {score?.details.length ? score.details.map((d) => (
                <div key={d.key} style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                  <span style={{ fontSize: 13 }}>{d.label}</span>
                  <span className="micro" style={{ flex: 1 }}>{d.evidence ?? '—'}</span>
                  {!d.available ? (
                    <span className="status-watch micro">待确认</span>
                  ) : d.met ? (
                    <span className={`num ${d.type === 'add' ? 'up' : 'down'}`}>
                      {d.type === 'add' ? '+' : '−'}{Math.abs(d.points).toFixed(0)}
                    </span>
                  ) : (
                    <span className="muted micro">未满足</span>
                  )}
                </div>
              )) : <p className="caption">暂无评分，需先执行一次筛选。</p>}
            </div>
          </Card>
        </div>
      </div>

      <div className="detail-grid" style={{ marginTop: 16 }}>
        <ManualMetricsForm
          code={code}
          latest={latestMetric}
          list={metrics}
          onSaved={async () => {
            await load()
            toast('已保存，重新执行筛选后计入评分')
          }}
        />

        <Card>
          <CardHead title="观察池变更记录" />
          <div className="card-body">
            {history.length ? (
              <ol className="timeline">
                {history.map((h) => (
                  <li key={h.id}>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
                      <StatusBadge status={h.to_status as 'keep' | 'watch' | 'drop'} />
                      <span className="num micro">{fmtTime(h.created_at)}</span>
                    </div>
                    <p className="caption" style={{ margin: '4px 0 0' }}>{h.reason}</p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="caption">{pooled ? '暂无变更记录' : '加入观察池后可记录变更理由'}</p>
            )}
          </div>
        </Card>
      </div>

      <p className="micro" style={{ marginTop: 16 }}>
        本页数据仅用于历史规律复盘，不构成投资建议。数据抓取时间：{fmtTime(quote?.trade_date)}
      </p>
    </>
  )
}

function Stat({ label, value, sub, cls }: { label: string; value: string; sub?: string; cls?: string }) {
  return (
    <div>
      <div className="micro">{label}</div>
      <div className={`num ${cls ?? ''}`} style={{ fontSize: 20, fontWeight: 600 }}>{value}</div>
      {sub && <div className={`num micro ${cls ?? ''}`}>{sub}</div>}
    </div>
  )
}

interface MetricFormProps {
  code: string
  latest: Map<string, number | null>
  list: ManualMetric[]
  onSaved: () => Promise<void>
}

function ManualMetricsForm({ code, latest, list, onSaved }: MetricFormProps) {
  const [date, setDate] = useState(todayStr())
  const [values, setValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const toast = useToast()

  const submit = async () => {
    const entries = METRICS.filter((m) => values[m.key] !== undefined && values[m.key] !== '')
    if (!entries.length) {
      toast('请至少填写一项指标', 'warn')
      return
    }
    setSaving(true)
    try {
      for (const m of entries) {
        const raw = values[m.key]
        await api.saveMetric(code, {
          trade_date: date,
          metric: m.key,
          value: raw === '' ? null : Number(raw),
        })
      }
      setValues({})
      await onSaved()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '保存失败', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHead
        title="人工补录指标"
        extra={<span className="micro">免费源缺失，需手动维护</span>}
      />
      <div className="card-body">
        <div style={{ marginBottom: 12 }}>
          <label className="field-label" htmlFor="metric-date">交易日期</label>
          <input id="metric-date" className="input-dark" type="date" value={date}
            onChange={(e) => setDate(e.target.value)} />
        </div>
        <div className="form-row" style={{ marginBottom: 12 }}>
          {METRICS.map((m) => (
            <div key={m.key}>
              <label className="field-label" htmlFor={`metric-${m.key}`}>
                {m.label}
                <span className="micro" style={{ marginLeft: 6 }}>
                  当前：{latest.get(m.key) ?? '—'}
                </span>
              </label>
              <input
                id={`metric-${m.key}`}
                className="input-dark"
                style={{ width: '100%' }}
                inputMode="decimal"
                placeholder={m.hint}
                value={values[m.key] ?? ''}
                onChange={(e) => setValues((v) => ({ ...v, [m.key]: e.target.value }))}
              />
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Button variant="primary" loading={saving} onClick={submit}>保存补录</Button>
          <span className="micro">仅填写本次要更新的项，未填项保持不变</span>
        </div>

        {list.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div className="micro" style={{ marginBottom: 6 }}>最近记录</div>
            <div style={{ display: 'grid', gap: 4 }}>
              {list.slice(0, 6).map((m) => (
                <div key={m.id} className="caption" style={{ display: 'flex', gap: 12 }}>
                  <span className="num">{m.trade_date}</span>
                  <span style={{ flex: 1 }}>{METRICS.find((x) => x.key === m.metric)?.label ?? m.metric}</span>
                  <span className="num">{m.value ?? '—'}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}
