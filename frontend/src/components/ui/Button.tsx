import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'default' | 'ghost' | 'danger'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  loading?: boolean
  children: ReactNode
}

const CLASS: Record<Variant, string> = {
  primary: 'btn-primary-dark',
  default: 'btn-dark',
  ghost: 'btn-ghost',
  danger: 'btn-danger-ghost',
}

export function Button({ variant = 'default', loading, children, disabled, ...rest }: Props) {
  return (
    <button className={CLASS[variant]} disabled={disabled || loading} {...rest}>
      {loading ? '处理中…' : children}
    </button>
  )
}
