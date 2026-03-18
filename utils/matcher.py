"""
Match a free-text diagnosis to the best diagram(s) in the library.

Scoring: keyword overlap between normalized diagnosis text and diagram metadata.
"""
import re
from utils.diagram_library import get_all_diagrams

# ---------------------------------------------------------------------------
# Expanded medical abbreviation dictionary for normalization
# ---------------------------------------------------------------------------
ABBREVIATIONS = {
    r'\bhlhs\b': 'hypoplastic left heart',
    r'\bms\b': 'mitral stenosis',
    r'\bma\b': 'mitral atresia',
    r'\baa\b': 'aortic atresia',
    r'\bas\b': 'aortic stenosis',
    r'\basd\b': 'atrial septal defect',
    r'\bvsd\b': 'ventricular septal defect',
    r'\bpda\b': 'patent ductus arteriosus',
    r'\btof\b': 'tetralogy fallot',
    r'\btof\b': 'tetralogy fallot',
    r'\bdtga\b': 'd-tga',
    r'\btga\b': 'transposition great arteries',
    r'\bltga\b': 'l-tga corrected transposition',
    r'\bdorv\b': 'double outlet right ventricle',
    r'\bccavc\b': 'complete common atrioventricular canal',
    r'\bcavc\b': 'common atrioventricular canal',
    r'\bavc\b': 'atrioventricular canal',
    r'\bavcsd\b': 'atrioventricular canal',
    r'\bcoA\b': 'coarctation aorta',
    r'\bcoa\b': 'coarctation aorta',
    r'\biaa\b': 'interrupted aortic arch',
    r'\bpa\b': 'pulmonary atresia',
    r'\bpivs\b': 'pulmonary atresia intact ventricular septum',
    r'\bpa ivs\b': 'pulmonary atresia intact ventricular septum',
    r'\bnorwood\b': 'norwood',
    r'\bbts\b': 'blalock taussig shunt',
    r'\brmbts\b': 'right modified blalock taussig shunt',
    r'\bsano\b': 'sano',
    r'\bglenn\b': 'glenn',
    r'\bbdg\b': 'bidirectional glenn',
    r'\bbdgl\b': 'bidirectional glenn',
    r'\bfontan\b': 'fontan',
    r'\becff\b': 'extracardiac fenestrated fontan',
    r'\becf\b': 'extracardiac fontan',
    r'\bltff\b': 'lateral tunnel fenestrated fontan',
    r'\bltf\b': 'lateral tunnel fontan',
    r'\brastelli\b': 'rastelli',
    r'\bmustard\b': 'mustard',
    r'\bsenning\b': 'senning',
    r'\barterial switch\b': 'arterial switch',
    r'\baso\b': 'arterial switch',
    r'\bpab\b': 'pulmonary artery band',
    r'\bpa band\b': 'pulmonary artery band',
    r'\blsvc\b': 'left superior vena cava',
    r'\brsca\b': 'right subclavian artery',
    r'\blaa\b': 'left aortic arch',
    r'\braa\b': 'right aortic arch',
    r'\bwarden\b': 'warden',
    r'\bsp\b': 'status post',
    r's/p': 'status post',
    r'\brepaired\b': 'repaired status post',
    r'\bpost\b': 'status post',
    r'\bbal\b': 'balanced',
    r'\blpa\b': 'left pulmonary artery',
    r'\brpa\b': 'right pulmonary artery',
    r'\bsv\b': 'single ventricle',
}

# High-value keywords that strongly indicate a specific category
STRONG_KEYWORDS = {
    'hlhs': 15, 'hypoplastic': 15,
    'norwood': 12, 'sano': 12, 'fontan': 10, 'glenn': 10,
    'tetralogy': 12, 'fallot': 12,
    'transposition': 10, 'tga': 10, 'dtga': 10, 'mustard': 12,
    'dorv': 12, 'double outlet': 12,
    'coarctation': 10, 'interrupted': 10,
    'atresia': 8,
    'rastelli': 12, 'arterial switch': 12,
    'canal': 8, 'cavc': 10, 'ccavc': 10,
    'fenestrated': 6, 'ecff': 8, 'ltff': 8,
    'bilateral': 5, 'bilateral svc': 8,
    'lpa stenosis': 8, 'lpa stent': 8,
}


