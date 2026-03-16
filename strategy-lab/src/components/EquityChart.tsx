import { useEffect, useRef, useMemo } from 'react'
import { createChart, ColorType, LineStyle } from 'lightweight-charts'
import type { UTCTimestamp, SeriesMarker, IChartApi } from 'lightweight-charts'
import type { EquityPoint } from '../types/api'

// Indicator names that should appear in a separate oscillator pane below the price chart
const OSCILLATOR_KEYWORDS = ['rsi', 'macd', 'stoch', 'cci', 'roc', 'momentum', 'mfi', 'adx', 'williams', 'dpo', 'trix', 'ppo']

// Fields that are NOT user-defined indicators
const KNOWN_FIELDS = new Set(['ts', 'equity', 'adj_equity', 'action', 'in_trade', 'close', 'open', 'high', 'low'])

// Colour palette for indicator lines
const INDICATOR_COLORS = ['#f59e0b', '#a78bfa', '#34d399', '#fb923c', '#60a5fa', '#f472b6', '#e879f9']

function isOscillator(name: string): boolean {
  const lower = name.toLowerCase()
  return OSCILLATOR_KEYWORDS.some(kw => lower.includes(kw))
}

function makeChart(el: HTMLDivElement, height: number): IChartApi {
  return createChart(el, {
    layout: {
      background: { type: ColorType.Solid, color: '#0f172a' },
      textColor: '#64748b',
    },
    grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
    crosshair: { vertLine: { color: '#334155' }, horzLine: { color: '#334155' } },
    rightPriceScale: { borderColor: '#1e293b' },
    timeScale: { borderColor: '#1e293b', timeVisible: true },
    width: el.clientWidth,
    height,
  })
}

function toTime(ts: string): UTCTimestamp {
  return Math.floor(new Date(ts).getTime() / 1000) as UTCTimestamp
}

// lightweight-charts requires strictly ascending timestamps with no duplicates.
// Deduplicate by keeping the last point per timestamp, then re-sort.
function dedupe<T extends { time: UTCTimestamp }>(arr: T[]): T[] {
  const map = new Map<number, T>()
  for (const item of arr) map.set(item.time as number, item)
  return [...map.values()].sort((a, b) => (a.time as number) - (b.time as number))
}

interface Props {
  data: EquityPoint[]
}

