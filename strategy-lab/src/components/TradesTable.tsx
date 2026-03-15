import type { Trade } from '../types/api'

interface Props {
  trades: Trade[]
}

const fmtCell = (col: string, v: unknown): string => {
  if (v == null) return '—'
  if (col.includes('date') || col.includes('ts') || col.includes('time')) {
    try {
      return new Date(String(v)).toLocaleString()
    } catch {
      return String(v)
    }
  }
  if (typeof v === 'number') return isFinite(v) ? v.toFixed(4) : '—'
  return String(v)
}

const isPnlCol = (col: string) => col.includes('pnl') || col.includes('change')

export function TradesTable({ trades }: Props) {
  if (trades.length === 0) {
    return (
      <div className="flex items-center justify-center h-[200px] text-slate-600 text-sm">
        No trades
      </div>
    )
  }

  const cols = Object.keys(trades[0])

  return (
    <div className="overflow-auto max-h-[400px]">
      <table className="w-full text-xs">
        <thead className="sticky top-0 bg-slate-900 z-10">
          <tr>
            {cols.map(col => (
              <th
                key={col}
                className="px-3 py-2 text-left text-slate-500 border-b border-slate-800 whitespace-nowrap font-medium"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {trades.map((trade, i) => (
            <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
              {cols.map(col => {
                const v = (trade as Record<string, unknown>)[col]
                const numVal = typeof v === 'number' ? v : null
                const isPnl = isPnlCol(col)
                const colorClass = isPnl && numVal != null
                  ? numVal > 0 ? 'text-green-400' : numVal < 0 ? 'text-red-400' : 'text-slate-300'
                  : 'text-slate-300'
                return (
                  <td key={col} className={`px-3 py-2 whitespace-nowrap ${colorClass}`}>
                    {fmtCell(col, v)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
