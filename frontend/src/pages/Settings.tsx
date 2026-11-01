import { useEffect, useState, type ReactNode } from 'react'
import { api, ApiError } from '../api/client'
import type { PoolStage, Settings as SettingsData } from '../types'
import { Button, Card, CardHead, useToast } from '../components/ui'

interface Thresholds {
  min_total_mv: number
  max_total_mv: number
  min_price: number
  max_price: number
  max_float_mv: number
  enable_float_mv: boolean
}

export function Settings() {
  const [settings, setSettings] = useState<SettingsData | null>(null)
  const [saving, setSaving] = useState(false)
  const [loadError, setLoadError] = useState('')
  const toast = useToast()

  useEffect(() => {
    api.settings().then(setSettings).catch((err) => {
      setLoadError(err instanceof ApiError ? err.message : '加载失败')
    })
  }, [])

  if (loadError) return <div className="empty-state">{loadError}</div>
  if (!settings) return <div className="empty-state">加载中…</div>

  const thresholds = settings.thresholds as unknown as Thresholds

  const patchThresholds = (patch: Partial<Thresholds>) =>
    setSettings({ ...settings, thresholds: { ...thresholds, ...patch } })

  const patchItem = (idx: number, patch: { delta?: number; weight?: number }) =>
    setSettings({
      ...settings,
      scoring: {
        ...settings.scoring,
        items: settings.scoring.items.map((it, i) => (i === idx ? { ...it, ...patch } : it)),
      },
    })

  const patchStage = (idx: number, patch: Partial<PoolStage>) =>
    setSettings({
      ...settings,
      pool: {
        ...settings.pool,
        stages: settings.pool.stages.map((s, i) => (i === idx ? { ...s, ...patch } : s)),
      },
    })

  const addStage = () =>
    setSettings({
      ...settings,
      pool: {
        ...settings.pool,
        stages: [...settings.pool.stages, { name: '新阶段', start: '01-01', end: '01-31', target: 10 }],
      },
    })

  const removeStage = (idx: number) =>
    setSettings({
      ...settings,
      pool: { ...settings.pool, stages: settings.pool.stages.filter((_, i) => i !== idx) },
    })

  const save = async () => {
    const t = settings.thresholds as unknown as Thresholds
    if (t.min_total_mv >= t.max_total_mv) {
      toast('总市值下限必须小于上限', 'warn')
      return
    }
    if (t.min_price >= t.max_price) {
      toast('收盘价下限必须小于上限', 'warn')
      return
    }
    setSaving(true)
    try {
      const res = await api.saveSettings({
        thresholds: settings.thresholds,
        scoring: settings.scoring,
        pool: settings.pool,
        schedule: settings.schedule,
      })
      setSettings(res)
      toast('配置已保存，下次筛选生效')
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '保存失败', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="actionbar">
        <h1 className="page-title">系统设置</h1>
        <Button variant="primary" loading={saving} onClick={save}>保存配置</Button>
        <span className="caption">修改门槛后需重新执行筛选才会产生新结果</span>
      </div>

      <div style={{ display: 'grid', gap: 16 }}>
        <Card>
          <CardHead title="硬门槛阈值" extra={<span className="micro">区间均含边界</span>} />
          <div className="card-body form-row">
            <Field label="总市值下限（亿元）">
              <NumInput value={thresholds.min_total_mv} onChange={(v) => patchThresholds({ min_total_mv: v })} />
            </Field>
            <Field label="总市值上限（亿元）">
              <NumInput value={thresholds.max_total_mv} onChange={(v) => patchThresholds({ max_total_mv: v })} />
            </Field>
            <Field label="收盘价下限（元）">
              <NumInput value={thresholds.min_price} onChange={(v) => patchThresholds({ min_price: v })} />
            </Field>
            <Field label="收盘价上限（元）">
              <NumInput value={thresholds.max_price} onChange={(v) => patchThresholds({ max_price: v })} />
            </Field>
            <Field label="流通市值上限（亿元）">
              <NumInput value={thresholds.max_float_mv} onChange={(v) => patchThresholds({ max_float_mv: v })} />
            </Field>
            <Field label="启用流通市值门槛">
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, height: 32 }} className="caption">
                <input
                  type="checkbox"
                  checked={thresholds.enable_float_mv}
                  onChange={(e) => patchThresholds({ enable_float_mv: e.target.checked })}
                />
                启用后流通市值缺失将被标为「待确认」
              </label>
            </Field>
          </div>
        </Card>

        <Card>
          <CardHead
            title="评分规则"
            extra={<span className="micro">满分不封顶，基准分与权重可调</span>}
          />
          <div className="card-body">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <span className="caption">基准分</span>
              <NumInput
                value={settings.scoring.base}
                onChange={(v) => setSettings({ ...settings, scoring: { ...settings.scoring, base: v } })}
                width={90}
              />
            </div>
            <div className="table-wrap" style={{ margin: '0 -16px' }}>
              <table className="dt">
                <thead>
                  <tr>
                    <th>评分项</th>
                    <th>类型</th>
                    <th style={{ width: 120 }}>分值</th>
                    <th style={{ width: 120 }}>权重</th>
                    <th>数据来源</th>
                  </tr>
                </thead>
                <tbody>
                  {settings.scoring.items.map((it, idx) => (
                    <tr key={it.key}>
                      <td>{it.label}</td>
                      <td>
                        <span className={it.type === 'add' ? 'up' : 'down'}>
                          {it.type === 'add' ? '加分' : '减分'}
                        </span>
                      </td>
                      <td>
                        <NumInput value={it.delta} onChange={(v) => patchItem(idx, { delta: v })} width={80} />
                      </td>
                      <td>
                        <NumInput value={it.weight} onChange={(v) => patchItem(idx, { weight: v })} width={80} />
                      </td>
                      <td className="caption">{it.source === 'manual' ? '人工补录' : '自动计算'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Card>

        <Card>
          <CardHead
            title="观察池与阶段目标"
            extra={<Button onClick={addStage}>新增阶段</Button>}
          />
          <div className="card-body">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
              <span className="caption">池容量</span>
              <NumInput
                value={settings.pool.capacity}
                onChange={(v) => setSettings({ ...settings, pool: { ...settings.pool, capacity: v } })}
                width={90}
              />
              <span className="micro">达到容量后加入观察池会失败，需先淘汰</span>
            </div>
            <div className="table-wrap" style={{ margin: '0 -16px' }}>
              <table className="dt">
                <thead>
                  <tr>
                    <th>阶段</th>
                    <th style={{ width: 110 }}>开始（MM-DD）</th>
                    <th style={{ width: 110 }}>结束（MM-DD）</th>
                    <th style={{ width: 110 }}>目标只数</th>
                    <th style={{ width: 80 }} />
                  </tr>
                </thead>
                <tbody>
                  {settings.pool.stages.map((s, idx) => (
                    <tr key={idx}>
                      <td>
                        <TextInput value={s.name} onChange={(v) => patchStage(idx, { name: v })} />
                      </td>
                      <td>
                        <TextInput value={s.start} onChange={(v) => patchStage(idx, { start: v })} width={90} />
                      </td>
                      <td>
                        <TextInput value={s.end} onChange={(v) => patchStage(idx, { end: v })} width={90} />
                      </td>
                      <td>
                        <NumInput value={s.target} onChange={(v) => patchStage(idx, { target: v })} width={80} />
                      </td>
                      <td>
                        <Button variant="ghost" onClick={() => removeStage(idx)}>删除</Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="micro" style={{ marginTop: 8 }}>
              跨年阶段（如 12-01 至 01-10）按自然年份循环匹配。题材池一期由种子数据维护，暂不支持页面编辑。
            </p>
          </div>
        </Card>

        <Card>
          <CardHead title="定时任务" />
          <div className="card-body form-row">
            <Field label="每日自动刷新">
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, height: 32 }} className="caption">
                <input
                  type="checkbox"
                  checked={settings.schedule.enabled}
                  onChange={(e) =>
                    setSettings({ ...settings, schedule: { ...settings.schedule, enabled: e.target.checked } })
                  }
                />
                工作日收盘后自动抓取行情并筛选
              </label>
            </Field>
            <Field label="执行时间（HH:MM）">
              <TextInput
                value={settings.schedule.refresh_time}
                onChange={(v) => setSettings({ ...settings, schedule: { ...settings.schedule, refresh_time: v } })}
                width={100}
              />
            </Field>
          </div>
        </Card>

        <PasswordCard />
      </div>
    </>
  )
}

function PasswordCard() {
  const [oldPwd, setOldPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [confirm, setConfirm] = useState('')
  const [saving, setSaving] = useState(false)
  const toast = useToast()

  const submit = async () => {
    if (newPwd.length < 8) {
      toast('新密码至少 8 位', 'warn')
      return
    }
    if (newPwd !== confirm) {
      toast('两次输入的新密码不一致', 'warn')
      return
    }
    setSaving(true)
    try {
      await api.changePassword(oldPwd, newPwd)
      toast('密码已修改，请重新登录')
      window.setTimeout(() => window.location.assign('/login'), 800)
    } catch (err) {
      toast(err instanceof ApiError ? err.message : '修改失败', 'error')
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHead title="访问密码" />
      <div className="card-body form-row">
        <Field label="原密码">
          <TextInput type="password" value={oldPwd} onChange={setOldPwd} />
        </Field>
        <Field label="新密码（至少 8 位）">
          <TextInput type="password" value={newPwd} onChange={setNewPwd} />
        </Field>
        <Field label="确认新密码">
          <TextInput type="password" value={confirm} onChange={setConfirm} />
        </Field>
        <div style={{ display: 'flex', alignItems: 'flex-end' }}>
          <Button variant="primary" loading={saving} onClick={submit}>修改密码</Button>
        </div>
      </div>
    </Card>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <span className="field-label">{label}</span>
      {children}
    </div>
  )
}

/** 数字输入用本地字符串缓冲，避免受控 number 在输入小数时被强制格式化。 */
function NumInput({
  value, onChange, width,
}: { value: number; onChange: (v: number) => void; width?: number }) {
  const [text, setText] = useState(String(value))
  useEffect(() => { setText(String(value)) }, [value])

  const commit = () => {
    const n = Number(text)
    if (Number.isFinite(n)) onChange(n)
    else setText(String(value))
  }

  return (
    <input
      className="input-dark num"
      style={{ width: width ?? 140 }}
      inputMode="decimal"
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur() }}
    />
  )
}

function TextInput({
  value, onChange, width, type = 'text',
}: { value: string; onChange: (v: string) => void; width?: number; type?: string }) {
  return (
    <input
      className="input-dark"
      type={type}
      style={{ width: width ?? 180 }}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}
