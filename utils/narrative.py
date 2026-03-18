"""
Auto-generate hemodynamic narrative text for cath reports.

Structured as 4 clinical paragraphs per the standard cath report format:
  1. Conditions  (anesthesia, FiO2)
  2. Saturations (right-sided then left-sided, step-up detection)
  3. Pressures   (right side → left side, with normal/elevated labels)
  4. Calculations (VO2, Hgb, Fick-derived Qp/Qs/PVRi/SVRi)

Normal-value thresholds derived from:
  "The Blue Book" – Diagnostic and Interventional Cardiac Catheterization
  (Children's Hospital Boston / Park Pediatric Cardiology).
  RA mean 3-6 mmHg | RV sys 20-30 mmHg | PA mean <20 mmHg
  PCWP/LA 6-9 mmHg | LVEDP ≤12 mmHg (children) | PVRi <2 iWU
  Step-up ≥7 % saturation rise = significant left-to-right shunt
"""

# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt_sat(sat):
    if sat is None:
        return "not measured"
    return f"{int(round(sat))}%"


def _fmt_pct_systemic(val, ao_sys):
    if val is None or ao_sys is None or ao_sys == 0:
        return ""
    pct = round(val / ao_sys * 100)
    return f" ({pct}% of systemic)"


def _fmt_wedge(sys, diast, mean):
    """Format wedge/PCWP — mean-only entries display as plain number."""
    if sys is not None and diast is not None:
        parts = [f"{int(sys)}/{int(diast)}"]
        if mean is not None:
            parts.append(f"mean {int(mean)}")
        return " ".join(parts)
    elif mean is not None:
        return str(int(mean))
    return "not measured"


def _fmt_pressure(sys, diast, mean):
    parts = []
    if sys is not None and diast is not None:
        parts.append(f"{int(sys)}/{int(diast)}")
    elif sys is not None:
        parts.append(str(int(sys)))
    if mean is not None:
        parts.append(f"mean {int(mean)}")
    return " ".join(parts) if parts else "not measured"


def _p(loc, field, hemodynamics):
    v = hemodynamics.get(loc, {}).get(field)
    return float(v) if v is not None else None


# ── Normal-range helpers (Blue Cath Book thresholds) ─────────────────────────

def _ra_level(mean):
    """RA mean: normal 3-6, mildly elevated 7-10, elevated >10 mmHg."""
    if mean is None:
        return "unknown"
    if mean <= 6:
        return "normal"
    if mean <= 10:
        return "mildly elevated"
    return "elevated"


def _pa_level(mean):
    """PA mean: normal <20, mildly elevated 20-25, elevated >25 mmHg."""
    if mean is None:
        return "unknown"
    if mean < 20:
        return "normal"
    if mean <= 25:
        return "mildly elevated"
    return "elevated"


def _pcwp_level(mean):
    """PCWP/LA: normal ≤9, mildly elevated 10-15, elevated >15 mmHg."""
    if mean is None:
        return "unknown"
    if mean <= 9:
        return "normal"
    if mean <= 15:
        return "mildly elevated"
    return "elevated"


def _lvedp_level(val):
    """LVEDP: normal ≤12 mmHg in children (Blue Cath Book p. 6)."""
    if val is None:
        return "unknown"
    if val <= 12:
        return "normal"
    if val <= 18:
        return "mildly elevated"
    return "elevated"


def _rvedp_level(val):
    """RVEDP: normal 3-6 mmHg."""
    if val is None:
        return "unknown"
    if val <= 6:
        return "normal"
    if val <= 10:
        return "mildly elevated"
    return "elevated"


# ── Main function ─────────────────────────────────────────────────────────────

