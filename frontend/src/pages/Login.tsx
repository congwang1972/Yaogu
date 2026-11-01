import { useState } from 'react'
import { api, ApiError } from '../api/client'

export function Login({ onLogin }: { onLogin: () => void }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await api.login(password)
      onLogin()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '服务暂不可用，请稍后重试')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <div className="brand" style={{ fontSize: 22, marginBottom: 4 }}>妖股</div>
        <p className="caption" style={{ marginBottom: 24 }}>跨年总龙选股与跟踪工作台</p>

        <label className="field-label" htmlFor="pwd">访问密码</label>
        <input
          id="pwd"
          className="input-dark"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={{ width: '100%', height: 40, marginBottom: 12 }}
          autoFocus
        />
        {error && <div className="notice notice-error" style={{ marginBottom: 12 }}>{error}</div>}

        <button className="btn-primary-dark" type="submit" disabled={loading || !password}
          style={{ width: '100%', height: 40 }}>
          {loading ? '登录中…' : '登录'}
        </button>

        <p className="micro" style={{ marginTop: 20, lineHeight: 1.6 }}>
          本工具仅做历史规律复盘，不构成任何投资建议。
        </p>
      </form>
    </div>
  )
}
