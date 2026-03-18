import { useState } from 'react'
import DataEntryScreen from './screens/DataEntryScreen'
import DiagramSelectorScreen from './screens/DiagramSelectorScreen'
import OutputScreen from './screens/OutputScreen'

// Patient defaults stored in localStorage
function loadPatientData() {
  try {
    return JSON.parse(localStorage.getItem('patientDefaults') || '{}')
  } catch { return {} }
}

function mergePatientData(updates) {
  const current = loadPatientData()
  const merged = { ...current, ...updates }
  localStorage.setItem('patientDefaults', JSON.stringify(merged))
  return merged
}

const DEFAULT_PATIENT = {
  hgb: 12.0,
  avo2: 125,
  anesthesia: 'general anesthesia',
  anatomy_type: 'biventricle',
  fio2: '21%',
}

export default function App() {
  const [screen, setScreen] = useState('entry')    // 'entry' | 'selector' | 'output'
  const [hemoText, setHemoText] = useState('')
  const [selectedDiagram, setSelectedDiagram] = useState(null)
  const patientData = { ...DEFAULT_PATIENT, ...loadPatientData() }

  function reset() {
    setHemoText('')
    setSelectedDiagram(null)
    setScreen('entry')
  }

  function handleGenerate() {
    // Update anatomy_type from selected diagram
    if (selectedDiagram?.anatomy_type) {
      mergePatientData({ anatomy_type: selectedDiagram.anatomy_type })
    }
    setScreen('output')
  }

  return (
    <>
      {screen === 'entry' && (
        <DataEntryScreen
          hemoText={hemoText}
          setHemoText={setHemoText}
          onNext={() => setScreen('selector')}
        />
      )}

      {screen === 'selector' && (
        <DiagramSelectorScreen
          selectedDiagram={selectedDiagram}
          setSelectedDiagram={setSelectedDiagram}
          onBack={() => setScreen('entry')}
          onGenerate={handleGenerate}
        />
      )}

      {screen === 'output' && (
        <OutputScreen
          hemoText={hemoText}
          diagram={selectedDiagram}
          patientData={patientData}
          onReset={reset}
        />
      )}

      {/* Bottom tab bar (visual only — navigation is driven by screen state above) */}
      <nav className="tab-bar">
        <button className={`tab-btn${screen === 'entry' ? ' active' : ''}`} onClick={() => setScreen('entry')}>
          <EditIcon />
          Enter Data
        </button>
        <button className={`tab-btn${screen === 'selector' ? ' active' : ''}`} onClick={() => setScreen('selector')}>
          <GridIcon />
          Diagrams
        </button>
        <button
          className={`tab-btn${screen === 'output' ? ' active' : ''}`}
          disabled={!selectedDiagram || !hemoText}
          onClick={handleGenerate}
        >
          <ReportIcon />
          Report
        </button>
      </nav>
    </>
  )
}

function EditIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
    </svg>
  )
}

function GridIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/>
      <rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/>
    </svg>
  )
}

function ReportIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <line x1="16" y1="13" x2="8" y2="13"/>
      <line x1="16" y1="17" x2="8" y2="17"/>
      <polyline points="10 9 9 9 8 9"/>
    </svg>
  )
}
