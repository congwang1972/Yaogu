import type { ReactNode } from 'react'

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`card-dark ${className}`}>{children}</section>
}

export function CardHead({ title, extra }: { title: ReactNode; extra?: ReactNode }) {
  return (
    <header className="card-head">
      <h2 style={{ fontSize: 16, fontWeight: 600, margin: 0 }}>{title}</h2>
      {extra}
    </header>
  )
}

export function CardBody({ children }: { children: ReactNode }) {
  return <div className="card-body">{children}</div>
}
