"""
Auto-generate hemodynamic narrative text for cath reports.

Follows the standard clinical template:
  Para 1: FiO2 conditions
  Para 2: Saturations — SVC step-up sentence, PV sats, LA sat, descending aorta sat
  Para 3: Pressures — right filling, RV + PA gradients, wedge, LA, PV-LA gradient, LV + Ao
  Para 4: Fick calculations — Qs, Qp/Qs, PVRi

Only sentences for which data are provided are included.
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_sat(sat):
    if sat is None:
        return "not measured"
    return f"{int(round(sat))}%"


def _fmt_press(sys, diast, mean):
    """Return 'sys/dia mean X' string, omitting missing components. Returns None if nothing."""
    parts = []
    if sys is not None and diast is not None:
        parts.append(f"{int(sys)}/{int(diast)}")
    elif sys is not None:
        parts.append(str(int(sys)))
    if mean is not None:
        parts.append(f"mean {int(mean)}")
    return " ".join(parts) if parts else None


def _p(loc, field, hemo):
    v = hemo.get(loc, {}).get(field)
    return float(v) if v is not None else None


def _grad_str(from_val, to_val):
    """Return 'no gradient' or 'X mmHg gradient' based on systolic difference."""
    if from_val is None or to_val is None:
        return None
    diff = from_val - to_val
    if diff <= 5:
        return "no gradient"
    return f"{int(round(diff))} mmHg gradient"


def _ra_level(mean):
    if mean is None:
        return "unknown"
    if mean <= 6:
        return "normal"
    if mean <= 10:
        return "mildly elevated"
    return "elevated"


def _rvedp_level(val):
    if val is None:
        return "unknown"
    if val <= 6:
        return "normal"
    if val <= 10:
        return "mildly elevated"
    return "elevated"


# ── Main function ──────────────────────────────────────────────────────────────

def generate_hemodynamic_narrative(hemodynamics, calculations, patient_data, step_ups):
    """
    Generate the full hemodynamic findings narrative (up to 4 paragraphs).
    Paragraphs are separated by double newlines.
    Only sentences for which data are available are included.
    """

    fio2         = patient_data.get("fio2", "21%")
    avo2         = float(patient_data.get("avo2") or 125.0)
    anatomy_type = patient_data.get("anatomy_type", "biventricle")

    # ═══════════════════════════════════════════════════════════════════════
    # PARAGRAPH 1 — CONDITIONS
    # ═══════════════════════════════════════════════════════════════════════
    para1 = f"Hemodynamics were measured on FiO2 {fio2}."

    # ═══════════════════════════════════════════════════════════════════════
    # PARAGRAPH 2 — SATURATIONS
    # ═══════════════════════════════════════════════════════════════════════
    sat_sentences = []

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

    # Step-up language
    step_up_desc = "a step-up" if step_ups else "no step-up"

    # --- Sentence 1: SVC → right-heart chain ---
    # "The SVC saturation was X% with no/a step-up through the right-heart,
    #  RA saturation of X%, RV saturation of X% and RPA saturation of X%."
    right_chain = []
    if ra_sat is not None:
        right_chain.append(f"RA saturation of {_fmt_sat(ra_sat)}")
    if rv_sat is not None:
        right_chain.append(f"RV saturation of {_fmt_sat(rv_sat)}")
    if rpa_sat is not None:
        right_chain.append(f"RPA saturation of {_fmt_sat(rpa_sat)}")
    elif mpa_sat is not None:
        right_chain.append(f"MPA saturation of {_fmt_sat(mpa_sat)}")
    if lpa_sat is not None:
        right_chain.append(f"LPA saturation of {_fmt_sat(lpa_sat)}")

    if svc_sat is not None:
        s = f"The SVC saturation was {_fmt_sat(svc_sat)} with {step_up_desc} through the right-heart"
        if right_chain:
            if len(right_chain) == 1:
                s += f", {right_chain[0]}"
            else:
                s += ", " + ", ".join(right_chain[:-1]) + " and " + right_chain[-1]
        s += "."
        sat_sentences.append(s)
    elif right_chain:
        # No SVC — list right-sided sats as available
        sat_sentences.append("Right-sided saturations: " + ", ".join(right_chain) + ".")

    # IVC (separate sentence when SVC was already mentioned)
    if svc_sat is not None and ivc_sat is not None:
        sat_sentences.append(f"The IVC saturation was {_fmt_sat(ivc_sat)}.")
    elif svc_sat is None and ivc_sat is not None and not right_chain:
        sat_sentences.append(f"The IVC saturation was {_fmt_sat(ivc_sat)}.")

    # --- Pulmonary vein saturations ---
    pv_vals = [v for v in [rpv_sat, lpv_sat, rupv_sat, lupv_sat, rlpv_sat, llpv_sat]
               if v is not None]
    if pv_vals:
        pv_strs = [_fmt_sat(v) for v in pv_vals]
        if len(set(pv_strs)) == 1:
            sat_sentences.append(
                f"The pulmonary veins were fully saturated with PV saturations of {pv_strs[0]}."
            )
        else:
            sat_sentences.append(
                f"Pulmonary vein saturations were {', '.join(pv_strs)}."
            )

    # --- LA saturation ---
    if la_sat is not None:
        sat_sentences.append(f"The LA saturation was {_fmt_sat(la_sat)}.")

    # --- LV saturation (only if different from LA, e.g. admixture) ---
    if lv_sat is not None and lv_sat != la_sat:
        sat_sentences.append(f"The LV saturation was {_fmt_sat(lv_sat)}.")

    # --- Descending aorta saturation ---
    if ao_sat is not None:
        sat_sentences.append(f"The descending aorta saturation was {_fmt_sat(ao_sat)}.")

    para2 = " ".join(sat_sentences) if sat_sentences else ""

    # ═══════════════════════════════════════════════════════════════════════
    # PARAGRAPH 3 — PRESSURES (right → left)
    # ═══════════════════════════════════════════════════════════════════════
    pres_sentences = []

    ra_sys  = _p("RA", "systolic", hemodynamics)
    ra_dia  = _p("RA", "diastolic", hemodynamics)
    ra_mean = _p("RA", "mean", hemodynamics)
    rvedp   = _p("RV", "diastolic", hemodynamics)

    # --- Right-sided filling pressures ---
    # "Right sided filling pressures were (normal/elevated) with RA pressure X/X mean X mmHg
    #  and RVEDP X mmHg."
    if ra_mean is not None or ra_sys is not None or rvedp is not None:
        level = _ra_level(ra_mean)
        ra_str = _fmt_press(ra_sys, ra_dia, ra_mean)
        parts = []
        if ra_str:
            parts.append(f"RA pressure {ra_str} mmHg")
        if rvedp is not None:
            parts.append(f"RVEDP {int(rvedp)} mmHg")
        if parts:
            pres_sentences.append(
                f"Right sided filling pressures were {level} with {' and '.join(parts)}."
            )

    # --- RV systolic with gradients to branch PAs ---
    # "The RV systolic pressure was X mmHg with X gradient to RPA pressure X/X mean X mmHg
    #  and X gradient to LPA pressure X/X mean X mmHg."
    rv_sys   = _p("RV", "systolic", hemodynamics)
    rpa_sys  = _p("RPA", "systolic", hemodynamics)
    rpa_dia  = _p("RPA", "diastolic", hemodynamics)
    rpa_mean = _p("RPA", "mean", hemodynamics)
    lpa_sys  = _p("LPA", "systolic", hemodynamics)
    lpa_dia  = _p("LPA", "diastolic", hemodynamics)
    lpa_mean = _p("LPA", "mean", hemodynamics)
    mpa_sys  = _p("MPA", "systolic", hemodynamics)
    mpa_dia  = _p("MPA", "diastolic", hemodynamics)
    mpa_mean = _p("MPA", "mean", hemodynamics)

    if rv_sys is not None:
        rv_s = f"The RV systolic pressure was {int(rv_sys)} mmHg"

        # Prefer RPA for gradient target; fall back to MPA
        if rpa_sys is not None or rpa_mean is not None:
            rpa_str = _fmt_press(rpa_sys, rpa_dia, rpa_mean)
            rpa_grad = _grad_str(rv_sys, rpa_sys)
            if rpa_str and rpa_grad:
                rv_s += f" with {rpa_grad} to RPA pressure {rpa_str} mmHg"
                if lpa_sys is not None or lpa_mean is not None:
                    lpa_str = _fmt_press(lpa_sys, lpa_dia, lpa_mean)
                    lpa_grad = _grad_str(rv_sys, lpa_sys)
                    if lpa_str and lpa_grad:
                        rv_s += f" and {lpa_grad} to LPA pressure {lpa_str} mmHg"
        elif mpa_sys is not None or mpa_mean is not None:
            mpa_str = _fmt_press(mpa_sys, mpa_dia, mpa_mean)
            mpa_grad = _grad_str(rv_sys, mpa_sys)
            if mpa_str and mpa_grad:
                rv_s += f" with {mpa_grad} to MPA pressure {mpa_str} mmHg"

        rv_s += "."
        pres_sentences.append(rv_s)
    elif mpa_sys is not None or mpa_mean is not None:
        mpa_str = _fmt_press(mpa_sys, mpa_dia, mpa_mean)
        if mpa_str:
            pres_sentences.append(f"Main pulmonary artery pressure was {mpa_str} mmHg.")

    # --- RPCWP ---
    rpcwp_sys  = _p("RPCWP", "systolic", hemodynamics)
    rpcwp_dia  = _p("RPCWP", "diastolic", hemodynamics)
    rpcwp_mean = _p("RPCWP", "mean", hemodynamics)
    if rpcwp_sys is not None or rpcwp_mean is not None:
        s = _fmt_press(rpcwp_sys, rpcwp_dia, rpcwp_mean)
        if s:
            pres_sentences.append(f"The right pulmonary capillary wedge pressure was {s} mmHg.")

    # --- LPCWP ---
    lpcwp_sys  = _p("LPCWP", "systolic", hemodynamics)
    lpcwp_dia  = _p("LPCWP", "diastolic", hemodynamics)
    lpcwp_mean = _p("LPCWP", "mean", hemodynamics)
    if lpcwp_sys is not None or lpcwp_mean is not None:
        s = _fmt_press(lpcwp_sys, lpcwp_dia, lpcwp_mean)
        if s:
            pres_sentences.append(f"The left pulmonary capillary wedge pressure was {s} mmHg.")

    # --- LA pressure ---
    la_sys  = _p("LA", "systolic", hemodynamics)
    la_dia  = _p("LA", "diastolic", hemodynamics)
    la_mean = _p("LA", "mean", hemodynamics)
    if la_sys is not None or la_mean is not None:
        s = _fmt_press(la_sys, la_dia, la_mean)
        if s:
            pres_sentences.append(f"LA pressure was {s} mmHg.")

    # --- PV pressure to LA gradient ---
    # "There was X gradient from pulmonary vein pressures of X mmHg to LA pressure."
    rpv_sys  = _p("RPV", "systolic", hemodynamics)
    rpv_dia  = _p("RPV", "diastolic", hemodynamics)
    rpv_mean = _p("RPV", "mean", hemodynamics)
    lpv_sys  = _p("LPV", "systolic", hemodynamics)
    lpv_dia  = _p("LPV", "diastolic", hemodynamics)
    lpv_mean = _p("LPV", "mean", hemodynamics)

    pv_sys_val  = rpv_sys  or lpv_sys
    pv_dia_val  = rpv_dia  or lpv_dia
    pv_mean_val = rpv_mean or lpv_mean

    if (pv_sys_val is not None or pv_mean_val is not None) and la_mean is not None:
        pv_str  = _fmt_press(pv_sys_val, pv_dia_val, pv_mean_val)
        compare = pv_mean_val if pv_mean_val is not None else pv_sys_val
        grad    = _grad_str(compare, la_mean)
        if pv_str and grad:
            pres_sentences.append(
                f"There was {grad} from pulmonary vein pressures of {pv_str} mmHg to LA pressure."
            )

    # --- LV pressure with gradient to aorta ---
    # "LV pressure was X/X mmHg with X gradient across aortic valve to ascending
    #  pressure of X mmHg and descending aorta pressure of X mmHg."
    lv_sys = _p("LV", "systolic", hemodynamics)
    lv_dia = _p("LV", "diastolic", hemodynamics)

    asc_ao_sys  = _p("Ascending_Aorta", "systolic", hemodynamics)
    asc_ao_dia  = _p("Ascending_Aorta", "diastolic", hemodynamics)
    asc_ao_mean = _p("Ascending_Aorta", "mean", hemodynamics)

    desc_ao_sys  = _p("Descending_Aorta", "systolic", hemodynamics)
    desc_ao_dia  = _p("Descending_Aorta", "diastolic", hemodynamics)
    desc_ao_mean = _p("Descending_Aorta", "mean", hemodynamics)

    neoao_sys  = _p("Neoaorta", "systolic", hemodynamics)
    neoao_dia  = _p("Neoaorta", "diastolic", hemodynamics)
    neoao_mean = _p("Neoaorta", "mean", hemodynamics)

    if lv_sys is not None:
        lv_str = _fmt_press(lv_sys, lv_dia, None)
        lv_s   = f"LV pressure was {lv_str} mmHg"

        # Ascending aorta (prefer explicit Ascending_Aorta; fallback Neoaorta)
        asc_sys  = asc_ao_sys  or neoao_sys
        asc_dia  = asc_ao_dia  or neoao_dia
        asc_mean = asc_ao_mean or neoao_mean

        if asc_sys is not None:
            av_grad = _grad_str(lv_sys, asc_sys)
            asc_str = _fmt_press(asc_sys, asc_dia, asc_mean)
            if av_grad and asc_str:
                lv_s += f" with {av_grad} across aortic valve to ascending pressure of {asc_str} mmHg"
                if desc_ao_sys is not None:
                    desc_str = _fmt_press(desc_ao_sys, desc_ao_dia, desc_ao_mean)
                    if desc_str:
                        lv_s += f" and descending aorta pressure of {desc_str} mmHg"
        elif desc_ao_sys is not None:
            av_grad = _grad_str(lv_sys, desc_ao_sys)
            desc_str = _fmt_press(desc_ao_sys, desc_ao_dia, desc_ao_mean)
            if av_grad and desc_str:
                lv_s += f" with {av_grad} across aortic valve to aortic pressure of {desc_str} mmHg"

        lv_s += "."
        pres_sentences.append(lv_s)
    elif lv_dia is not None:
        pres_sentences.append(f"LVEDP was {int(lv_dia)} mmHg.")

    # Standalone descending aorta (when no LV)
    if lv_sys is None and lv_dia is None and desc_ao_sys is not None:
        desc_str = _fmt_press(desc_ao_sys, desc_ao_dia, desc_ao_mean)
        if desc_str:
            pres_sentences.append(f"Descending aorta pressure was {desc_str} mmHg.")

    # Single-ventricle anatomy
    if anatomy_type in ("post_fontan", "post_glenn"):
        fontan_p = _p("Fontan_IVC_limb", "mean", hemodynamics)
        if fontan_p is not None:
            pres_sentences.append(f"Fontan circuit pressure was {int(fontan_p)} mmHg.")
        glenn_p = _p("Glenn_anastomosis", "mean", hemodynamics)
        if glenn_p is not None:
            pres_sentences.append(f"Glenn anastomosis pressure was {int(glenn_p)} mmHg.")

    para3 = " ".join(pres_sentences) if pres_sentences else ""

    # ═══════════════════════════════════════════════════════════════════════
    # PARAGRAPH 4 — FICK CALCULATIONS
    # ═══════════════════════════════════════════════════════════════════════
    calc_sentences = []

    qs    = calculations.get("qs")
    qp    = calculations.get("qp")
    qp_qs = calculations.get("qp_qs")
    pvri  = calculations.get("pvri")
    svri  = calculations.get("svri")

    if qs is not None:
        calc_sentences.append(
            f"Using Fick and an assumed aVO2 of {int(avo2)} mL/min/m\u00b2, "
            f"Qs was equal to {qs:.2f} L/min/m\u00b2."
        )

    if qp is not None:
        qp_s = f"Qp was {qp:.2f} L/min/m\u00b2"
        if qp_qs is not None:
            qp_s += f", yielding a Qp:Qs of {qp_qs:.2f}"
        calc_sentences.append(qp_s + ".")

    if pvri is not None:
        pvri_s = f"The PVRi was {pvri:.2f} iWU"
        if svri is not None:
            pvri_s += f" and SVRi was {svri:.1f} iWU"
        calc_sentences.append(pvri_s + ".")

    # Calculation warnings
    warnings = calculations.get("warnings", [])
    if warnings:
        calc_sentences.append("Note: " + "; ".join(warnings) + ".")

    para4 = " ".join(calc_sentences) if calc_sentences else ""

    # ═══════════════════════════════════════════════════════════════════════
    # Assemble — skip empty paragraphs
    # ═══════════════════════════════════════════════════════════════════════
    paragraphs = [p for p in [para1, para2, para3, para4] if p.strip()]
    return "\n\n".join(paragraphs)
