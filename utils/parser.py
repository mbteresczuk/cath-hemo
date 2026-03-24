"""
Parse free-text hemodynamic data from a cath report paste.

Handles multiple formats from cath lab systems:
  SVC 79
  RA 74 10/8 m9
  RV 79% 34/4
  MPA 80 34/10/21
  RPCWP 17/12 14
  LV 97 82/12
  Ao 98 97/45 65

Returns a dict keyed by canonical location name.
"""
import re

# ---------------------------------------------------------------------------
# Canonical location names and all their aliases (upper-cased for matching)
# ---------------------------------------------------------------------------
LOCATION_ALIASES = {
    "SVC": ["SVC", "SUPERIOR VENA CAVA", "SUP VENA CAVA", "SUP VC"],
    "IVC": ["IVC", "INFERIOR VENA CAVA", "INF VENA CAVA", "INF VC"],
    "RA":  ["RA", "RIGHT ATRIUM", "R ATRIUM", "RT ATRIUM", "RT RA"],
    "RV":  ["RV", "RIGHT VENTRICLE", "R VENTRICLE", "RT VENTRICLE",
            "RVOT", "RV APEX", "RV BODY", "RVOTO"],
    "MPA": ["MPA", "PA", "MAIN PA", "MAIN PULM", "MAIN PULMONARY",
            "PULMONARY ARTERY", "PULM ART", "MP", "PAP"],
    "RPA": ["RPA", "RIGHT PA", "R PA", "RT PA", "RIGHT PULMONARY",
            "RIGHT PULM", "R PULM"],
    "LPA": ["LPA", "LEFT PA", "L PA", "LEFT PULMONARY", "LEFT PULM",
            "L PULM"],
    "RPCWP": ["RPCWP", "RCWP", "RPCW", "RPWP", "RIGHT WEDGE",
              "R WEDGE", "RIGHT PCW", "RIGHT PCWP", "RT WEDGE",
              "RT PCW", "RT PCWP", "RPCWP"],
    "LPCWP": ["LPCWP", "LCWP", "LPCW", "LPWP", "LEFT WEDGE",
              "L WEDGE", "LEFT PCW", "LEFT PCWP", "LT WEDGE",
              "LT PCW", "LT PCWP", "PCWP", "PCW", "WEDGE", "CWP"],
    "LA":  ["LA", "LEFT ATRIUM", "L ATRIUM", "LT ATRIUM",
            "LEFT AT", "L AT"],
    "LV":  ["LV", "LEFT VENTRICLE", "L VENTRICLE", "LT VENTRICLE",
            "LEFT VENT", "L VENT", "LT VENT"],
    "Descending_Aorta": ["AO", "AORTA", "AORTIC", "AORTIC ARCH",
                         "DESC AO", "DESC AORTA", "DESCENDING AO", "DAO"],
    "Neoaorta":         ["NEO", "NEOAORTA", "NEO AO", "NEO-AO", "NEOAO"],
    "Glenn_anastomosis":["GLENN", "BDGL", "BDG", "BILATERAL GLENN",
                         "BILATERAL BDG", "BIDIRECTIONAL GLENN"],
    "Fontan_IVC_limb":  ["FONTAN", "IVC LIMB", "FONTAN CIRCUIT",
                          "FONTAN IVC", "IVC FONTAN"],
    "RV_systemic":      ["RV SYSTEMIC", "SYSTEMIC RV", "SRV"],
    "LV_systemic":      ["LV SYSTEMIC", "SYSTEMIC LV", "SLV"],
    "LV_pulmonary":     ["LV PULMONARY", "PULM LV", "PLV"],
    "Venous_atrium":    ["VENOUS ATRIUM", "VEN ATRIUM", "VA"],
    "Arterial_atrium":  ["ARTERIAL ATRIUM", "ART ATRIUM", "AA"],
    # Extra locations for per-diagram customization
    "Ascending_Aorta":  ["ASC AO", "ASC AORTA", "ASCENDING AO", "AAO"],
    "BTS":              ["BTS", "BT SHUNT", "BLALOCK"],
    "Sano_conduit":     ["SANO", "SANO CONDUIT", "RV-PA CONDUIT", "RVPA"],
    "Fontan_conduit":   ["FONTAN CONDUIT", "FONTAN BAFFLE", "FONTAN TUNNEL",
                          "EXTRACARDIAC FONTAN", "LATERAL TUNNEL"],
    "LSVC":             ["LSVC", "LEFT SVC", "L SVC", "LT SVC",
                          "LEFT SUPERIOR VENA CAVA"],
    "Coronary_sinus":   ["CS", "CORONARY SINUS", "COR SINUS"],
    "Innominate_vein":  ["INNOMINATE", "INNOMINATE VEIN", "INNOM",
                          "BRACHIOCEPHALIC", "BRACHIOCEPHALIC VEIN"],
    "Hepatic_vein":     ["HV", "HEPATIC VEIN", "HEPATIC", "HEP VEIN"],
    "Azygos_vein":      ["AZYGOS", "AZYGOS VEIN", "AZ VEIN"],
    "RVOT":             ["RVOT", "RV OUTFLOW", "RV OUTFLOW TRACT"],
    "LVOT":             ["LVOT", "LV OUTFLOW", "LV OUTFLOW TRACT"],
    "Conduit":          ["CONDUIT", "RV PA CONDUIT"],
    "PV_confluence":    ["PV CONFLUENCE", "PULM VEIN CONFLUENCE",
                          "PULMONARY VEIN CONFLUENCE"],
    "Baffle":           ["BAFFLE", "ATRIAL BAFFLE"],
    "RV_body":          ["RV BODY"],
    "RV_apex":          ["RV APEX"],
    "RPV":              ["RPV", "RIGHT PULM VEIN", "RIGHT PULMONARY VEIN",
                          "R PULM VEIN"],
    "LPV":              ["LPV", "LEFT PULM VEIN", "LEFT PULMONARY VEIN",
                          "L PULM VEIN"],
    "RUPV":             ["RUPV", "RIGHT UPPER PV", "R UPPER PV", "RT UPPER PV",
                          "RIGHT UPPER PULM VEIN", "RIGHT UPPER PULMONARY VEIN"],
    "LUPV":             ["LUPV", "LEFT UPPER PV", "L UPPER PV", "LT UPPER PV",
                          "LEFT UPPER PULM VEIN", "LEFT UPPER PULMONARY VEIN"],
    "RLPV":             ["RLPV", "RIGHT LOWER PV", "R LOWER PV", "RT LOWER PV",
                          "RIGHT LOWER PULM VEIN", "RIGHT LOWER PULMONARY VEIN"],
    "LLPV":             ["LLPV", "LEFT LOWER PV", "L LOWER PV", "LT LOWER PV",
                          "LEFT LOWER PULM VEIN", "LEFT LOWER PULMONARY VEIN"],
}

