import { useEffect, useState } from 'react'
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch'
import { generateReport } from '../api/client'

export default function OutputScreen({ hemoText, diagram, patientData, onReset }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    run()
  }, [])

  async function run() {
    setLoading(true)
    setError('')
    try {
      const data = await generateReport({
        hemoText,
        diagramId: diagram.id,
        patientData,
      })
      setResult(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function copyNarrative() {
    if (!result?.narrative) return
    try {
      await navigator.clipboard.writeText(result.narrative)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback for browsers that block clipboard
      const el = document.createElement('textarea')
      el.value = result.narrative
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  async function shareImage() {
    if (!result?.annotated_image_b64) return
    const dataUrl = `data:image/png;base64,${result.annotated_image_b64}`
    const res = await fetch(dataUrl)
    const blob = await res.blob()
    const file = new File([blob], 'cath_diagram.png', { type: 'image/png' })

    if (navigator.canShare?.({ files: [file] })) {
      await navigator.share({ files: [file], title: 'Cath Diagram' })
    } else {
      // Fallback: trigger download
      const a = document.createElement('a')
      a.href = dataUrl; a.download = 'cath_diagram.png'; a.click()
    }
  }

  async function shareAll() {
    if (!result) return
    const text = result.narrative || ''
    if (navigator.share) {
      await navigator.share({ title: 'Hemodynamic Report', text })
    } else {
      await navigator.clipboard.writeText(text)
    }
  }

  if (loading) {
    return (
      <div className="page" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 16 }}>
        <div className="spinner" style={{ width: 40, height: 40, borderWidth: 4 }} />
        <p style={{ color: 'var(--muted)', fontSize: 15 }}>Generating report…</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page">
        <div className="alert" style={{ background: '#FEE2E2', borderColor: '#F87171' }}>
          <strong>Error:</strong> {error}
        </div>
        <button className="btn btn-outline btn-full" onClick={run}>Retry</button>
        <button className="btn btn-secondary btn-full" style={{ marginTop: 10 }} onClick={onReset}>
          ← Start Over
        </button>
      </div>
    )
  }

  const calcs = result?.calculations || {}
  const stepUps = result?.step_ups || []

  return (
    <div className="page">
      {/* Diagram */}
      <h2>Annotated Diagram</h2>
      <div style={{ borderRadius: 12, overflow: 'hidden', border: '1px solid var(--border)', marginBottom: 14, background: '#fff' }}>
        <TransformWrapper minScale={1} maxScale={5} wheel={{ disabled: true }}>
          <TransformComponent wrapperStyle={{ width: '100%' }} contentStyle={{ width: '100%' }}>
            <img
              src={`data:image/png;base64,${result.annotated_image_b64}`}
              alt="Annotated diagram"
              style={{ width: '100%', display: 'block' }}
            />
          </TransformComponent>
        </TransformWrapper>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <button className="btn btn-outline" style={{ flex: 1, fontSize: 13 }} onClick={shareImage}>
          Save Image
        </button>
        <button className="btn btn-secondary" style={{ flex: 1, fontSize: 13 }} onClick={shareAll}>
          Share Report
        </button>
      </div>

      {/* Step-up alerts */}
      {stepUps.length > 0 && (
        <>
          <div className="section-header">Step-up Alerts</div>
          {stepUps.map((s, i) => (
            <div key={i} className="alert">
              {s.level?.charAt(0).toUpperCase() + s.level?.slice(1)} step-up: {s.from} {s.from_sat}% → {s.to} {s.to_sat}% (Δ{s.delta?.toFixed(1)}%)
            </div>
          ))}
        </>
      )}

      {/* Calculations */}
      <div className="section-header">Calculations (Fick Method)</div>
      <div className="card" style={{ padding: '4px 0' }}>
        <table>
          <thead>
            <tr><th>Parameter</th><th>Value</th><th>Units</th></tr>
          </thead>
          <tbody>
            {calcs.qs != null && <tr><td>Qs</td><td>{calcs.qs.toFixed(2)}</td><td>L/min/m²</td></tr>}
            {calcs.qp != null && <tr><td>Qp</td><td>{calcs.qp.toFixed(2)}</td><td>L/min/m²</td></tr>}
            {calcs.qp_qs != null && <tr><td>Qp:Qs</td><td>{calcs.qp_qs.toFixed(2)}:1</td><td></td></tr>}
            {calcs.pvri != null && <tr><td>PVRi</td><td>{calcs.pvri.toFixed(2)}</td><td>iWU</td></tr>}
            {calcs.svri != null && <tr><td>SVRi</td><td>{calcs.svri.toFixed(2)}</td><td>iWU</td></tr>}
            {calcs.rp_rs != null && <tr><td>Rp/Rs</td><td>{calcs.rp_rs.toFixed(3)}</td><td></td></tr>}
            {calcs.tpg != null && <tr><td>TPG</td><td>{calcs.tpg.toFixed(0)}</td><td>mmHg</td></tr>}
          </tbody>
        </table>
      </div>

      {/* Narrative */}
      <div className="section-header">Hemodynamics Narrative</div>
      <div className="card">
        <p className="narrative-text">{result.narrative}</p>
      </div>
      <button className="btn btn-outline btn-full" style={{ marginTop: -4, marginBottom: 14 }} onClick={copyNarrative}>
        {copied ? '✓ Copied!' : 'Copy Narrative'}
      </button>

      {/* Calculation warnings */}
      {calcs.warnings?.length > 0 && (
        <>
          <div className="section-header">Notes</div>
          {calcs.warnings.map((w, i) => (
            <div key={i} className="alert" style={{ marginBottom: 6 }}>{w}</div>
          ))}
        </>
      )}

      <button className="btn btn-secondary btn-full" style={{ marginTop: 12 }} onClick={onReset}>
        ← New Report
      </button>
    </div>
  )
}
