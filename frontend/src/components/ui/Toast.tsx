import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

type Kind = 'info' | 'warn' | 'error'
interface Item { id: number; message: string; kind: Kind }

const ToastContext = createContext<(message: string, kind?: Kind) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Item[]>([])

  const push = useCallback((message: string, kind: Kind = 'info') => {
    const id = Date.now() + Math.random()
    setItems((prev) => [...prev, { id, message, kind }])
    // 3 秒自动消失，符合 DESIGN_SPEC §5.7
    window.setTimeout(() => setItems((prev) => prev.filter((i) => i.id !== id)), 3000)
  }, [])

  const value = useMemo(() => push, [push])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack">
        {items.map((i) => (
          <div key={i.id} className={`toast-item ${i.kind}`}>{i.message}</div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
