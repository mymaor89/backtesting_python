import { useEffect, useRef, useMemo } from 'react'
import { createChart, ColorType, LineStyle } from 'lightweight-charts'
import type { UTCTimestamp, SeriesMarker, IChartApi } from 'lightweight-charts'
import type { EquityPoint } from '../types/api'

// Indicator names that should appear in a separate oscillator pane below the price chart
const OSCILLATOR_KEYWORDS = ['rsi', 'macd', 'stoch', 'cci', 'roc', 'momentum', 'mfi', 'adx', 'williams', 'dpo', 'trix', 'ppo']

// Fields that are NOT user-defined indicators
const KNOWN_FIELDS = new Set(['ts', 'equity', 'adj_equity', 'action', 'close', 'open', 'high', 'low'])

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

interface Props {
  data: EquityPoint[]
}

export function EquityChart({ data }: Props) {
  const priceRef = useRef<HTMLDivElement>(null)
  const oscRef = useRef<HTMLDivElement>(null)

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
    const chart = makeChart(priceRef.current, 300)

    // Close price — main series
    const priceSeries = chart.addLineSeries({
      color: '#22d3ee',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      title: 'Price',
    })
    priceSeries.setData(
      data
        .filter(d => d.close != null)
        .map(d => ({ time: toTime(d.ts), value: d.close as number })),
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
        data
          .filter(d => (d[name] as number | null) != null)
          .map(d => ({ time: toTime(d.ts), value: d[name] as number })),
      )
    })

    // Buy / sell markers
    const markers: SeriesMarker<UTCTimestamp>[] = data
      .filter(d => d.action !== 'h')
      .map(d => ({
        time: toTime(d.ts),
        position: d.action === 'e' ? ('belowBar' as const) : ('aboveBar' as const),
        color: d.action === 'e' ? '#22c55e' : '#f87171',
        shape: d.action === 'e' ? ('arrowUp' as const) : ('arrowDown' as const),
        text: d.action === 'e' ? 'B' : 'S',
        size: 1,
      }))
      .sort((a, b) => (a.time as number) - (b.time as number))

    if (markers.length > 0) priceSeries.setMarkers(markers)
    chart.timeScale().fitContent()

    const onResize = () => {
      if (priceRef.current) chart.applyOptions({ width: priceRef.current.clientWidth })
    }
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); chart.remove() }
  }, [data, overlayNames])

  // ── Oscillator chart (RSI, MACD, …) ─────────────────────────────────────────
  useEffect(() => {
    if (!oscRef.current || data.length === 0 || oscNames.length === 0) return
    const chart = makeChart(oscRef.current, 160)

    oscNames.forEach((name, i) => {
      const series = chart.addLineSeries({
        color: INDICATOR_COLORS[i % INDICATOR_COLORS.length],
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: true,
        title: name,
      })
      series.setData(
        data
          .filter(d => (d[name] as number | null) != null)
          .map(d => ({ time: toTime(d.ts), value: d[name] as number })),
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
          <span className="text-green-400 text-xs">▲B</span>
          <span className="text-red-400 text-xs">▼S</span>
          <span className="text-slate-500">trades</span>
        </span>
      </div>

      {/* Price + overlays */}
      <div ref={priceRef} className="w-full rounded overflow-hidden" />

      {/* Oscillators */}
      {oscNames.length > 0 && (
        <div className="border-t border-slate-800">
          <div ref={oscRef} className="w-full rounded overflow-hidden" />
        </div>
      )}
    </div>
  )
}
