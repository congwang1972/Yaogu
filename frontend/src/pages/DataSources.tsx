import { useCallback, useEffect, useState } from 'react'
import { api, ApiError } from '../api/client'
import type { SourceItem } from '../types'
import { Button, Card, CardHead, useToast } from '../components/ui'
import { fmtTime } from '../utils/format'

const SOURCE_META: Record<string, { title: string; desc: string }> = {
  eastmoney: { title: '东方财富', desc: '全市场快照 · 主数据源（字段最全）' },
  tencent: { title: '腾讯行情', desc: '按代码批量查询 · 备用源（需已有股票列表）' },
  sina: { title: '新浪财经', desc: '按代码批量查询 · 备用源（无市值字段）' },
}

export function DataSources() {
  const [items, setItems] = useState<SourceItem[]>([])
  const [loading, setLoading] = useState(true)
  const [testing, setTesting] = useState<string | null>(null)
  const toast = useToast()

  const load = useCallback(async () => {
    try {
      const res = await api.sources()
      setItems(res.items)
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '加载失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => { load() }, [load])

  const toggle = async (item: SourceItem) => {
    try {
      await api.patchSource(item.name, { enabled: item.enabled !== 1 })
      await load()
      toast(`${SOURCE_META[item.name]?.title ?? item.name} 已${item.enabled === 1 ? '停用' : '启用'}`)
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '操作失败', 'error')
    }
  }

  const test = async (item: SourceItem) => {
    setTesting(item.name)
    try {
      const res = await api.testSource(item.name)
      toast(
        res.ok
          ? `${SOURCE_META[item.name]?.title ?? item.name} 可用，延迟 ${res.latency_ms ?? '—'} ms`
          : `测试失败：${res.error ?? '未知错误'}`,
        res.ok ? 'info' : 'error',
      )
      await load()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '测试失败', 'error')
    } finally {
      setTesting(null)
    }
  }

  return (
    <>
      <div className="actionbar">
        <h1 className="page-title">数据源健康</h1>
        <span className="caption">按优先级自动降级，前一个源失败才尝试下一个</span>
      </div>

      <div className="notice" style={{ marginBottom: 16 }}>
        ⚠ 已知部分免费接口会屏蔽腾讯云服务器 IP。部署后若某源持续失败，请先测试再决定是否停用。
      </div>

      {loading ? (
        <div className="empty-state">加载中…</div>
      ) : (
        <div style={{ display: 'grid', gap: 12 }}>
          {items.map((item) => {
            const meta = SOURCE_META[item.name] ?? { title: item.name, desc: '' }
            const health = item.last_health
            return (
              <Card key={item.name}>
                <CardHead
                  title={
                    <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      {meta.title}
                      <span className="badge-soft">优先级 {item.priority}</span>
                      {item.enabled === 1 ? (
                        <span className="badge-soft status-keep">启用</span>
                      ) : (
                        <span className="badge-soft status-drop">停用</span>
                      )}
                    </span>
                  }
                  extra={
                    <div style={{ display: 'flex', gap: 8 }}>
                      <Button loading={testing === item.name} onClick={() => test(item)}>测试连接</Button>
                      <Button variant={item.enabled === 1 ? 'ghost' : 'default'} onClick={() => toggle(item)}>
                        {item.enabled === 1 ? '停用' : '启用'}
                      </Button>
                    </div>
                  }
                />
                <div className="card-body" style={{ display: 'grid', gap: 6 }}>
                  <p className="caption" style={{ margin: 0 }}>{meta.desc}</p>
                  <div className="caption">
                    最近成功：{fmtTime(item.last_success_at)}
                    {item.last_error && <span className="status-drop" style={{ marginLeft: 12 }}>最近错误：{item.last_error}</span>}
                  </div>
                  {health && (
                    <div className="caption">
                      健康检查：{fmtTime(health.checked_at)} ·{' '}
                      {health.ok === 1 ? (
                        <span className="status-keep">正常</span>
                      ) : (
                        <span className="status-drop">异常</span>
                      )}
                      {health.latency_ms !== null && ` · ${health.latency_ms} ms`}
                      {health.error && ` · ${health.error}`}
                    </div>
                  )}
                </div>
              </Card>
            )
          })}
        </div>
      )}
    </>
  )
}