def generate_hemodynamic_narrative(hemodynamics, calculations, patient_data, step_ups):
    """
    Generate the full hemodynamic findings narrative as 4 paragraphs.

    Returns a string with paragraphs separated by double newlines.
    """

    anesthesia   = patient_data.get("anesthesia", "general anesthesia")
    fio2         = patient_data.get("fio2", "21%")
    anatomy_type = patient_data.get("anatomy_type", "biventricle")
    hgb          = float(patient_data.get("hgb") or 12.0)
    avo2         = float(patient_data.get("avo2") or 125.0)

    # ═══════════════════════════════════════════════════════════════════════
    # PARAGRAPH 1 — CONDITIONS
    # ═══════════════════════════════════════════════════════════════════════
    para1_parts = []
    para1_parts.append(
        f"Hemodynamic data were obtained under {anesthesia} on FiO\u2082 {fio2}."
    )
    para1 = " ".join(para1_parts)

    # ═══════════════════════════════════════════════════════════════════════
    # PARAGRAPH 2 — SATURATIONS
    # ═══════════════════════════════════════════════════════════════════════
    sat_lines = []

    # Pull all saturation values
    svc_sat  = _p("SVC",  "sat", hemodynamics)
    ivc_sat  = _p("IVC",  "sat", hemodynamics)
    ra_sat   = _p("RA",   "sat", hemodynamics)
    rv_sat   = _p("RV",   "sat", hemodynamics)
    mpa_sat  = _p("MPA",  "sat", hemodynamics)
    rpa_sat  = _p("RPA",  "sat", hemodynamics)
    lpa_sat  = _p("LPA",  "sat", hemodynamics)
    la_sat   = _p("LA",   "sat", hemodynamics)
    lv_sat   = _p("LV",   "sat", hemodynamics)
    ao_sat   = _p("Descending_Aorta", "sat", hemodynamics)
    rpv_sat  = _p("RPV",  "sat", hemodynamics)
    lpv_sat  = _p("LPV",  "sat", hemodynamics)
    rupv_sat = _p("RUPV", "sat", hemodynamics)
    lupv_sat = _p("LUPV", "sat", hemodynamics)
    rlpv_sat = _p("RLPV", "sat", hemodynamics)
    llpv_sat = _p("LLPV", "sat", hemodynamics)

    atrial_su  = next((s for s in step_ups if s["level"] == "atrial"),     None)
    ventric_su = next((s for s in step_ups if s["level"] == "ventricular"), None)
    pa_su      = next((s for s in step_ups if s["level"] == "PA level"),    None)

    # --- Right-sided saturations ---
    right_sat_parts = []

    if svc_sat is not None:
        right_sat_parts.append(f"SVC {_fmt_sat(svc_sat)}")
    if ivc_sat is not None:
        right_sat_parts.append(f"IVC {_fmt_sat(ivc_sat)}")

    # Mixed venous (used internally for Fick calculations — not reported in saturation list)

    if ra_sat is not None:
        right_sat_parts.append(f"RA {_fmt_sat(ra_sat)}")
    if rv_sat is not None:
        right_sat_parts.append(f"RV {_fmt_sat(rv_sat)}")
    if mpa_sat is not None:
        right_sat_parts.append(f"MPA {_fmt_sat(mpa_sat)}")
    if rpa_sat is not None:
        right_sat_parts.append(f"RPA {_fmt_sat(rpa_sat)}")
    if lpa_sat is not None:
        right_sat_parts.append(f"LPA {_fmt_sat(lpa_sat)}")

    if right_sat_parts:
        sat_lines.append(
            "Right-sided saturations: " + ", ".join(right_sat_parts) + "."
        )

    # --- Step-up commentary ---
    if atrial_su:
        delta = atrial_su.get("delta", 0)
        sat_lines.append(
            f"There was a significant oxygen saturation step-up from the SVC "
            f"({_fmt_sat(svc_sat)}) to the RA ({_fmt_sat(ra_sat)}), "
            f"a rise of {delta:.1f}%, consistent with a left-to-right shunt at "
            f"the atrial level (threshold \u22657%)."
        )
    if ventric_su:
        from_sat = ventric_su.get("from_sat")
        to_sat   = ventric_su.get("to_sat")
        delta    = ventric_su.get("delta", 0)
        sat_lines.append(
            f"There was a significant oxygen saturation step-up from the RA "
            f"({_fmt_sat(from_sat)}) to the RV ({_fmt_sat(to_sat)}), "
            f"a rise of {delta:.1f}%, consistent with a left-to-right shunt at "
            f"the ventricular level."
        )
    if pa_su:
        from_sat = pa_su.get("from_sat")
        to_sat   = pa_su.get("to_sat")
        delta    = pa_su.get("delta", 0)
        sat_lines.append(
            f"There was a significant oxygen saturation step-up from the RV "
            f"({_fmt_sat(from_sat)}) to the MPA ({_fmt_sat(to_sat)}), "
            f"a rise of {delta:.1f}%, consistent with a left-to-right shunt at "
            f"the PA level."
        )
    if not step_ups and svc_sat is not None and (ra_sat is not None or mpa_sat is not None):
        sat_lines.append(
            "No significant oxygen saturation step-up was identified (\u22657% threshold)."
        )

    # --- Left-sided saturations ---
    left_sat_parts = []

    # Pulmonary veins
    if rpv_sat is not None:
        left_sat_parts.append(f"RPV {_fmt_sat(rpv_sat)}")
    if lpv_sat is not None:
        left_sat_parts.append(f"LPV {_fmt_sat(lpv_sat)}")
    if rupv_sat is not None:
        left_sat_parts.append(f"RUPV {_fmt_sat(rupv_sat)}")
    if lupv_sat is not None:
        left_sat_parts.append(f"LUPV {_fmt_sat(lupv_sat)}")
    if rlpv_sat is not None:
        left_sat_parts.append(f"RLPV {_fmt_sat(rlpv_sat)}")
    if llpv_sat is not None:
        left_sat_parts.append(f"LLPV {_fmt_sat(llpv_sat)}")

    if la_sat is not None:
        left_sat_parts.append(f"LA {_fmt_sat(la_sat)}")
    if lv_sat is not None:
        left_sat_parts.append(f"LV {_fmt_sat(lv_sat)}")
    if ao_sat is not None:
        left_sat_parts.append(f"descending aorta {_fmt_sat(ao_sat)}")

    if left_sat_parts:
        sat_lines.append(
            "Left-sided saturations: " + ", ".join(left_sat_parts) + "."
        )

    para2 = " ".join(sat_lines) if sat_lines else ""

    # ═══════════════════════════════════════════════════════════════════════
    # PARAGRAPH 3 — PRESSURES (right → left)
    # ═══════════════════════════════════════════════════════════════════════
    pres_lines = []

    # --- Right atrium ---
    ra_mean = _p("RA", "mean", hemodynamics)
    ra_sys  = _p("RA", "systolic", hemodynamics)
    ra_dia  = _p("RA", "diastolic", hemodynamics)
    rvedp   = _p("RV", "diastolic", hemodynamics)

    if ra_mean is not None:
        level = _ra_level(ra_mean)
        ra_str = _fmt_pressure(ra_sys, ra_dia, ra_mean)
        if rvedp is not None:
            pres_lines.append(
                f"Right-sided filling pressures were {level}: "
                f"RA {ra_str} mmHg with RVEDP {int(rvedp)} mmHg "
                f"({_rvedp_level(rvedp)})."
            )
        else:
            pres_lines.append(
                f"Right-sided filling pressures were {level}: "
                f"RA {ra_str} mmHg."
            )
    elif rvedp is not None:
        pres_lines.append(
            f"RVEDP was {int(rvedp)} mmHg ({_rvedp_level(rvedp)})."
        )

    # --- Right ventricle ---
    rv_sys  = _p("RV", "systolic", hemodynamics)
    ao_sys  = _p("Descending_Aorta", "systolic", hemodynamics)
    neoao_sys = _p("Neoaorta", "systolic", hemodynamics)
    systemic_sys = ao_sys or neoao_sys

    if rv_sys is not None:
        pct_str = _fmt_pct_systemic(rv_sys, systemic_sys)
        # Normal RV systolic 20-30 mmHg per Blue Cath Book
        rv_level = "normal" if 20 <= rv_sys <= 30 else ("elevated" if rv_sys > 30 else "low")
        pres_lines.append(
            f"RV systolic pressure was {int(rv_sys)} mmHg{pct_str} ({rv_level})."
        )

    # --- Pulmonary artery ---
    mpa_sys  = _p("MPA", "systolic", hemodynamics)
    mpa_dia  = _p("MPA", "diastolic", hemodynamics)
    mpa_mean = _p("MPA", "mean", hemodynamics)
    rpa_sys  = _p("RPA", "systolic", hemodynamics)
    rpa_dia  = _p("RPA", "diastolic", hemodynamics)
    rpa_mean = _p("RPA", "mean", hemodynamics)
    lpa_sys  = _p("LPA", "systolic", hemodynamics)
    lpa_dia  = _p("LPA", "diastolic", hemodynamics)
    lpa_mean = _p("LPA", "mean", hemodynamics)

    if mpa_mean is not None:
        pa_level = _pa_level(mpa_mean)
        if mpa_sys is not None and mpa_dia is not None:
            pa_str = f"{int(mpa_sys)}/{int(mpa_dia)} mean {int(mpa_mean)}"
        else:
            pa_str = f"mean {int(mpa_mean)}"
        pres_lines.append(
            f"Main pulmonary artery pressure was {pa_str} mmHg ({pa_level})."
        )
    elif mpa_sys is not None:
        pres_lines.append(
            f"Main pulmonary artery systolic pressure was {int(mpa_sys)} mmHg."
        )

    # Branch PAs
    if rpa_mean is not None and lpa_mean is not None:
        pres_lines.append(
            f"RPA pressure was {_fmt_pressure(rpa_sys, rpa_dia, rpa_mean)} mmHg "
            f"and LPA pressure was {_fmt_pressure(lpa_sys, lpa_dia, lpa_mean)} mmHg."
        )
    elif rpa_mean is not None:
        pres_lines.append(
            f"RPA pressure was {_fmt_pressure(rpa_sys, rpa_dia, rpa_mean)} mmHg."
        )
    elif lpa_mean is not None:
        pres_lines.append(
            f"LPA pressure was {_fmt_pressure(lpa_sys, lpa_dia, lpa_mean)} mmHg."
        )

    # PA branch gradients
    if mpa_mean is not None and rpa_mean is not None:
        grad = mpa_mean - rpa_mean
        if grad > 5:
            pres_lines.append(
                f"There was a mean gradient of {int(grad)} mmHg from the MPA to the RPA."
            )
    if mpa_mean is not None and lpa_mean is not None:
        grad = mpa_mean - lpa_mean
        if grad > 5:
            pres_lines.append(
                f"There was a mean gradient of {int(grad)} mmHg from the MPA to the LPA."
            )

    # --- Wedge / PCWP ---
    rpcwp_mean = _p("RPCWP", "mean", hemodynamics)
    rpcwp_sys  = _p("RPCWP", "systolic", hemodynamics)
    rpcwp_dia  = _p("RPCWP", "diastolic", hemodynamics)
    lpcwp_mean = _p("LPCWP", "mean", hemodynamics)
    lpcwp_sys  = _p("LPCWP", "systolic", hemodynamics)
    lpcwp_dia  = _p("LPCWP", "diastolic", hemodynamics)
    mean_pcwp  = calculations.get("mean_pcwp")

    if rpcwp_mean is not None and lpcwp_mean is not None:
        mean_suffix = (
            f" (mean {int(mean_pcwp)} mmHg, {_pcwp_level(mean_pcwp)})"
            if rpcwp_mean != lpcwp_mean else f" ({_pcwp_level(mean_pcwp)})"
        )
        pres_lines.append(
            f"RPCWP was {_fmt_wedge(rpcwp_sys, rpcwp_dia, rpcwp_mean)} mmHg "
            f"and LPCWP was {_fmt_wedge(lpcwp_sys, lpcwp_dia, lpcwp_mean)} mmHg"
            f"{mean_suffix}."
        )
    elif rpcwp_mean is not None:
        pres_lines.append(
            f"RPCWP was {_fmt_wedge(rpcwp_sys, rpcwp_dia, rpcwp_mean)} mmHg "
            f"({_pcwp_level(rpcwp_mean)})."
        )
    elif lpcwp_mean is not None:
        pres_lines.append(
            f"LPCWP was {_fmt_wedge(lpcwp_sys, lpcwp_dia, lpcwp_mean)} mmHg "
            f"({_pcwp_level(lpcwp_mean)})."
        )

    # Transpulmonary gradient
    tpg = calculations.get("tpg")
    if tpg is not None:
        pres_lines.append(f"Transpulmonary gradient was {int(tpg)} mmHg.")

    # --- Pulmonary vein pressures ---
    rpv_sys  = _p("RPV", "systolic", hemodynamics)
    rpv_dia  = _p("RPV", "diastolic", hemodynamics)
    rpv_mean = _p("RPV", "mean", hemodynamics)
    lpv_sys  = _p("LPV", "systolic", hemodynamics)
    lpv_dia  = _p("LPV", "diastolic", hemodynamics)
    lpv_mean = _p("LPV", "mean", hemodynamics)

    if rpv_sys is not None or rpv_mean is not None:
        pres_lines.append(
            f"Right pulmonary vein pressure was "
            f"{_fmt_pressure(rpv_sys, rpv_dia, rpv_mean)} mmHg."
        )
    if lpv_sys is not None or lpv_mean is not None:
        pres_lines.append(
            f"Left pulmonary vein pressure was "
            f"{_fmt_pressure(lpv_sys, lpv_dia, lpv_mean)} mmHg."
        )

    # --- Left atrium ---
    la_mean = _p("LA", "mean", hemodynamics)
    if la_mean is not None:
        pres_lines.append(
            f"Left atrial mean pressure was {int(la_mean)} mmHg "
            f"({_pcwp_level(la_mean)})."
        )

    # --- Left ventricle ---
    lv_sys = _p("LV", "systolic", hemodynamics)
    lv_dia = _p("LV", "diastolic", hemodynamics)

    if lv_sys is not None:
        lv_line = f"LV systolic pressure was {int(lv_sys)} mmHg"
        if lv_dia is not None:
            lv_line += (
                f" with LVEDP {int(lv_dia)} mmHg ({_lvedp_level(lv_dia)})"
            )
        pres_lines.append(lv_line + ".")
    elif lv_dia is not None:
        pres_lines.append(
            f"LVEDP was {int(lv_dia)} mmHg ({_lvedp_level(lv_dia)})."
        )

    # --- Aorta ---
    ao_dia  = _p("Descending_Aorta", "diastolic", hemodynamics)
    ao_mean = _p("Descending_Aorta", "mean", hemodynamics)

    if ao_sys is not None:
        ao_line = f"Descending aortic pressure was {int(ao_sys)}"
        if ao_dia is not None:
            ao_line += f"/{int(ao_dia)}"
        if ao_mean is not None:
            ao_line += f" mean {int(ao_mean)} mmHg"
        pres_lines.append(ao_line + ".")

    # Single ventricle pressures
    if anatomy_type in ("post_fontan", "post_glenn"):
        fontan_p = _p("Fontan_IVC_limb", "mean", hemodynamics)
        if fontan_p is not None:
            pres_lines.append(
                f"Fontan circuit pressure was {int(fontan_p)} mmHg."
            )
        glenn_p = _p("Glenn_anastomosis", "mean", hemodynamics)
        if glenn_p is not None:
            pres_lines.append(
                f"Glenn anastomosis pressure was {int(glenn_p)} mmHg."
            )

    para3 = " ".join(pres_lines) if pres_lines else ""

    # ═══════════════════════════════════════════════════════════════════════
    # PARAGRAPH 4 — CALCULATIONS
    # ═══════════════════════════════════════════════════════════════════════
    calc_lines = []

    qs     = calculations.get("qs")
    qp     = calculations.get("qp")
    qp_qs  = calculations.get("qp_qs")
    pvri   = calculations.get("pvri")
    svri   = calculations.get("svri")
    rp_rs  = calculations.get("rp_rs")

    any_calc = any(v is not None for v in [qs, qp, pvri])

    if any_calc:
        # State the inputs used
        calc_lines.append(
            f"Flows were calculated using the Fick method with an assumed "
            f"oxygen consumption index (VO\u2082) of {int(avo2)}\u00a0mL/min/m\u00b2 "
            f"and hemoglobin of {hgb:.1f}\u00a0g/dL."
        )

    if qs is not None:
        calc_lines.append(
            f"Systemic flow (Qs) was {qs:.2f}\u00a0L/min/m\u00b2."
        )

    if qp is not None:
        qp_line = f"Pulmonary flow (Qp) was {qp:.2f}\u00a0L/min/m\u00b2"
        if qp_qs is not None:
            ratio_interp = ""
            if qp_qs >= 2.0:
                ratio_interp = " (large left-to-right shunt)"
            elif qp_qs >= 1.5:
                ratio_interp = " (moderate left-to-right shunt)"
            elif qp_qs >= 1.2:
                ratio_interp = " (mild left-to-right shunt)"
            elif qp_qs <= 0.8:
                ratio_interp = " (net right-to-left shunt)"
            qp_line += f" with a Qp:Qs of {qp_qs:.2f}:1{ratio_interp}"
        calc_lines.append(qp_line + ".")

    if pvri is not None:
        # PVRi normal <2 iWU per Blue Cath Book
        pvri_level = "normal" if pvri < 2.0 else ("mildly elevated" if pvri < 4.0 else "elevated")
        pvri_line  = (
            f"Indexed pulmonary vascular resistance (PVRi) was "
            f"{pvri:.2f}\u00a0iWU ({pvri_level})"
        )
        if svri is not None:
            # SVRi normal 15-20 WU per Blue Cath Book
            svri_level = "normal" if 15 <= svri <= 20 else ("low" if svri < 15 else "elevated")
            pvri_line += (
                f" and indexed systemic vascular resistance (SVRi) was "
                f"{svri:.1f}\u00a0iWU ({svri_level})"
            )
        if rp_rs is not None:
            pvri_line += f", with Rp/Rs {rp_rs:.2f}"
        calc_lines.append(pvri_line + ".")

    # Calculation warnings
    calc_warnings = calculations.get("warnings", [])
    if calc_warnings:
        calc_lines.append("Note: " + "; ".join(calc_warnings) + ".")

    para4 = " ".join(calc_lines) if calc_lines else ""

    # ═══════════════════════════════════════════════════════════════════════
    # Assemble final narrative — skip empty paragraphs
    # ═══════════════════════════════════════════════════════════════════════
    paragraphs = [p for p in [para1, para2, para3, para4] if p.strip()]
    return "\n\n".join(paragraphs)