# Locations that DO NOT have oxygen saturations.
# A lone number at these locations is interpreted as a mean pressure, not systolic.
PRESSURE_ONLY = {
    "RPCWP", "LPCWP",
    # Glenn anastomosis — pressure only (no saturation measured here)
    "Glenn_anastomosis",
    # Generic PV confluence — pressure only (no individual PV sats)
    "RPV", "LPV", "PV_confluence",
    # Note: individual pulmonary veins (RUPV/LUPV/RLPV/LLPV) are NOT listed here
    # because they DO have measurable O₂ saturations that should display as circles.
    # A lone value ≥40 is treated as a saturation; a value <40 becomes a mean pressure.
    #
    # Fontan_IVC_limb and Fontan_conduit are intentionally NOT listed here —
    # Fontan limb saturations are clinically important and must be captured.
    # A value entered alongside a pressure (e.g. "Fontan 62 12") is: sat=62, mean=12.
}

# ---------------------------------------------------------------------------
# Build reverse lookup: ALIAS_UPPER → canonical name
# ---------------------------------------------------------------------------
_ALIAS_MAP: dict = {}
for canonical, aliases in LOCATION_ALIASES.items():
    for alias in aliases:
        _ALIAS_MAP[alias.upper()] = canonical

# Also allow canonical names typed directly (e.g. "Ascending_Aorta" or
# "Ascending Aorta") — covers all standard + extra locations without
# requiring the user to know the shorthand alias.
for canonical in list(LOCATION_ALIASES.keys()):
    _ALIAS_MAP.setdefault(canonical.upper(), canonical)
    _ALIAS_MAP.setdefault(canonical.replace("_", " ").upper(), canonical)


def _find_location(token_list, start=0):
    """
    Try to match 1, 2, or 3 consecutive tokens to a known location alias.
    Returns (canonical_name, tokens_consumed) or (None, 0).
    Tries longer matches first.
    """
    for length in (3, 2, 1):
        candidate = " ".join(token_list[start : start + length]).upper()
        if candidate in _ALIAS_MAP:
            return _ALIAS_MAP[candidate], length
    return None, 0


