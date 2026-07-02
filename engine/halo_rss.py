"""HALO RSS advisory logic for vibration mitigation workflows.

This is prototype decision-support logic. Field users must validate every
action with active DD, company, and OEM procedures before changing parameters.
"""


def pct(value, change):
    return round(value * (1 + change / 100.0), 2)


def halo_rss_assessment(data):
    alerts = []
    rpm = float(data.get("rpm", 0) or 0)
    wob = float(data.get("wob", 0) or 0)
    torque = float(data.get("torque", 0) or 0)
    lateral = float(data.get("lateral_vib", 0) or 0)
    torsional = float(data.get("torsional_vib", 0) or 0)
    delta = float(data.get("delta_vibes", 0) or 0)
    shock = float(data.get("shock_count", 0) or 0)
    stick = float(data.get("stick_slip", 0) or 0)
    torque_osc = bool(data.get("torque_oscillation", False))

    if delta >= 4:
        alerts.append(
            {
                "module": "HALO RSS Coach",
                "level": "CRITICAL" if delta >= 6 else "WARNING",
                "problem": "Possible HFTO vibration",
                "confidence": 90,
                "evidence": [
                    f"Delta Vibes: {delta} g RMS",
                    f"RPM: {rpm}",
                    f"WOB: {wob} klb",
                    "HALO workflow trigger: repeated Delta Vibes above 4 g RMS",
                ],
                "likely_cause": "High-frequency torsional oscillation or dynamic instability while drilling.",
                "recommended_action": [
                    f"If allowed by surface RPM and flow limits, increase bit/surface RPM 5-10%: target {pct(rpm, 5)} to {pct(rpm, 10)} RPM. Observe response.",
                    "If vibration is not mitigated, increase RPM another 5-10% and observe.",
                    "If no improvement, reduce RPM back to original value.",
                    f"Then reduce WOB by 15%: target about {pct(wob, -15)} klb. Observe response.",
                    "If unresolved, reduce bit RPM 5-10%; if still severe, pick up off bottom, allow string torque to unwind, restart at minimum operating parameters, and step parameters up.",
                    "Drill ahead only with improved parameters until out of the trouble zone.",
                ],
                "procedure_source": "HALO RSS Appendix B - HFTO Vibration Mitigation",
            }
        )

    if lateral >= 7.5 or shock >= 10:
        alerts.append(
            {
                "module": "HALO RSS Coach",
                "level": "CRITICAL" if lateral >= 15 else "WARNING",
                "problem": "Possible bit whirl / lateral vibration",
                "confidence": 88 if lateral >= 7.5 else 75,
                "evidence": [
                    f"Lateral vibration: {lateral} g",
                    f"Shock count: {shock}",
                    f"Torque: {torque} klb-ft",
                    f"RPM: {rpm}",
                ],
                "likely_cause": "Lateral instability, bit whirl, BHA contact, or formation-driven vibration.",
                "recommended_action": [
                    f"Decrease bit RPM 5-10%: target {pct(rpm, -10)} to {pct(rpm, -5)} RPM.",
                    f"Increase WOB 5-10% if within drilling limits: target {pct(wob, 5)} to {pct(wob, 10)} klb.",
                    "If whirl is not reduced, repeat the RPM reduction / WOB increase once and observe.",
                    "If unresolved, pick up off bottom and allow string torque to unwind.",
                    f"Restart drilling with WOB around 110% of original ({pct(wob, 10)} klb) and RPM at original value ({rpm} RPM).",
                    "If still unstable, manage as best possible and consider BHA adjustments: bit, motor, stabilizers, RSS spacing/configuration.",
                ],
                "procedure_source": "HALO RSS Appendix B - Bit Whirl / Lateral Vibration Mitigation",
            }
        )

    if stick > 0 or torque_osc or torsional >= 5:
        alerts.append(
            {
                "module": "HALO RSS Coach",
                "level": "CRITICAL" if stick >= 50 or torsional >= 10 else "WARNING",
                "problem": "Possible stick-slip / torsional vibration",
                "confidence": 92 if torque_osc or stick > 0 else 75,
                "evidence": [
                    f"Stick-slip indicator: {stick}",
                    f"Torsional vibration: {torsional}",
                    f"Torque oscillation: {'Yes' if torque_osc else 'No'}",
                    f"RPM: {rpm}",
                    f"WOB: {wob} klb",
                ],
                "likely_cause": "Torsional instability caused by bit/formation interaction, excessive WOB, low RPM, or BHA friction.",
                "recommended_action": [
                    f"Increase bit RPM 5-10%: target {pct(rpm, 5)} to {pct(rpm, 10)} RPM.",
                    f"Decrease WOB 5-10%: target {pct(wob, -10)} to {pct(wob, -5)} klb.",
                    "If stick-slip is not reduced, repeat the RPM increase / WOB decrease once and observe.",
                    "If unresolved, pick up off bottom and allow string torque to unwind.",
                    f"Restart around RPM 110% of original ({pct(rpm, 10)} RPM) and WOB 85% of original ({pct(wob, -15)} klb).",
                    f"If still unstable, restart around RPM 50% of original ({pct(rpm, -50)} RPM), WOB 75% of original ({pct(wob, -25)} klb), then gradually increase RPM until stable.",
                ],
                "procedure_source": "HALO RSS Appendix B - Stick Slip / Torsional Vibration Mitigation",
            }
        )

    return alerts


def drilling_stability_score(data):
    score = 100
    score -= min(float(data.get("delta_vibes", 0) or 0) * 8, 30)
    score -= min(float(data.get("lateral_vib", 0) or 0) * 2, 25)
    score -= min(float(data.get("stick_slip", 0) or 0) * 0.5, 25)
    score -= min(float(data.get("shock_count", 0) or 0) * 1.5, 20)
    return max(0, round(score, 1))
