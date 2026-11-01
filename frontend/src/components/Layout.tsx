import { useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import type { SystemStatus } from '../types'
import { fmtTime } from '../utils/format'

export function Layout({ onLogout }: { onLogout: () => void }) {
  const [status, setStatus] = useState<SystemStatus | null>(null)
  const navigate = useNavigate()

  useEffect(() => {
    api.systemStatus().then(setStatus).catch(() => setStatus(null))
  }, [])

  const logout = async () => {
    try {
      await api.logout()
    } finally {
      onLogout()
      navigate('/login')
    }
  }

  const stage = status?.pool.stage
  const sourceText = status ? `${status.sources.healthy}/${status.sources.enabled} 可用` : '—'
  const lastRun = status?.last_run

  return (
    <div className="app-shell">
      <header className="topbar">
        <span className="brand">妖股</span>
        <nav style={{ display: 'flex', gap: 20 }}>
          <NavLink to="/workbench" className={({ isActive }) => `nav-link-item${isActive ? ' active' : ''}`}>
            选股工作台
          </NavLink>
          <NavLink to="/pool" className={({ isActive }) => `nav-link-item${isActive ? ' active' : ''}`}>
            观察池
          </NavLink>
          <NavLink to="/sources" className={({ isActive }) => `nav-link-item${isActive ? ' active' : ''}`}>
            数据源
          </NavLink>
          <NavLink to="/settings" className={({ isActive }) => `nav-link-item${isActive ? ' active' : ''}`}>
            设置
          </NavLink>
        </nav>
        <div className="topbar-right">
          <span className="caption">
            上次筛选 {lastRun ? fmtTime(lastRun.finished_at ?? lastRun.started_at) : '—'}
          </span>
          <span className={`caption ${status && status.sources.healthy < status.sources.enabled ? 'status-watch' : ''}`}>
            数据源 {sourceText}
          </span>
          {stage && (
            <span className="caption">
              {stage.name} · 目标 {stage.target} 只
            </span>
          )}
          <button className="btn-ghost" onClick={logout}>退出</button>
        </div>
      </header>
      {status?.market.degraded && (
        <div className="notice notice-error" style={{ marginTop: 12 }} role="alert">
          ⚠ 行情降级：{status.market.degraded_reason ?? `最近数据为 ${status.market.latest_trade_date ?? '—'} 快照`}
          。请先恢复数据源，再用最新行情重跑筛选。
        </div>
      )}
      <main style={{ paddingTop: 8 }}>
        <Outlet />
      </main>
    </div>
  )
}
