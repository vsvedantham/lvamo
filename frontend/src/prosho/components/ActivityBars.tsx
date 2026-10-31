import { useState } from 'react'

export interface Bar {
  key: string
  value: number
  /** Shown in the readout on hover/focus, e.g. "Week of 13 Oct · 5 commits". */
  label: string
}

// One series, so one hue and no legend — the card title names it. Thin bars
// with 4px rounded tops on a shared baseline, a 2px gap between them, and a
// readout line that answers hover and keyboard focus (each whole column is
// the target, not just the bar).
export default function ActivityBars({ bars, summary, startLabel, endLabel, height = 72 }: {
  bars: Bar[]
  summary: string
  startLabel: string
  endLabel: string
  height?: number
}) {
  const [active, setActive] = useState<Bar | null>(null)
  const max = Math.max(1, ...bars.map(b => b.value))

  return (
    // Capped at 30px per bar so the end labels stay under the first and last bar.
    <figure style={{ margin: 0, maxWidth: `${bars.length * 30}px` }}>
      <figcaption aria-live="polite" style={{ fontSize: '0.8rem', color: active ? 'var(--text-1)' : 'var(--text-2)', minHeight: '1.2rem', marginBottom: '0.5rem' }}>
        {active ? active.label : summary}
      </figcaption>
      <div
        role="list"
        aria-label={summary}
        onMouseLeave={() => setActive(null)}
        style={{ display: 'flex', alignItems: 'flex-end', gap: '2px', height, borderBottom: '1px solid var(--border-strong)' }}
      >
        {bars.map(b => (
          <div
            key={b.key}
            role="listitem"
            tabIndex={0}
            aria-label={b.label}
            onMouseEnter={() => setActive(b)}
            onFocus={() => setActive(b)}
            onBlur={() => setActive(null)}
            style={{ flex: '1 1 0', maxWidth: '28px', height: '100%', display: 'flex', alignItems: 'flex-end', cursor: 'default', outlineOffset: '2px' }}
          >
            {b.value > 0 && (
              <div style={{
                width: '100%', height: `${Math.max(4, (b.value / max) * 100)}%`, borderRadius: '4px 4px 0 0',
                background: 'var(--accent)', opacity: active && active.key !== b.key ? 0.45 : 1, transition: 'opacity 120ms',
              }} />
            )}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: 'var(--text-3)', marginTop: '0.35rem' }}>
        <span>{startLabel}</span><span>{endLabel}</span>
      </div>
    </figure>
  )
}
