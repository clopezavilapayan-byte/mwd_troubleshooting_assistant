def analyze_mwd_data(data):
    alerts = []

    if data["sync_status"] in ["No Sync", "Poor Sync", "Sync Hunt"]:
        alerts.append(
            {
                "level": "CRITICAL" if data["sync_status"] == "No Sync" else "WARNING",
                "problem": "MWD sync issue detected",
                "evidence": [
                    f'Sync Status: {data["sync_status"]}',
                    f'Decode Confidence: {data["decode_confidence"]}%',
                    f'Correlation: {data["correlation"]}',
                    f'Pulse Pressure: {data["pulse_pressure"]} psi',
                ],
                "likely_cause": "Weak pulse signal, unstable standpipe pressure, pump noise, or decoder not locked.",
                "recommended_action": [
                    "Confirm pumps are on and flow is stable.",
                    "Check standpipe pressure trend for noise or cycling.",
                    "Verify pulse pressure is visible and consistent.",
                    "Confirm active pump and ask driller about valve/seat condition.",
                    "Switch pumps if pressure instability is suspected.",
                    "Do not change FFT or major decoder settings until hydraulic issues are ruled out.",
                ],
                "procedure_source": "KB-0001: No Sync / Weak Pulse Troubleshooting",
            }
        )

    if data["decode_confidence"] < 80 or data["correlation"] < 85:
        alerts.append(
            {
                "level": "WARNING",
                "problem": "Decode quality dropping",
                "evidence": [
                    f'Decode Confidence: {data["decode_confidence"]}%',
                    f'Correlation: {data["correlation"]}',
                    f'Correlation Margin: {data["correlation_margin"]}',
                ],
                "likely_cause": "Poor signal-to-noise ratio, weak pulses, pump noise, or incorrect decoder alignment.",
                "recommended_action": [
                    "Review oscilloscope waveform for pulse visibility.",
                    "Check if SPP is stable while pulses are visible.",
                    "Compare pulse pressure against normal operating range.",
                    "Check pump condition before changing decode filters.",
                    "Escalate if confidence continues falling.",
                ],
                "procedure_source": "KB-0002: Decode Confidence / Correlation Drop",
            }
        )

    if data["pulse_pressure"] < 10:
        alerts.append(
            {
                "level": "WARNING",
                "problem": "Weak pulse pressure",
                "evidence": [
                    f'Pulse Pressure: {data["pulse_pressure"]} psi',
                    f'SPP: {data["spp"]} psi',
                    f'Pump Rate: {data["pump_rate"]} gpm',
                ],
                "likely_cause": "Low signal amplitude, insufficient flow, pulser issue, or noisy pumps masking pulses.",
                "recommended_action": [
                    "Confirm expected pulse pressure for current tool/program.",
                    "Verify flow rate and pump output.",
                    "Check if pulses are visible on pressure trace.",
                    "Inspect for hydraulic noise or pressure instability.",
                    "Do not assume software issue until hydraulic signal is confirmed.",
                ],
                "procedure_source": "KB-0003: Weak Pulse Pressure",
            }
        )

    if data["lateral_vib"] >= 20:
        alerts.append(
            {
                "level": "WARNING",
                "problem": "Elevated lateral vibration",
                "evidence": [
                    f'Lateral Vibration: {data["lateral_vib"]}',
                    f'RPM: {data["rpm"]}',
                    f'WOB: {data["wob"]} klb',
                    f'Torque: {data["torque"]} klb-ft',
                ],
                "likely_cause": "BHA whirl, aggressive drilling parameters, formation change, or poor weight transfer.",
                "recommended_action": [
                    "Reduce surface RPM in small increments if allowed.",
                    "Review WOB and torque response.",
                    "Watch for stick-slip or toolface instability.",
                    "Coordinate changes with DD and directional plan.",
                ],
                "procedure_source": "KB-0004: Vibration Risk Troubleshooting",
            }
        )

    if data["stick_slip"] > 0:
        alerts.append(
            {
                "level": "WARNING",
                "problem": "Stick-slip risk detected",
                "evidence": [
                    f'Stick-Slip Risk: {data["stick_slip"]}',
                    f'RPM: {data["rpm"]}',
                    f'Torque: {data["torque"]} klb-ft',
                ],
                "likely_cause": "Torsional dysfunction caused by bit/formation interaction, excessive WOB, or RPM mismatch.",
                "recommended_action": [
                    "Review torque oscillation trend.",
                    "Consider reducing WOB or adjusting RPM.",
                    "Avoid aggressive parameter changes without DD/driller alignment.",
                    "Monitor MWD/RSS vibration response after each change.",
                ],
                "procedure_source": "KB-0004: Vibration Risk Troubleshooting",
            }
        )

    return alerts
