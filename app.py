import streamlit as st
from datetime import datetime

st.set_page_config(page_title="MWD Troubleshooting Assistant", page_icon="🛠️", layout="wide")

st.title("🛠️ MWD Troubleshooting Assistant")
st.caption("Prototype MVP: guided troubleshooting for No Pulse, Pulse Present / Not Decoding, Weak Pulses, and Downlink Issues")

# -----------------------------
# Rule Engine
# -----------------------------

def add_step(steps, title, details, area="", priority="Normal"):
    steps.append({"area": area, "title": title, "details": details, "priority": priority})


def diagnose(data):
    steps = []
    causes = []
    problem = data["problem"]

    if problem == "No Pulses Detected":
        causes += ["Tool not pulsing", "Surface transducer/signal issue", "Hydraulic/pump issue", "Pulser/orifice plugged", "Tool unseated", "Receiver/software frozen"]
        add_step(steps, "Confirm pulse waveform is updating", "Check if the MWD pulse waveform window is moving. If frozen, restart/verify the software and computer.", "Area A - Inside Unit", "High")
        add_step(steps, "Confirm standpipe pressure is visible", "If SPP is not displayed, check receiver, transducer cable, interface, power, and software communication.", "Area A - Inside Unit", "High")
        if data["temp_c"] and data["temp_c"] >= 150:
            add_step(steps, "Temperature limit warning", "Downhole temperature is at or above normal operating limit. Escalate and consider removing tool per company procedure.", "Area A - Limits", "Critical")
        if data["vibration"] == "High":
            add_step(steps, "Vibration limit warning", "High vibration may damage or disable the tool. Reduce vibration and escalate if limits were exceeded.", "Area A - Limits", "Critical")
        add_step(steps, "Check analog standpipe gauge", "Look for pressure fluctuations at expected pulse timing. If visible on gauge but not software, suspect surface acquisition/transducer/receiver issue.", "Area B - Outside Unit", "High")
        add_step(steps, "Vary pump rate", "Try different flow rates: one pump, two pumps, and the pump not in use when failure occurred.", "Area B - Pumps", "High")
        add_step(steps, "Hydraulic system check", "Check mud aeration/foam, high solids, suction/pipe screens, LCM mixing, mixing pump, and dampener pressure.", "Area B - Hydraulics", "High")
        add_step(steps, "Pump sweep if possible", "Circulate off bottom and pump water/high-vis pill if allowed to clear solids from MWD pulser/orifice.", "Area C - Downhole", "Normal")
        add_step(steps, "Work drill string", "If tool may be unseated, pick up off bottom, work pipe carefully, rotate, then bring pumps up and check for pulses.", "Area C - Downhole", "Normal")
        add_step(steps, "Resynchronize", "Pumps off, wait at least one minute without moving string, bring pumps up rapidly to operating pressure, watch for sync pulses for 5 minutes.", "Area C - Downhole", "Normal")
        add_step(steps, "Surface inspection", "If unresolved, pull tool. Inspect muleshoe, float valve, signal shaft, clearance below muleshoe, and perform shallow test.", "Area D - Surface", "High")

    elif problem == "Pulses Present But Not Decoding":
        causes += ["Threshold settings incorrect", "Low quality/confidence", "Tool/receiver mode mismatch", "Filter setting issue", "Surface receiver/power/cable issue", "Transducer issue", "Hydraulic noise"]
        add_step(steps, "Verify waveform pulses", "Confirm pulses are visible and consistent in the waveform window.", "Area A - Inside Unit", "High")
        if data["quality"] and data["quality"] < 70:
            add_step(steps, "Quality below target", f"Quality is {data['quality']}%. Target is generally >70%. Check noise, filters, thresholds, and pulse shape.", "Area A - Decoder", "High")
        if data["confidence"] and data["confidence"] < 80:
            add_step(steps, "Confidence below target", f"Confidence is {data['confidence']}%. Target is generally >80%. Verify sync, thresholds, and mode match.", "Area A - Decoder", "High")
        add_step(steps, "Check HiPL and LoPL", "Set LoPL above noise. HiPL should be above expected pulse amplitude but below torque-wave/stall pressure spikes.", "Area A - Decoder", "High")
        add_step(steps, "Check final bandwidth filter", "Verify filter settings are correct for the pulse window and not clipping the signal.", "Area A - Decoder", "Normal")
        if data["downlink_enabled"]:
            add_step(steps, "Mode match check", "If downlink is enabled, confirm tool mode matches surface receiver mode. Downlink to same mode if necessary.", "Area A - Downlink", "High")
        add_step(steps, "Small pulse workaround", "If pulses are small and flow cannot be increased, downlink to a wider pulse width where allowed.", "Area A - Downlink", "Normal")
        add_step(steps, "Cycle receiver power", "Power-cycle receiver/interface. If still failing, continue to cable/power/interface checks.", "Area A - Receiver", "Normal")
        add_step(steps, "Inspect and clean cable connections", "Clean and reseat connectors. Inspect cables for damage and replace if necessary.", "Area B - Outside Unit", "High")
        add_step(steps, "Check pressure transducer", "Inspect diaphragm for damage/debris/ice/LCM. Clean and reinstall or replace as needed.", "Area B - Transducer", "High")
        add_step(steps, "Hydraulic system check", "Check standpipe stability, air/foam, solids/screens, dampener pressure, LCM mixing.", "Area B - Hydraulics", "Normal")
        add_step(steps, "Surface inspection if unresolved", "If no decode remains unresolved, pull tool and inspect muleshoe, float valve, signal shaft, clearance, and shallow test.", "Area D - Surface", "High")

    elif problem == "Weak Pulses":
        causes += ["Low flow", "Partial pulser/orifice plugging", "LCM/debris", "Dampener issue", "Aerated mud", "Transducer sensitivity issue"]
        add_step(steps, "Compare flow to tool range", "Confirm flow rate is inside the pulser/orifice operating range.", "Area B - Pumps", "High")
        add_step(steps, "Try higher and lower flow", "Test controlled flow changes and observe pulse amplitude response.", "Area B - Pumps", "High")
        add_step(steps, "Check dampener setting", "Normal dampener precharge is commonly checked against about one third of system pressure, per procedure.", "Area B - Hydraulics", "Normal")
        add_step(steps, "Check mud condition", "Look for air/foam, solids, poorly mixed LCM, plugged screens, or soap stick residue.", "Area B - Hydraulics", "High")
        add_step(steps, "Quick pump cycles", "If allowed by company/rig procedure, use controlled pump cycles to help clear LCM/debris from pulser/orifice.", "Area C - Downhole", "Normal")
        add_step(steps, "Check transducer", "Inspect diaphragm and port for debris, damage, ice, or mud buildup.", "Area B - Transducer", "Normal")

    elif problem == "Downlink Failed":
        causes += ["Incorrect pump timing", "Mode window missed", "Pump response lag", "Tool/receiver mode mismatch", "Flow not reaching required command state"]
        add_step(steps, "Check pump timing", "Compare pumps up/down timing against the programmed command time period and mode sequence.", "Downlink", "High")
        add_step(steps, "Allow pump response tolerance", "Rig pumps may be sluggish. Use consistent timing and verify pressure actually changed, not just command state.", "Downlink", "High")
        add_step(steps, "Verify command window", "Any missing action or action outside the command window can invalidate the downlink procedure.", "Downlink", "High")
        add_step(steps, "Confirm tool/receiver mode", "If pulses are present but not decoding after downlink, confirm tool and receiver are in the same mode.", "Downlink", "High")
        add_step(steps, "Repeat with controlled sequence", "Repeat downlink only after pumps are stable and timing is verified. Record each pump transition time.", "Downlink", "Normal")

    # Smart hints based on values
    if data["spp_stable"] == "No":
        add_step(steps, "Standpipe pressure unstable", "Unstable SPP can distort or hide pulses. Check pumps, dampeners, air/foam, screens, and mud condition.", "Auto-Detected", "Critical")
    if data["pulse_amp"] is not None and data["pulse_amp"] < 5 and problem != "No Pulses Detected":
        add_step(steps, "Low pulse amplitude", f"Pulse amplitude is {data['pulse_amp']} psi. Check flow, pulser/orifice plugging, dampener, mud aeration, and transducer.", "Auto-Detected", "High")

    return causes, steps

