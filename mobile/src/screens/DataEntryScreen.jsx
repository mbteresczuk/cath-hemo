import { useRef, useState } from 'react'
import { ocrImage } from '../api/client'
import ParsePreview from '../components/ParsePreview'

const PLACEHOLDER = `SVC 79
IVC 81
RA 75 10/8 9
RV 75 50/5
MPA 75 50/30 38
RPCWP 12
LA 98 10/5 8
LV 98 95/10
Aorta 98 95/55 72`

export default function DataEntryScreen({ hemoText, setHemoText, onNext }) {
  const [tab, setTab] = useState('scan')   // 'scan' | 'type'
  const [preview, setPreview] = useState(null)   // blob URL
  const [scanning, setScanning] = useState(false)
  const [scanError, setScanError] = useState('')
  const fileRef = useRef()

  async function handleFile(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setPreview(URL.createObjectURL(file))
    setScanning(true)
    setScanError('')
    try {
      const text = await ocrImage(file)
      setHemoText(text)
      setTab('type')   // switch to type tab to show/edit result
    } catch (err) {
      setScanError(`Scan failed: ${err.message}. Please type the values manually.`)
    } finally {
      setScanning(false)
    }
  }

  const canProceed = hemoText.trim().length > 0

  return (
    <div className="page">
      <h1>Enter Data</h1>
      <p style={{ color: 'var(--muted)', fontSize: 14, marginBottom: 18 }}>
        Scan a cath sheet or type the values manually.
      </p>

      <div className="tab-pills">
        <button className={`tab-pill${tab === 'scan' ? ' active' : ''}`} onClick={() => setTab('scan')}>
          Scan Sheet
        </button>
        <button className={`tab-pill${tab === 'type' ? ' active' : ''}`} onClick={() => setTab('type')}>
          Type Values
        </button>
      </div>

      {tab === 'scan' && (
        <div>
          {/* Hidden file input — opens camera on mobile */}
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            capture="environment"
            style={{ display: 'none' }}
            onChange={handleFile}
          />

          {scanning ? (
            <div className="card" style={{ textAlign: 'center', padding: 40 }}>
              <div className="spinner" />
              <p style={{ marginTop: 14, color: 'var(--muted)', fontSize: 14 }}>
                Extracting values…
              </p>
            </div>
          ) : (
            <button className="camera-btn" onClick={() => fileRef.current.click()}>
              <CameraIcon />
              Take Photo of Cath Sheet
            </button>
          )}

          {preview && !scanning && (
            <img src={preview} alt="Captured sheet" className="ocr-preview" />
          )}

          {scanError && <div className="alert">{scanError}</div>}

          {hemoText && !scanning && (
            <div className="card">
              <div className="section-header">Extracted — tap Type tab to review/edit</div>
              <pre style={{ fontSize: 12, color: 'var(--muted)', overflow: 'auto', maxHeight: 120 }}>
                {hemoText}
              </pre>
            </div>
          )}

          <p style={{ textAlign: 'center', color: 'var(--muted)', fontSize: 13, margin: '12px 0' }}>
            — or upload an existing photo —
          </p>
          <button
            className="btn btn-outline btn-full"
            onClick={() => {
              // Open file picker without camera capture
              const inp = document.createElement('input')
              inp.type = 'file'; inp.accept = 'image/*'
              inp.onchange = e => handleFile(e)
              inp.click()
            }}
          >
            Choose from Library
          </button>
        </div>
      )}

      {tab === 'type' && (
        <div>
          <label htmlFor="hemo-text">Hemodynamic Data</label>
          <textarea
            id="hemo-text"
            rows={12}
            value={hemoText}
            onChange={e => setHemoText(e.target.value)}
            placeholder={PLACEHOLDER}
            spellCheck={false}
            autoCorrect="off"
            autoCapitalize="off"
          />
          <ParsePreview text={hemoText} />
        </div>
      )}

      <div style={{ marginTop: 24 }}>
        <button
          className="btn btn-primary btn-full"
          disabled={!canProceed}
          onClick={onNext}
        >
          Select Diagram →
        </button>
      </div>
    </div>
  )
}

function CameraIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}>
      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
      <circle cx="12" cy="13" r="4"/>
    </svg>
  )
}