def _parse_numbers(tokens):
    """
    Given a list of string tokens (after the location name has been removed),
    extract: sat, systolic, diastolic, mean.

    Rules:
    - Token like  X/Y        → systolic=X, diastolic=Y
    - Token like  X/Y/Z      → systolic=X, diastolic=Y, mean=Z
    - Token like  mXX or mXX → mean=XX   (m prefix)
    - Bare number 40–100     → saturation candidate (first one wins)
    - Bare number            → fill systolic → diastolic → mean in order
    """
    sat = systolic = diastolic = mean = None

    for tok in tokens:
        tok = tok.strip().rstrip('%').strip()
        if not tok:
            continue

        # m-prefixed mean
        m = re.fullmatch(r'm(\d+\.?\d*)', tok, re.IGNORECASE)
        if m:
            mean = float(m.group(1))
            continue

        # Slash-separated: X/Y or X/Y/Z
        sl = re.fullmatch(r'(\d+\.?\d*)/(\d+\.?\d*)(?:/(\d+\.?\d*))?', tok)
        if sl:
            systolic = float(sl.group(1))
            diastolic = float(sl.group(2))
            if sl.group(3):
                mean = float(sl.group(3))
            continue

        # Bare number
        nb = re.fullmatch(r'(\d+\.?\d*)', tok)
        if nb:
            val = float(nb.group(1))
            if sat is None and systolic is None and 40 <= val <= 100:
                sat = val
            elif systolic is None:
                systolic = val
            elif diastolic is None:
                diastolic = val
            elif mean is None:
                mean = val
            continue

    result = {}
    if sat is not None:
        result["sat"] = sat
    if systolic is not None:
        result["systolic"] = systolic
    if diastolic is not None:
        result["diastolic"] = diastolic
    if mean is not None:
        result["mean"] = mean
    return result


def _find_custom_location(token_list, start, extra_locations):
    """
    Fallback: try to match tokens against a list of custom location names
    (those not registered in LOCATION_ALIASES).
    Accepts both the underscore form (e.g. "Hepatic_vein") and the
    space-separated display form (e.g. "Hepatic vein").
    Returns (canonical_name, tokens_consumed) or (None, 0).
    """
    for length in (3, 2, 1):
        if start + length > len(token_list):
            continue
        candidate = " ".join(token_list[start : start + length])
        for extra in extra_locations:
            if (candidate.upper() == extra.upper()
                    or candidate.upper() == extra.replace("_", " ").upper()):
                return extra, length
    return None, 0


def _collect_entries(text: str, extra_locations: list = None) -> dict:
    """
    Parse hemodynamic text and return ALL entries per location as a list.

    Returns: {loc: [parsed_dict, parsed_dict, ...]}
    Multiple entries for the same location are preserved (not merged).
    """
    all_entries = {}

    normalized = re.sub(r'[,:;]', ' ', text)
    lines = normalized.splitlines()

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue

        tokens = line.split()
        if not tokens:
            continue

        pos = 0
        while pos < len(tokens):
            loc, consumed = _find_location(tokens, pos)

            if loc is None and extra_locations:
                loc, consumed = _find_custom_location(tokens, pos, extra_locations)

            if loc is None:
                pos += 1
                continue

            pos += consumed

            value_tokens = []
            while pos < len(tokens):
                next_loc, _ = _find_location(tokens, pos)
                if next_loc is not None:
                    break
                value_tokens.append(tokens[pos])
                pos += 1

            parsed = _parse_numbers(value_tokens)

            # Pressure-only location fixups
            if loc in PRESSURE_ONLY:
                if "sat" in parsed:
                    v = parsed.pop("sat")
                    if "systolic" not in parsed:
                        parsed["systolic"] = v
                if ("systolic" in parsed
                        and "diastolic" not in parsed
                        and "mean" not in parsed):
                    parsed["mean"] = parsed.pop("systolic")

            if parsed:
                all_entries.setdefault(loc, []).append(parsed)

    return all_entries


def parse_hemodynamics(text: str, extra_locations: list = None) -> dict:
    """
    Parse a block of hemodynamic text into a dict keyed by canonical location.

    Accepts:
    - One location per line (most common)
    - Multiple locations on one line (fallback)
    - Colon or comma separators
    - % signs, m-prefix for mean
    - Slash-separated pressures

    extra_locations: optional list of custom location names (canonical form,
        e.g. ["Hepatic_vein", "My_Custom_Loc"]) that are not in LOCATION_ALIASES.
        Used as a fallback when the standard alias lookup fails.

    Returns:
    {
      'SVC':   {'sat': 79},
      'RA':    {'sat': 74, 'systolic': 10, 'diastolic': 8, 'mean': 9},
      'RPCWP': {'systolic': 17, 'diastolic': 12, 'mean': 14},
      ...
    }
    When a location appears multiple times, later values overwrite earlier ones.
    Use parse_hemodynamics_with_conflicts() to detect and surface conflicts.
    """
    all_entries = _collect_entries(text, extra_locations)
    result = {}
    for loc, entries in all_entries.items():
        merged = {}
        for entry in entries:
            merged.update(entry)
        result[loc] = merged
    return result


