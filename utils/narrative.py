"""
Auto-generate hemodynamic narrative text for cath reports.

Follows the standard clinical template:
  Para 1: FiO2 conditions
  Para 2: Saturations — SVC step-up sentence, PV sats, LA sat, descending aorta sat
  Para 3: Pressures — right filling, RV + PA gradients, RVOT gradient, wedge + TPG, LA, LV + Ao
  Para 4: Fick calculations — Qs, Qp/Qs, PVRi

Only sentences for which data are provided are included.

Clinical thresholds (per hemodynamics example document):
  RA mean    : normal 2–7 mmHg; ≥8 elevated
  LA mean    : normal <10 mmHg; ≥10 elevated
  RVEDP/LVEDP: normal ≤10 mmHg; >10 elevated
  RVOT grad  : mild 25–49 mmHg; moderate 50–79 mmHg; severe ≥80 mmHg
  TPG        : normal <12 mmHg; elevated ≥12 mmHg
  PV sat     : <95% → mixed pulmonary vein desaturation
  Step-ups   : atrial (SVC→RA) >8%; ventricular (RA→RV) >5%; PA (RV→MPA) >5%
  Fontan/Glenn pressure: normal <15 mmHg; ≥15 elevated
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


def _mean_or_sys(loc, hemo):
    """Return mean pressure, falling back to systolic for mean-only locations
    where a single entered value gets stored as systolic by the parser."""
    v = hemo.get(loc, {})
    m = v.get("mean")
    if m is not None:
        return float(m)
    s = v.get("systolic")
    return float(s) if s is not None else None


def _grad_str(from_val, to_val):
    """Return 'no gradient' or 'a X mmHg gradient'. Returns None if either value missing."""
    if from_val is None or to_val is None:
        return None
    diff = int(round(from_val - to_val))
    if diff <= 0:
        return "no gradient"
    return f"a {diff} mmHg gradient"


def _ra_level(mean):
    """RA normal 2–7 mmHg; ≥8 elevated."""
    if mean is None:
        return "unknown"
    return "normal" if mean <= 7 else "elevated"


def _la_level(mean):
    """LA normal <10 mmHg; ≥10 elevated."""
    if mean is None:
        return None
    return "normal" if mean < 10 else "elevated"


def _vedp_level(val):
    """RVEDP/LVEDP normal ≤10 mmHg; >10 elevated."""
    if val is None:
        return None
    return "normal" if val <= 10 else "elevated"


def _rvot_severity(gradient):
    """RVOT gradient: mild 25–49, moderate 50–79, severe ≥80 mmHg."""
    if gradient is None or gradient < 25:
        return None
    if gradient < 50:
        return "mild"
    if gradient < 80:
        return "moderate"
    return "severe"


def _fontan_level(mean):
    """Fontan/Glenn circuit pressure: normal <15 mmHg; ≥15 elevated."""
    if mean is None:
        return None
    return "normal" if mean < 15 else "elevated"


def _tpg_level(tpg):
    """Transpulmonary gradient: normal <12 mmHg; elevated ≥12 mmHg."""
    if tpg is None:
        return None
    return "normal" if tpg < 12 else "elevated"


def _step_up_description(step_ups):
    """
    Build a specific step-up phrase from the list of detected step-ups.

    Examples:
      []                          → "no significant step-up"
      [atrial]                    → "an atrial-level step-up"
      [ventricular]               → "a ventricular-level step-up"
      [atrial, ventricular]       → "step-ups at the atrial and ventricular levels"
      [atrial, ventricular, PA]   → "step-ups at the atrial, ventricular, and PA levels"
    """
    if not step_ups:
        return "no significant step-up"

    levels = [su["level"] for su in step_ups]

    if len(levels) == 1:
        level = levels[0]
        article = "an" if level[0].lower() in "aeiou" else "a"
        return f"{article} {level}-level step-up"

    # Multiple levels
    if len(levels) == 2:
        return f"step-ups at the {levels[0]} and {levels[1]} levels"

    joined = ", ".join(levels[:-1]) + f", and {levels[-1]}"
    return f"step-ups at the {joined} levels"


# ── Main function ──────────────────────────────────────────────────────────────

def generate_hemodynamic_narrative(hemodynamics, calculations, patient_data, step_ups):
    """
    Generate the full hemodynamic findings narrative (up to 4 paragraphs).
    Paragraphs are separated by double newlines.
    Only sentences for which data are available are included.
    """

    fio2         = patient_data.get("fio2", "21%")
    _avo2_raw    = patient_data.get("avo2")
    _hgb_raw     = patient_data.get("hgb")
    avo2         = float(_avo2_raw) if _avo2_raw not in (None, "", 0) else None
    hgb          = float(_hgb_raw)  if _hgb_raw  not in (None, "", 0) else None
    anatomy_type = patient_data.get("anatomy_type", "biventricle")
    is_fontan_glenn = anatomy_type in ("post_fontan", "post_glenn")

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
    lsvc_sat = _p("LSVC", "sat", hemodynamics)
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

    # Step-up phrase — specific to level(s) detected
    step_up_desc = _step_up_description(step_ups)

    # --- Sentence 1: SVC → right-heart chain ---
    right_chain = []
    if ra_sat is not None:
        right_chain.append(f"RA saturation of {_fmt_sat(ra_sat)}")
    if rv_sat is not None:
        right_chain.append(f"RV saturation of {_fmt_sat(rv_sat)}")
    if lpa_sat is not None:
        right_chain.append(f"LPA saturation of {_fmt_sat(lpa_sat)}")
    if rpa_sat is not None:
        right_chain.append(f"RPA saturation of {_fmt_sat(rpa_sat)}")
    elif mpa_sat is not None:
        right_chain.append(f"MPA saturation of {_fmt_sat(mpa_sat)}")

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
        # No SVC sat but have other right-sided saturations
        sat_sentences.append("Right-sided saturations: " + ", ".join(right_chain) + ".")
        # Still report any detected step-ups as a separate sentence
        if step_ups:
            sat_sentences.append(
                f"There was {step_up_desc} noted through the right-heart."
            )

    # IVC (separate sentence when SVC was already mentioned)
    if svc_sat is not None and ivc_sat is not None:
        sat_sentences.append(f"The IVC saturation was {_fmt_sat(ivc_sat)}.")
    elif svc_sat is None and ivc_sat is not None and not right_chain:
        sat_sentences.append(f"The IVC saturation was {_fmt_sat(ivc_sat)}.")

    # L-SVC saturation
    if lsvc_sat is not None:
        sat_sentences.append(f"The L-SVC saturation was {_fmt_sat(lsvc_sat)}.")

    # --- Pulmonary vein saturations ---
    # Named PV sats take priority over generic RPV/LPV
    named_pv = [(n, v) for n, v in [
        ("RUPV", rupv_sat), ("LUPV", lupv_sat),
        ("RLPV", rlpv_sat), ("LLPV", llpv_sat),
    ] if v is not None]

    generic_pv = [(n, v) for n, v in [
        ("RPV", rpv_sat), ("LPV", lpv_sat),
    ] if v is not None]

    pv_entries = named_pv if named_pv else generic_pv

    if pv_entries:
        pv_vals = [v for _, v in pv_entries]
        any_desaturated = any(v < 95 for v in pv_vals)

        if any_desaturated:
            pv_parts = [f"{_fmt_sat(v)} ({n})" for n, v in pv_entries]
            sat_sentences.append(
                f"There were mixed pulmonary vein desaturations with PV saturations of "
                f"{', '.join(pv_parts)}."
            )
        else:
            unique_vals = list(dict.fromkeys(_fmt_sat(v) for v in pv_vals))
            if len(unique_vals) == 1:
                sat_sentences.append(
                    f"The pulmonary veins were fully saturated with PV saturations of {unique_vals[0]}."
                )
            else:
                pv_parts = [f"{_fmt_sat(v)} ({n})" for n, v in pv_entries]
                sat_sentences.append(
                    f"The pulmonary veins were fully saturated with PV saturations of "
                    f"{', '.join(pv_parts)}."
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
    # RVEDP stored as "mean" by parser for ventricular locations (e.g. 34/3/10)
    rvedp   = _p("RV", "mean", hemodynamics)

    # --- Right-sided filling pressures ---
    if ra_mean is not None or ra_sys is not None or rvedp is not None:
        ra_elev    = ra_mean is not None and ra_mean > 7
        rvedp_elev = rvedp is not None and rvedp > 10
        level = "elevated" if (ra_elev or rvedp_elev) else "normal"

        ra_str = _fmt_press(ra_sys, ra_dia, ra_mean)
        parts = []
        if ra_str:
            parts.append(f"RA pressure {ra_str} mmHg")
        if rvedp is not None:
            rvedp_qualifier = " (elevated)" if rvedp > 10 else ""
            parts.append(f"RVEDP {int(rvedp)} mmHg{rvedp_qualifier}")
        if parts:
            pres_sentences.append(
                f"Right sided filling pressures were {level} with {' and '.join(parts)}."
            )

    # --- RV systolic with RVOT gradient and gradients to branch PAs ---
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

    # For Glenn/Fontan anatomy, PA pressures are mean-only — promote systolic to mean
    if is_fontan_glenn:
        if rpa_mean is None and rpa_sys is not None:
            rpa_mean, rpa_sys, rpa_dia = rpa_sys, None, None
        if lpa_mean is None and lpa_sys is not None:
            lpa_mean, lpa_sys, lpa_dia = lpa_sys, None, None
        if mpa_mean is None and mpa_sys is not None:
            mpa_mean, mpa_sys, mpa_dia = mpa_sys, None, None

    if rv_sys is not None:
        rv_s = f"The RV systolic pressure was {int(rv_sys)} mmHg"

        # RVOT gradient: RV systolic − PA systolic
        pa_sys_for_rvot = rpa_sys or mpa_sys or lpa_sys
        if pa_sys_for_rvot is not None:
            rvot_grad = int(round(rv_sys - pa_sys_for_rvot))
            severity = _rvot_severity(rvot_grad)
            if severity:
                rv_s += f" with a {severity} RVOT gradient of {rvot_grad} mmHg"
            elif rvot_grad > 0:
                rv_s += f" with a {rvot_grad} mmHg gradient to the PA"

        # Gradient to branch PAs
        if rpa_sys is not None or rpa_mean is not None:
            rpa_str  = _fmt_press(rpa_sys, rpa_dia, rpa_mean)
            rpa_grad = _grad_str(rv_sys, rpa_sys)
            if rpa_str and rpa_grad:
                rv_s += f" with {rpa_grad} to RPA pressure {rpa_str} mmHg"
                if lpa_sys is not None or lpa_mean is not None:
                    lpa_str  = _fmt_press(lpa_sys, lpa_dia, lpa_mean)
                    lpa_grad = _grad_str(rv_sys, lpa_sys)
                    if lpa_str and lpa_grad:
                        rv_s += f" and {lpa_grad} to LPA pressure {lpa_str} mmHg"
        elif mpa_sys is not None or mpa_mean is not None:
            mpa_str  = _fmt_press(mpa_sys, mpa_dia, mpa_mean)
            mpa_grad = _grad_str(rv_sys, mpa_sys)
            if mpa_str and mpa_grad:
                rv_s += f" with {mpa_grad} to MPA pressure {mpa_str} mmHg"

        rv_s += "."
        pres_sentences.append(rv_s)

    else:
        # No RV — report PA pressures directly (common for Glenn/Fontan or PA-only data)
        if mpa_sys is not None or mpa_mean is not None:
            mpa_str = _fmt_press(mpa_sys, mpa_dia, mpa_mean)
            if mpa_str:
                pres_sentences.append(f"Main pulmonary artery pressure was {mpa_str} mmHg.")

        # Branch PA pressures when no MPA and no RV
        if mpa_sys is None and mpa_mean is None:
            pa_parts = []
            if rpa_sys is not None or rpa_mean is not None:
                rpa_str = _fmt_press(rpa_sys, rpa_dia, rpa_mean)
                if rpa_str:
                    pa_parts.append(f"RPA pressure {rpa_str} mmHg")
            if lpa_sys is not None or lpa_mean is not None:
                lpa_str = _fmt_press(lpa_sys, lpa_dia, lpa_mean)
                if lpa_str:
                    pa_parts.append(f"LPA pressure {lpa_str} mmHg")
            if pa_parts:
                pres_sentences.append(
                    "Pulmonary artery pressures were: " + " and ".join(pa_parts) + "."
                )

    # --- RPCWP ---
    rpcwp_sys  = _p("RPCWP", "systolic", hemodynamics)
    rpcwp_dia  = _p("RPCWP", "diastolic", hemodynamics)
    rpcwp_mean = _p("RPCWP", "mean", hemodynamics)
    if rpcwp_sys is not None or rpcwp_mean is not None:
        s = _fmt_press(rpcwp_sys, rpcwp_dia, rpcwp_mean)
        if s:
            pres_sentences.append(f"The right pulmonary capillary wedge pressure was {s} mmHg.")

    # --- LPCWP with transpulmonary gradient ---
    lpcwp_sys  = _p("LPCWP", "systolic", hemodynamics)
    lpcwp_dia  = _p("LPCWP", "diastolic", hemodynamics)
    lpcwp_mean = _p("LPCWP", "mean", hemodynamics)
    if lpcwp_sys is not None or lpcwp_mean is not None:
        s = _fmt_press(lpcwp_sys, lpcwp_dia, lpcwp_mean)
        if s:
            tpg = calculations.get("tpg")
            if tpg is not None:
                tpg_desc = _tpg_level(tpg)
                pres_sentences.append(
                    f"The left pulmonary capillary wedge pressure was {s} mmHg, "
                    f"yielding a transpulmonary gradient of {int(round(tpg))} mmHg ({tpg_desc})."
                )
            else:
                pres_sentences.append(
                    f"The left pulmonary capillary wedge pressure was {s} mmHg."
                )
    elif rpcwp_sys is not None or rpcwp_mean is not None:
        # Only RPCWP present — still report TPG if calculable
        tpg = calculations.get("tpg")
        if tpg is not None:
            tpg_desc = _tpg_level(tpg)
            pres_sentences.append(
                f"The transpulmonary gradient was {int(round(tpg))} mmHg ({tpg_desc})."
            )

    # --- LA pressure ---
    la_sys  = _p("LA", "systolic", hemodynamics)
    la_dia  = _p("LA", "diastolic", hemodynamics)
    la_mean = _p("LA", "mean", hemodynamics)
    if la_sys is not None or la_mean is not None:
        s = _fmt_press(la_sys, la_dia, la_mean)
        if s:
            la_lvl    = _la_level(la_mean)
            qualifier = f" ({la_lvl})" if la_lvl else ""
            pres_sentences.append(f"LA pressure was {s} mmHg{qualifier}.")

    # --- PV pressure to LA gradient ---
    rpv_sys   = _p("RPV", "systolic", hemodynamics)
    rpv_dia   = _p("RPV", "diastolic", hemodynamics)
    rpv_mean  = _p("RPV", "mean", hemodynamics)
    lpv_sys   = _p("LPV", "systolic", hemodynamics)
    lpv_dia   = _p("LPV", "diastolic", hemodynamics)
    lpv_mean  = _p("LPV", "mean", hemodynamics)
    rupv_mean = _p("RUPV", "mean", hemodynamics)
    lupv_mean = _p("LUPV", "mean", hemodynamics)
    rlpv_mean = _p("RLPV", "mean", hemodynamics)
    llpv_mean = _p("LLPV", "mean", hemodynamics)

    pv_sys_val  = rpv_sys  or lpv_sys
    pv_dia_val  = rpv_dia  or lpv_dia
    pv_mean_val = rpv_mean or lpv_mean or rupv_mean or lupv_mean or rlpv_mean or llpv_mean

    if (pv_sys_val is not None or pv_mean_val is not None) and la_mean is not None:
        pv_str  = _fmt_press(pv_sys_val, pv_dia_val, pv_mean_val)
        compare = pv_mean_val if pv_mean_val is not None else pv_sys_val
        grad    = _grad_str(compare, la_mean)
        if pv_str and grad:
            pres_sentences.append(
                f"There was {grad} from pulmonary vein pressures of {pv_str} mmHg to LA pressure."
            )

    # --- LV pressure with LVEDP normality and gradient to aorta ---
    lv_sys = _p("LV", "systolic", hemodynamics)
    lv_dia = _p("LV", "diastolic", hemodynamics)
    lvedp  = _p("LV", "mean", hemodynamics)  # mean = LVEDP for ventricular locations

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

        # LVEDP normality (separate sentence)
        if lvedp is not None and lvedp > 10:
            pres_sentences.append(f"LVEDP was {int(lvedp)} mmHg (elevated).")

    elif lv_dia is not None:
        lvedp_lvl = _vedp_level(lv_dia)
        qualifier = f" ({lvedp_lvl})" if lvedp_lvl else ""
        pres_sentences.append(f"LVEDP was {int(lv_dia)} mmHg{qualifier}.")

    # Standalone descending aorta (when no LV data)
    if lv_sys is None and lv_dia is None and desc_ao_sys is not None:
        desc_str = _fmt_press(desc_ao_sys, desc_ao_dia, desc_ao_mean)
        if desc_str:
            pres_sentences.append(f"Descending aorta pressure was {desc_str} mmHg.")

    # --- Glenn and Fontan circuit pressures ---
    # Use _mean_or_sys to capture single values stored as systolic by the parser.
    fontan_p = _mean_or_sys("Fontan_IVC_limb", hemodynamics)
    if fontan_p is None:
        fontan_p = _mean_or_sys("Fontan_conduit", hemodynamics)
    if fontan_p is not None:
        f_lvl     = _fontan_level(fontan_p)
        qualifier = f" ({f_lvl})" if f_lvl else ""
        pres_sentences.append(f"Fontan circuit pressure was {int(fontan_p)} mmHg{qualifier}.")

    glenn_p = _mean_or_sys("Glenn_anastomosis", hemodynamics)
    if glenn_p is not None:
        g_lvl     = _fontan_level(glenn_p)
        qualifier = f" ({g_lvl})" if g_lvl else ""
        pres_sentences.append(f"Glenn anastomosis pressure was {int(glenn_p)} mmHg{qualifier}.")

    # For Glenn/Fontan anatomy, report branch PA mean pressures if not yet captured above
    if is_fontan_glenn:
        # After the promote-systolic-to-mean pass earlier, rpa_mean/lpa_mean may be populated
        # even if rv_sys was None. Report them if they weren't already in the RV sentence.
        if rv_sys is None:
            pa_parts = []
            if rpa_mean is not None:
                pa_parts.append(f"RPA mean {int(rpa_mean)} mmHg")
            if lpa_mean is not None:
                pa_parts.append(f"LPA mean {int(lpa_mean)} mmHg")
            if mpa_mean is not None:
                pa_parts.append(f"MPA mean {int(mpa_mean)} mmHg")
            if pa_parts:
                pres_sentences.append(
                    "Pulmonary artery mean pressures were " + ", ".join(pa_parts) + "."
                )

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
        # Both avo2 and hgb must be present for qs to be non-None (enforced in hemodynamics.py)
        avo2_str = str(int(avo2)) if avo2 is not None else "?"
        hgb_str  = (
            f"{hgb:.1f}".rstrip("0").rstrip(".")
            if hgb is not None and hgb != int(hgb)
            else (str(int(hgb)) if hgb is not None else "?")
        )
        # Wording matches document template exactly
        calc_sentences.append(
            f"Using Fick and an assumed aVO\u2082 of {avo2_str} mL/min/m\u00b2 "
            f"and hemoglobin of {hgb_str} g/dL, "
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

    # Calculation warnings — suppress the "skipped" note (absent para4 speaks for itself)
    warnings = [
        w for w in calculations.get("warnings", [])
        if "Fick flow calculations skipped" not in w
    ]
    if warnings:
        calc_sentences.append("Note: " + "; ".join(warnings) + ".")

    para4 = " ".join(calc_sentences) if calc_sentences else ""

    # ═══════════════════════════════════════════════════════════════════════
    # Assemble — skip empty paragraphs
    # ═══════════════════════════════════════════════════════════════════════
    paragraphs = [p for p in [para1, para2, para3, para4] if p.strip()]
    return "\n\n".join(paragraphs)
