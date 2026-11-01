import type { ReactNode } from 'react'

export interface Column<T> {
  key: string
  title: ReactNode
  width?: string
  align?: 'left' | 'right'
  render?: (row: T) => ReactNode
}

interface Props<T> {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string | number
  loading?: boolean
  empty?: ReactNode
  onRowClick?: (row: T) => void
  selectedKey?: string | number | null
}

export function DataTable<T>({ columns, rows, rowKey, loading, empty, onRowClick, selectedKey }: Props<T>) {
  if (loading) {
    return (
      <div className="card-body" style={{ display: 'grid', gap: 12 }}>
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="skeleton" style={{ width: `${100 - (i % 4) * 8}%` }} />
        ))}
      </div>
    )
  }
  if (!rows.length) {
    return <div className="empty-state">{empty ?? '暂无数据'}</div>
  }
  return (
    <div className="table-wrap">
      <table className="dt">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={{ width: c.width, textAlign: c.align ?? 'left' }}>
                {c.title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = rowKey(row)
            return (
              <tr
                key={key}
                className={selectedKey === key ? 'selected' : undefined}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                style={onRowClick ? { cursor: 'pointer' } : undefined}
              >
                {columns.map((c) => (
                  <td key={c.key} className={c.align === 'right' ? 'right' : undefined}>
                    {c.render ? c.render(row) : String((row as Record<string, unknown>)[c.key] ?? '—')}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