def _normalize(text: str) -> str:
    """Lowercase, expand abbreviations, remove punctuation."""
    text = text.lower()
    for pattern, replacement in ABBREVIATIONS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r'[^a-z0-9 ]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _score(diagnosis_norm: str, diagram: dict) -> int:
    """Score a diagram against a normalized diagnosis string."""
    # Build a searchable string from the diagram
    diag_str = _normalize(
        diagram.get("display_name", "") + " " +
        diagram.get("filename", "") + " " +
        diagram.get("anatomy_type", "") + " " +
        diagram.get("category_id", "")
    )

    score = 0
    diag_words = set(diagnosis_norm.split())
    diagram_words = set(diag_str.split())

    # Word-level overlap
    common = diag_words & diagram_words
    score += len(common) * 3

    # Strong keyword bonuses
    for kw, bonus in STRONG_KEYWORDS.items():
        if kw in diagnosis_norm and kw in diag_str:
            score += bonus

    # Penalize if key words in diagnosis are NOT in diagram
    for word in diag_words:
        if len(word) > 3 and word not in diagram_words:
            score -= 1

    # Extra bonus: if anatomy_type matches expected type from diagnosis
    anatomy = diagram.get("anatomy_type", "")
    if "fontan" in diagnosis_norm and anatomy == "post_fontan":
        score += 10
    if "glenn" in diagnosis_norm and anatomy == "post_glenn":
        score += 10
    if ("norwood" in diagnosis_norm or "bts" in diagnosis_norm or "sano" in diagnosis_norm) \
            and anatomy == "single_ventricle":
        score += 8
    if "mustard" in diagnosis_norm and anatomy == "post_mustard":
        score += 10
    if "biventricle" in diagnosis_norm and anatomy == "biventricle":
        score += 5

    return max(score, 0)


def match_diagrams(diagnosis: str, library: dict, top_n: int = 12) -> list:
    """
    Return the top_n best-matching diagrams for a free-text diagnosis.
    Each entry is the diagram dict with an added 'match_score' key.

    Scoring layers:
      1. Keyword overlap between normalized diagnosis and diagram metadata.
      2. Direct raw-token bonus: if the user typed e.g. "ASD" and "asd"
         appears literally in the diagram filename/display_name, add a
         large bonus so VSD/PDA diagrams don't outrank ASD-specific ones.
      3. Tie-break: prefer shorter (simpler) display names.
    """
    if not diagnosis.strip():
        return []

    norm = _normalize(diagnosis)

    # Raw tokens from the user's input for direct-match bonus
    raw_tokens = set(re.findall(r'[a-z0-9]+', diagnosis.lower()))

    diagrams = get_all_diagrams(library)

    scored = []
    for d in diagrams:
        s = _score(norm, d)

        # Direct raw-token bonus: reward diagrams whose filename / display
        # name literally contain the same short tokens the user typed.
        # This ensures "ASD" queries rank true ASD diagrams above VSD/PDA
        # diagrams that only share the "septal defect" expansion.
        target = re.sub(
            r'[^a-z0-9 ]', ' ',
            (d.get("display_name", "") + " " + d.get("filename", "")).lower()
        )
        target_tokens = set(target.split())
        for tok in raw_tokens:
            if len(tok) >= 2 and tok in target_tokens:
                s += 5

        if s > 0:
            scored.append({**d, "match_score": s})

    # Primary: score descending. Tie-break: shorter display name first
    # (simpler diagrams surface before complex multi-condition ones).
    scored.sort(key=lambda x: (-x["match_score"], len(x["display_name"])))
    return scored[:top_n]