# -----------------------------
# UI
# -----------------------------

with st.sidebar:
    st.header("Job Info")
    rig = st.text_input("Rig / Well", "")
    operator = st.text_input("MWD Operator", "")
    st.divider()
    st.caption("Prototype only. Follow company procedures and rig-site authority.")

col1, col2 = st.columns([1, 1])
with col1:
    problem = st.selectbox("Select Problem", ["No Pulses Detected", "Pulses Present But Not Decoding", "Weak Pulses", "Downlink Failed"])
    spp = st.number_input("Standpipe Pressure (psi)", min_value=0, value=0, step=50)
    flow = st.number_input("Flow Rate (GPM)", min_value=0, value=0, step=10)
    pulse_amp = st.number_input("Pulse Amplitude (psi)", min_value=0.0, value=0.0, step=0.5)
with col2:
    quality = st.number_input("Decoder Quality (%)", min_value=0, max_value=100, value=0)
    confidence = st.number_input("Decoder Confidence (%)", min_value=0, max_value=100, value=0)
    temp_c = st.number_input("Downhole Temp (°C)", min_value=0, value=0, step=1)
    vibration = st.selectbox("Vibration Status", ["Normal", "High", "Unknown"])
    spp_stable = st.selectbox("Is SPP Stable?", ["Yes", "No", "Unknown"])
    downlink_enabled = st.checkbox("Downlink Enabled")