def parse_hemodynamics_with_conflicts(text: str, extra_locations: list = None) -> tuple:
    """
    Like parse_hemodynamics but also detects conflicting values.

    Returns (result, conflicts) where:
      result    — {loc: {field: value}}  first-occurrence value wins per field
      conflicts — {loc: {field: [val1, val2, ...]}}  only fields with >1 distinct value

    Example:
      Input: "RPA 75 50/30 38\\nRPA 80 45/25 35"
      result    → {'RPA': {'sat': 75, 'systolic': 50, 'diastolic': 30, 'mean': 38}}
      conflicts → {'RPA': {'sat': [75, 80], 'systolic': [50, 45],
                            'diastolic': [30, 25], 'mean': [38, 35]}}
    """
    all_entries = _collect_entries(text, extra_locations)
    result = {}
    conflicts = {}

    for loc, entries in all_entries.items():
        # Accumulate all seen values per field, in order
        field_vals: dict = {}
        for entry in entries:
            for field, value in entry.items():
                field_vals.setdefault(field, [])
                if value not in field_vals[field]:
                    field_vals[field].append(value)

        # Result: first value per field
        result[loc] = {f: vals[0] for f, vals in field_vals.items()}

        # Conflicts: fields with more than one distinct value
        loc_conflicts = {f: vals for f, vals in field_vals.items() if len(vals) > 1}
        if loc_conflicts:
            conflicts[loc] = loc_conflicts

    return result, conflicts


def format_parsed_for_display(parsed: dict) -> str:
    """Return a human-readable summary of parsed hemodynamics for confirmation."""
    lines = []
    ORDER = ["SVC", "IVC", "LSVC", "Innominate_vein", "Coronary_sinus",
             "Hepatic_vein", "Azygos_vein",
             "RA", "RV", "RV_body", "RV_apex", "RVOT", "MPA", "RPA", "LPA",
             "RPCWP", "LPCWP", "RPV", "LPV", "RUPV", "LUPV", "RLPV", "LLPV", "PV_confluence",
             "LA", "LV", "LVOT", "Descending_Aorta", "Ascending_Aorta",
             "Neoaorta", "Glenn_anastomosis", "Fontan_IVC_limb", "Fontan_conduit",
             "RV_systemic", "LV_systemic", "LV_pulmonary",
             "Venous_atrium", "Arterial_atrium",
             "BTS", "Sano_conduit", "Conduit", "Baffle"]
    seen = set()
    for loc in ORDER:
        if loc in parsed:
            seen.add(loc)
            d = parsed[loc]
            parts = []
            if "sat" in d:
                parts.append(f"Sat {int(d['sat'])}%")
            if "systolic" in d and "diastolic" in d:
                parts.append(f"{int(d['systolic'])}/{int(d['diastolic'])}")
                if "mean" in d:
                    parts.append(f"mean {int(d['mean'])}")
            elif "systolic" in d:
                parts.append(str(int(d["systolic"])))
            elif "mean" in d:
                parts.append(f"mean {int(d['mean'])}")
            lines.append(f"  {loc:<20} {' | '.join(parts)}")
    # Any extras not in ORDER
    for loc, d in parsed.items():
        if loc not in seen:
            parts = []
            if "sat" in d:
                parts.append(f"Sat {int(d['sat'])}%")
            if "systolic" in d and "diastolic" in d:
                parts.append(f"{int(d['systolic'])}/{int(d['diastolic'])}")
                if "mean" in d:
                    parts.append(f"mean {int(d['mean'])}")
            lines.append(f"  {loc:<20} {' | '.join(parts)}")
    return "\n".join(lines) if lines else "  (nothing parsed yet)"


# ---------------------------------------------------------------------------
# Metadata extraction: HGB and aVO2 from free-text
# ---------------------------------------------------------------------------

_META_PATTERNS = {
    # Hemoglobin
    "hgb": re.compile(
        r'(?:^|[\s,;])'
        r'(?:HGB|HB|HEMOGLOBIN|HAEMOGLOBIN|HGBCONC)'
        r'[\s:=]*'
        r'(\d+\.?\d*)',
        re.IGNORECASE | re.MULTILINE,
    ),
    # Assumed AV O2 difference (indexed VO2 / assumed content difference)
    "avo2": re.compile(
        r'(?:^|[\s,;])'
        r'(?:AVO2|AVDO2|AV ?O2|A-?VO2|A-?V ?O2 ?DIFF(?:ERENCE)?|ASSUMED ?VO2|VO2)'
        r'[\s:=]*'
        r'(\d+\.?\d*)',
        re.IGNORECASE | re.MULTILINE,
    ),
}


def parse_metadata(text: str) -> dict:
    """
    Extract non-hemodynamic metadata from free text.

    Returns a dict with any of:
      { "hgb": float, "avo2": float }
    Only keys that were found are included.
    """
    result = {}
    for key, pattern in _META_PATTERNS.items():
        m = pattern.search(text)
        if m:
            result[key] = float(m.group(1))
    return result
