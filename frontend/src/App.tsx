import { useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { api } from './api/client'
import { Layout } from './components/Layout'
import { ToastProvider } from './components/ui'
import { Login } from './pages/Login'
import { Workbench } from './pages/Workbench'
import { WatchPool } from './pages/WatchPool'
import { StockDetail } from './pages/StockDetail'
import { DataSources } from './pages/DataSources'
import { Settings } from './pages/Settings'

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null)

  useEffect(() => {
    api.me().then(() => setAuthed(true)).catch(() => setAuthed(false))
  }, [])

  if (authed === null) {
    return <div className="empty-state">正在连接…</div>
  }

  return (
    <ToastProvider>
      <Routes>
        <Route path="/login" element={<Login onLogin={() => setAuthed(true)} />} />
        {authed ? (
          <Route element={<Layout onLogout={() => setAuthed(false)} />}>
            <Route path="/workbench" element={<Workbench />} />
            <Route path="/pool" element={<WatchPool />} />
            <Route path="/stocks/:code" element={<StockDetail />} />
            <Route path="/sources" element={<DataSources />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/workbench" replace />} />
          </Route>
        ) : (
          <Route path="*" element={<Navigate to="/login" replace />} />
        )}
      </Routes>
    </ToastProvider>
  )
}
