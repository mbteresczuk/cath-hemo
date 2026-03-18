import { useEffect, useState, useRef } from 'react'
import { parseHemo } from '../api/client'

/** Shows recognized locations as chips, debounced 400ms. */
export default function ParsePreview({ text }) {
  const [parsed, setParsed] = useState(null)
  const [loading, setLoading] = useState(false)
  const timerRef = useRef(null)

  useEffect(() => {
    if (!text.trim()) { setParsed(null); return }
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(async () => {
      setLoading(true)
      try {
        const result = await parseHemo(text)
        setParsed(result)
      } catch {
        setParsed(null)
      } finally {
        setLoading(false)
      }
    }, 400)
    return () => clearTimeout(timerRef.current)
  }, [text])

  if (!parsed && !loading) return null

  const entries = Object.entries(parsed || {})

  return (
    <div style={{ marginTop: 10 }}>
      <div className="section-header">
        {loading ? 'Parsing…' : `${entries.length} location${entries.length !== 1 ? 's' : ''} recognized`}
      </div>
      {!loading && (
        <div className="chip-list">
          {entries.map(([loc, vals]) => {
            const parts = [loc]
            if (vals.sat != null) parts.push(`${vals.sat}%`)
            if (vals.systolic != null) {
              parts.push(vals.diastolic != null ? `${vals.systolic}/${vals.diastolic}` : `${vals.systolic}`)
            }
            if (vals.mean != null) parts.push(`m${vals.mean}`)
            return <span key={loc} className="chip">{parts.join(' ')}</span>
          })}
        </div>
      )}
    </div>
  )
}
