import { useEffect, useRef, useState } from 'react'
import { getLibrary, matchDiagrams } from '../api/client'

const BASE = import.meta.env.VITE_API_URL || ''

export default function DiagramSelectorScreen({ selectedDiagram, setSelectedDiagram, onBack, onGenerate }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const timerRef = useRef()

  // Load initial diagrams on mount
  useEffect(() => {
    loadAll()
  }, [])

  async function loadAll() {
    setLoading(true)
    try {
      const cats = await getLibrary()
      const all = cats.flatMap(c => c.diagrams).slice(0, 24)
      setResults(all)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  // Debounced search
  useEffect(() => {
    if (!query.trim()) { loadAll(); return }
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(async () => {
      setLoading(true)
      setError('')
      try {
        const res = await matchDiagrams(query, 20)
        setResults(res)
      } catch (e) {
        setError(e.message)
      } finally {
        setLoading(false)
      }
    }, 350)
    return () => clearTimeout(timerRef.current)
  }, [query])

  return (
    <div className="page">
      <div className="nav-row">
        <button className="btn btn-outline" style={{ padding: '8px 14px', fontSize: 14 }} onClick={onBack}>
          ← Back
        </button>
        <h2 style={{ margin: 0 }}>Select Diagram</h2>
        <div style={{ width: 70 }} />
      </div>

      {/* Search */}
      <div className="search-wrap">
        <SearchIcon />
        <input
          type="text"
          className="search-input"
          placeholder="Search diagnosis (e.g. TOF, ASD, Fontan)"
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
      </div>

      {error && <div className="alert">{error}</div>}

      {loading && (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <div className="spinner" />
        </div>
      )}

      {!loading && results.length === 0 && (
        <p style={{ textAlign: 'center', color: 'var(--muted)', paddingTop: 32 }}>
          No diagrams found.
        </p>
      )}

      <div className="diagram-grid">
        {results.map(d => (
          <div
            key={d.id}
            className={`diagram-card${selectedDiagram?.id === d.id ? ' selected' : ''}`}
            onClick={() => setSelectedDiagram(d)}
          >
            <img
              src={`${BASE}${d.thumbnail_url}`}
              alt={d.display_name}
              loading="lazy"
              onError={e => { e.target.style.opacity = 0.3 }}
            />
            <div className="diagram-card-name">{d.display_name}</div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 24 }}>
        <button
          className="btn btn-primary btn-full"
          disabled={!selectedDiagram}
          onClick={onGenerate}
        >
          Generate Report →
        </button>
        {!selectedDiagram && (
          <p style={{ textAlign: 'center', color: 'var(--muted)', fontSize: 13, marginTop: 8 }}>
            Tap a diagram to select it
          </p>
        )}
      </div>
    </div>
  )
}

function SearchIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <circle cx="11" cy="11" r="8"/>
      <path d="m21 21-4.35-4.35"/>
    </svg>
  )
}