run = st.button("Diagnose", type="primary")

if run:
    data = {
        "problem": problem,
        "spp": spp,
        "flow": flow,
        "pulse_amp": pulse_amp if pulse_amp > 0 else None,
        "quality": quality if quality > 0 else None,
        "confidence": confidence if confidence > 0 else None,
        "temp_c": temp_c if temp_c > 0 else None,
        "vibration": vibration,
        "spp_stable": spp_stable,
        "downlink_enabled": downlink_enabled,
    }
    causes, steps = diagnose(data)

    st.subheader("AI Diagnostic Summary")
    st.write(f"**Problem:** {problem}")
    st.write(f"**Likely Causes:** {', '.join(causes)}")

    st.subheader("Recommended Troubleshooting Steps")
    for i, step in enumerate(steps, 1):
        with st.expander(f"{i}. [{step['priority']}] {step['title']} — {step['area']}", expanded=i <= 4):
            st.write(step["details"])
            st.checkbox("Completed", key=f"step_{i}")

    causes_text = "\n- ".join(causes)
    steps_text = "\n".join([f"{i+1}. {s['title']} ({s['area']}): {s['details']}" for i, s in enumerate(steps)])
    report = f"""
MWD Troubleshooting Report
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Rig/Well: {rig}
Operator: {operator}
Problem: {problem}
SPP: {spp} psi
Flow: {flow} GPM
Pulse Amplitude: {pulse_amp} psi
Quality: {quality}%
Confidence: {confidence}%
Temperature: {temp_c} C
Vibration: {vibration}
SPP Stable: {spp_stable}
Downlink Enabled: {downlink_enabled}

Likely Causes:
- {causes_text}

Steps:
{steps_text}
"""
    st.download_button("Download Report", report, file_name="mwd_troubleshooting_report.txt")

st.divider()
st.caption("Next build: connect live WITS/WITSML/CSV data and add manual-based AI search.")
