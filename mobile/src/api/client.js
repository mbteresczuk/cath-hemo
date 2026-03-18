/**
 * All API calls to the FastAPI backend.
 * In development, Vite proxies /api and /diagrams to localhost:8000.
 * In production, set VITE_API_URL to the deployed backend URL.
 */

const BASE = import.meta.env.VITE_API_URL || ''

async function checkOk(res) {
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try { const j = await res.json(); msg = j.detail || msg } catch {}
    throw new Error(msg)
  }
  return res.json()
}

/** POST an image file and return extracted hemodynamic text. */
export async function ocrImage(file) {
  const form = new FormData()
  form.append('image', file)
  const res = await fetch(`${BASE}/api/ocr`, { method: 'POST', body: form })
  const data = await checkOk(res)
  return data.text   // string
}

/** Parse free-text hemo data into a structured dict. */
export async function parseHemo(text, extraLocations = null) {
  const res = await fetch(`${BASE}/api/parse`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, extra_locations: extraLocations }),
  })
  const data = await checkOk(res)
  return data.parsed  // dict
}

/** Search diagrams by diagnosis text. Returns array of diagram objects. */
export async function matchDiagrams(query, topN = 12) {
  const params = new URLSearchParams({ q: query, top_n: topN })
  const res = await fetch(`${BASE}/api/diagrams/match?${params}`)
  const data = await checkOk(res)
  return data.results   // array
}

/** Get the full diagram library. */
export async function getLibrary() {
  const res = await fetch(`${BASE}/api/diagrams`)
  const data = await checkOk(res)
  return data.categories  // array of category objects
}

/**
 * Generate annotated diagram + narrative + calculations.
 * Returns { annotated_image_b64, narrative, calculations, step_ups, parsed }
 */
export async function generateReport({ hemoText, diagramId, patientData, extraLocations }) {
  const res = await fetch(`${BASE}/api/report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      hemo_text: hemoText,
      diagram_id: diagramId,
      patient_data: patientData,
      extra_locations: extraLocations || null,
    }),
  })
  return checkOk(res)
}
