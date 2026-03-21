"""
Hemodynamic calculations for cardiac catheterization.
Uses the Fick method for flow calculations.
"""


def calculate_mixed_venous(svc_sat, ivc_sat):
    """
    Flamm formula for mixed venous saturation:
    MV = (3 * SVC + IVC) / 4
    """
    if svc_sat is not None and ivc_sat is not None:
        return (3 * svc_sat + ivc_sat) / 4
    elif svc_sat is not None:
        return svc_sat
    elif ivc_sat is not None:
        return ivc_sat
    return None


def _o2_content(sat_pct, hgb):
    """O2 content in mL O2 / dL blood."""
    return (sat_pct / 100.0) * hgb * 1.36 * 10  # 10 = dL->L conversion factor


def calculate_fick_flow(avo2_indexed, sat_high, sat_low, hgb):
    """
    Fick flow = indexed VO2 / (CaO2 - CvO2)
    Units: L/min/m2 (indexed)
    avo2_indexed: mL/min/m2
    sat_high: higher (venous-to-arterial) side saturation %
    sat_low: lower side saturation %
    hgb: g/dL
    """
    delta_content = _o2_content(sat_high, hgb) - _o2_content(sat_low, hgb)
    if delta_content <= 0:
        return None
    return avo2_indexed / delta_content


def detect_step_ups(hemodynamics):
    """
    Detect O2 saturation step-ups (left-to-right shunting).

    Thresholds per level (per clinical convention):
      Atrial  (SVC → RA):  >8%
      Ventricular (RA → RV): >5%
      PA level (RV → MPA): >5%

    Returns list of step-up dicts.
    """
    SEQUENCE = [
        ("SVC", "RA",  "atrial",       8.0),
        ("RA",  "RV",  "ventricular",  5.0),
        ("RV",  "MPA", "PA level",     5.0),
    ]
    step_ups = []
    for from_loc, to_loc, level, threshold in SEQUENCE:
        from_sat = hemodynamics.get(from_loc, {}).get("sat")
        to_sat = hemodynamics.get(to_loc, {}).get("sat")
        if from_sat is not None and to_sat is not None:
            delta = to_sat - from_sat
            if delta > threshold:
                step_ups.append({
                    "from": from_loc,
                    "to": to_loc,
                    "from_sat": from_sat,
                    "to_sat": to_sat,
                    "delta": round(delta, 1),
                    "level": level,
                })
    return step_ups


def calculate_all(hemodynamics, patient_data):
    """
    Run all hemodynamic calculations.

    patient_data: {'hgb': float, 'avo2': float, 'bsa': float}
    hemodynamics: dict keyed by location, each with optional sat/systolic/diastolic/mean

    Returns dict with calculated values and warnings.
    """
    warnings = []

    hgb = float(patient_data.get("hgb") or 12.0)
    avo2 = float(patient_data.get("avo2") or 125.0)  # mL/min/m2

    # Saturation values
    def sat(loc):
        return hemodynamics.get(loc, {}).get("sat")

    def pressure(loc, field):
        v = hemodynamics.get(loc, {}).get(field)
        return float(v) if v is not None else None

    svc_sat = sat("SVC")
    ivc_sat = sat("IVC")
    pa_sat = sat("MPA") or sat("RPA")
    pv_sat = sat("LA") or sat("LV")
    ao_sat = sat("Descending_Aorta") or sat("LV") or sat("Neoaorta")

    # Mixed venous
    mv_sat = calculate_mixed_venous(svc_sat, ivc_sat)
    if mv_sat is None and pa_sat is not None:
        mv_sat = pa_sat
        warnings.append("No SVC/IVC saturations entered; using PA sat as mixed venous proxy.")
    # Pulmonary venous saturation
    if pv_sat is None:
        pv_sat = 98.0
        if ao_sat and ao_sat < 95:
            warnings.append("Assuming PV saturation of 98% (LA/LV sat not entered).")

    # PA saturation fallback
    if pa_sat is None and mv_sat is not None:
        pa_sat = mv_sat
        warnings.append("PA saturation not entered; using mixed venous for Qp estimate.")

    # Qp and Qs
    qp = None
    qs = None

    if pa_sat is not None and pv_sat is not None:
        qp = calculate_fick_flow(avo2, pv_sat, pa_sat, hgb)
        if qp is None:
            warnings.append("Qp could not be calculated (PV sat ≤ PA sat).")

    if ao_sat is not None and mv_sat is not None:
        qs = calculate_fick_flow(avo2, ao_sat, mv_sat, hgb)
        if qs is None:
            warnings.append("Qs could not be calculated (Ao sat ≤ mixed venous sat).")

    qp_qs = None
    if qp and qs and qs > 0:
        qp_qs = qp / qs

    # Pressures
    mean_mpa = pressure("MPA", "mean")
    mean_rpcwp = pressure("RPCWP", "mean")
    mean_lpcwp = pressure("LPCWP", "mean")
    mean_pcwp = None
    if mean_rpcwp is not None and mean_lpcwp is not None:
        mean_pcwp = (mean_rpcwp + mean_lpcwp) / 2
    elif mean_rpcwp is not None:
        mean_pcwp = mean_rpcwp
    elif mean_lpcwp is not None:
        mean_pcwp = mean_lpcwp

    mean_ao = pressure("Descending_Aorta", "mean") or pressure("Neoaorta", "mean")
    mean_ra = pressure("RA", "mean")

    pvri = None
    if mean_mpa is not None and mean_pcwp is not None and qp:
        pvri = (mean_mpa - mean_pcwp) / qp

    svri = None
    if mean_ao is not None and mean_ra is not None and qs:
        svri = (mean_ao - mean_ra) / qs

    rp_rs = None
    if pvri is not None and svri and svri > 0:
        rp_rs = pvri / svri

    # Transpulmonary gradient
    tpg = None
    if mean_mpa is not None and mean_pcwp is not None:
        tpg = mean_mpa - mean_pcwp

    return {
        "mixed_venous_sat": round(mv_sat, 1) if mv_sat else None,
        "qp": round(qp, 2) if qp else None,
        "qs": round(qs, 2) if qs else None,
        "qp_qs": round(qp_qs, 2) if qp_qs else None,
        "pvri": round(pvri, 2) if pvri is not None else None,
        "svri": round(svri, 2) if svri is not None else None,
        "rp_rs": round(rp_rs, 3) if rp_rs is not None else None,
        "tpg": round(tpg, 1) if tpg is not None else None,
        "mean_pcwp": round(mean_pcwp, 1) if mean_pcwp is not None else None,
        "method": "fick",
        "warnings": warnings,
    }


def assess_pressure_level(mean_value, thresholds):
    """
    Classify a pressure as normal/mildly/moderately/severely elevated.
    thresholds: (mild, moderate) e.g. (10, 15) for RA
    """
    if mean_value is None:
        return "unknown"
    if mean_value <= thresholds[0]:
        return "normal"
    elif mean_value <= thresholds[1]:
        return "mildly elevated"
    elif mean_value <= thresholds[2]:
        return "moderately elevated"
    else:
        return "severely elevated"