export function EquityChart({ data }: Props) {
  const priceRef   = useRef<HTMLDivElement>(null)
  const equityRef  = useRef<HTMLDivElement>(null)
  const oscRef     = useRef<HTMLDivElement>(null)

  const { overlayNames, oscNames } = useMemo(() => {
    if (data.length === 0) return { overlayNames: [], oscNames: [] }
    const indicatorKeys = Object.keys(data[0]).filter(k => !KNOWN_FIELDS.has(k))
    return {
      overlayNames: indicatorKeys.filter(k => !isOscillator(k)),
      oscNames:     indicatorKeys.filter(k =>  isOscillator(k)),
    }
  }, [data])

  // ── Price chart (close + overlay indicators + trade markers) ────────────────
  useEffect(() => {
    if (!priceRef.current || data.length === 0) return
    const chart = makeChart(priceRef.current, 450)

    // Close price — main series
    const priceSeries = chart.addLineSeries({
      color: '#22d3ee',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      title: 'Price',
    })
    priceSeries.setData(
      dedupe(
        data
          .filter(d => d.close != null)
          .map(d => ({ time: toTime(d.ts), value: d.close as number }))
      )
    )

    // Price-scale overlays (EMA, SMA, ZLEMA, …)
    overlayNames.forEach((name, i) => {
      const series = chart.addLineSeries({
        color: INDICATOR_COLORS[i % INDICATOR_COLORS.length],
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false,
        title: name,
      })
      series.setData(
        dedupe(
          data
            .filter(d => (d[name] as number | null) != null)
            .map(d => ({ time: toTime(d.ts), value: d[name] as number }))
        )
      )
    })

    // Buy / sell markers — detect actual in_trade transitions only.
    // False→True = trade opened (B), True→False = trade closed (S).
    // This correctly ignores duplicate signals that fire while already in/out of a position.
    const markers: SeriesMarker<UTCTimestamp>[] = []
    for (let i = 0; i < data.length; i++) {
      const prev = i > 0 ? !!data[i - 1].in_trade : false
      const curr = !!data[i].in_trade
      if (!prev && curr) {
        markers.push({ time: toTime(data[i].ts), position: 'belowBar', color: '#22c55e', shape: 'arrowUp', text: 'B', size: 1 })
      } else if (prev && !curr) {
        markers.push({ time: toTime(data[i].ts), position: 'aboveBar', color: '#f87171', shape: 'arrowDown', text: 'S', size: 1 })
      }
    }
    // Deduplicate markers by timestamp (keep last per ts) then sort ascending
    const markerMap = new Map<number, SeriesMarker<UTCTimestamp>>()
    for (const m of markers) markerMap.set(m.time as number, m)
    const dedupedMarkers = [...markerMap.values()].sort((a, b) => (a.time as number) - (b.time as number))

    if (dedupedMarkers.length > 0) priceSeries.setMarkers(dedupedMarkers)
    chart.timeScale().fitContent()

    const onResize = () => {
      if (priceRef.current) chart.applyOptions({ width: priceRef.current.clientWidth })
    }
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); chart.remove() }
  }, [data, overlayNames])

  // ── Equity comparison chart (strategy vs buy-and-hold) ──────────────────────
  useEffect(() => {
    if (!equityRef.current || data.length === 0) return
    const chart = makeChart(equityRef.current, 250)

    // Find first point that has both close and adj_equity
    const firstIdx = data.findIndex(d => d.close != null && d.adj_equity != null)
    if (firstIdx === -1) return

    const initialEquity = data[firstIdx].adj_equity as number
    const initialClose  = data[firstIdx].close as number

    // Strategy equity curve
    const strategySeries = chart.addLineSeries({
      color: '#818cf8',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      title: 'Strategy',
    })
    strategySeries.setData(
      dedupe(
        data
          .filter(d => d.adj_equity != null)
          .map(d => ({ time: toTime(d.ts), value: d.adj_equity as number }))
      )
    )

    // Buy-and-hold: same initial balance, passively held the asset
    const bhSeries = chart.addLineSeries({
      color: '#64748b',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceLineVisible: false,
      lastValueVisible: true,
      title: 'B&H',
    })
    bhSeries.setData(
      dedupe(
        data
          .filter(d => d.close != null)
          .map(d => ({
            time:  toTime(d.ts),
            value: initialEquity * ((d.close as number) / initialClose),
          }))
      )
    )

    chart.timeScale().fitContent()

    const onResize = () => {
      if (equityRef.current) chart.applyOptions({ width: equityRef.current.clientWidth })
    }
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); chart.remove() }
  }, [data])

  // ── Oscillator chart (RSI, MACD, …) ─────────────────────────────────────────
  useEffect(() => {
    if (!oscRef.current || data.length === 0 || oscNames.length === 0) return
    const chart = makeChart(oscRef.current, 220)

    oscNames.forEach((name, i) => {
      const series = chart.addLineSeries({
        color: INDICATOR_COLORS[i % INDICATOR_COLORS.length],
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: true,
        title: name,
      })
      series.setData(
        dedupe(
          data
            .filter(d => (d[name] as number | null) != null)
            .map(d => ({ time: toTime(d.ts), value: d[name] as number }))
        )
      )
    })

    chart.timeScale().fitContent()

    const onResize = () => {
      if (oscRef.current) chart.applyOptions({ width: oscRef.current.clientWidth })
    }
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); chart.remove() }
  }, [data, oscNames])

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[300px] text-slate-600 text-sm">
        No data — run a backtest first
      </div>
    )
  }

  return (
    <div className="space-y-px">
      {/* Legend */}
      <div className="flex flex-wrap gap-4 px-1 pb-2 text-xs">
        <span className="flex items-center gap-1.5">
          <span className="w-4 h-0.5 bg-cyan-400 inline-block rounded" />
          <span className="text-slate-400">Price</span>
        </span>
        {overlayNames.map((name, i) => (
          <span key={name} className="flex items-center gap-1.5">
            <span
              className="w-4 h-px inline-block rounded"
              style={{ backgroundColor: INDICATOR_COLORS[i % INDICATOR_COLORS.length], borderTop: `2px dashed ${INDICATOR_COLORS[i % INDICATOR_COLORS.length]}` }}
            />
            <span className="text-slate-400">{name}</span>
          </span>
        ))}
        {oscNames.map((name, i) => (
          <span key={name} className="flex items-center gap-1.5">
            <span
              className="w-4 h-0.5 inline-block rounded"
              style={{ backgroundColor: INDICATOR_COLORS[i % INDICATOR_COLORS.length] }}
            />
            <span className="text-slate-400">{name} (osc)</span>
          </span>
        ))}
        <span className="flex items-center gap-1.5">
          <span className="w-4 h-0.5 bg-indigo-400 inline-block rounded" />
          <span className="text-slate-400">Strategy</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-4 h-px inline-block rounded border-t-2 border-dashed border-slate-500" />
          <span className="text-slate-400">Buy &amp; Hold</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="text-green-400 text-xs">▲B</span>
          <span className="text-red-400 text-xs">▼S</span>
          <span className="text-slate-500">trades</span>
        </span>
      </div>

      {/* Price + overlays */}
      <div ref={priceRef} className="w-full rounded overflow-hidden" />

      {/* Equity vs Buy-and-Hold */}
      <div className="border-t border-slate-800">
        <div ref={equityRef} className="w-full rounded overflow-hidden" />
      </div>

      {/* Oscillators */}
      {oscNames.length > 0 && (
        <div className="border-t border-slate-800">
          <div ref={oscRef} className="w-full rounded overflow-hidden" />
        </div>
      )}
    </div>
  )
}
