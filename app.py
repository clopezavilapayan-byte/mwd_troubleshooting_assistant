import csv
import io
import re

import streamlit as st
from datetime import datetime

st.set_page_config(page_title="MWD Troubleshooting Assistant", page_icon="🛠️", layout="wide")

st.title("🛠️ MWD Troubleshooting Assistant")
st.caption("Prototype MVP: guided troubleshooting for No Pulse, Pulse Present / Not Decoding, Weak Pulses, and Downlink Issues")

PROBLEM_OPTIONS = ["No Pulses Detected", "Pulses Present But Not Decoding", "Weak Pulses", "Downlink Failed"]
VIBRATION_OPTIONS = ["Normal", "High", "Unknown"]
SPP_STABLE_OPTIONS = ["Yes", "No", "Unknown"]

COLUMN_ALIASES = {
    "problem": ["problem", "issue", "event", "failure", "diagnosis"],
    "spp": ["spp", "standpipe_pressure", "standpipepressure", "pressure", "stand_pipe_pressure"],
    "flow": ["flow", "flow_rate", "flowrate", "gpm", "pump_rate", "pumprate"],
    "pulse_amp": ["pulse_amp", "pulse_amplitude", "pulseamplitude", "pulse_psi", "amplitude"],
    "quality": ["quality", "decoder_quality", "decode_quality", "signal_quality"],
    "confidence": ["confidence", "decoder_confidence", "decode_confidence"],
    "temp_c": ["temp_c", "temperature_c", "downhole_temp", "downhole_temperature", "temp"],
    "vibration": ["vibration", "vibration_status", "vibe_status"],
    "spp_stable": ["spp_stable", "pressure_stable", "standpipe_stable", "stable_spp"],
    "downlink_enabled": ["downlink_enabled", "downlink", "downlink_on"],
    "downlink_failed": ["downlink_failed", "downlink_fail"],
    "downlink_success": ["downlink_success", "downlink_ok"],
    "pulses_present": ["pulses_present", "pulse_present", "pulsing", "has_pulse"],
    "decoding": ["decoding", "decode", "decoded", "is_decoding"],
}

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


def clean_key(value):
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def read_csv_upload(uploaded_file):
    raw = uploaded_file.getvalue()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    rows = list(csv.DictReader(io.StringIO(text)))
    return [row for row in rows if any(str(value).strip() for value in row.values())]


def pick_value(row, aliases):
    normalized = {clean_key(key): value for key, value in row.items()}
    for alias in aliases:
        value = normalized.get(clean_key(alias))
        if value is not None and str(value).strip() != "":
            return value
    return None


def to_float(value):
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {"", "none", "null", "nan", "n/a"}:
        return None
    text = re.sub(r"[^0-9.\-]", "", text.replace(",", ""))
    if text in {"", "-", ".", "-."}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_int(value):
    number = to_float(value)
    return int(round(number)) if number is not None else None


def to_bool(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1", "on", "enabled", "pass", "ok"}:
        return True
    if text in {"false", "no", "n", "0", "off", "disabled", "fail", "failed"}:
        return False
    return None


def clamp_int(value, low, high=None):
    if value is None:
        return low
    value = max(low, int(value))
    return min(value, high) if high is not None else value


def normalize_problem(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if "downlink" in text:
        return "Downlink Failed"
    if "weak" in text or "low pulse" in text or "small pulse" in text:
        return "Weak Pulses"
    if "not decoding" in text or "no decode" in text or "decode" in text:
        return "Pulses Present But Not Decoding"
    if "no pulse" in text or "no pulses" in text or "lost pulse" in text:
        return "No Pulses Detected"
    for option in PROBLEM_OPTIONS:
        if clean_key(option) == clean_key(text):
            return option
    return None


def normalize_choice(value, options, default):
    if value is None:
        return default
    key = clean_key(value)
    for option in options:
        if clean_key(option) == key:
            return option
    return default


def infer_problem(data, row):
    downlink_failed = to_bool(pick_value(row, COLUMN_ALIASES["downlink_failed"]))
    downlink_success = to_bool(pick_value(row, COLUMN_ALIASES["downlink_success"]))
    pulses_present = to_bool(pick_value(row, COLUMN_ALIASES["pulses_present"]))
    decoding = to_bool(pick_value(row, COLUMN_ALIASES["decoding"]))

    if downlink_failed is True or downlink_success is False:
        return "Downlink Failed"
    if pulses_present is False:
        return "No Pulses Detected"
    if data["pulse_amp"] is not None:
        if data["pulse_amp"] <= 0 and (data["flow"] or 0) > 0:
            return "No Pulses Detected"
        if 0 < data["pulse_amp"] < 5:
            return "Weak Pulses"
    if decoding is False:
        return "Pulses Present But Not Decoding"
    if data["quality"] is not None and data["quality"] < 70:
        return "Pulses Present But Not Decoding"
    if data["confidence"] is not None and data["confidence"] < 80:
        return "Pulses Present But Not Decoding"
    return "No Pulses Detected"


def row_to_data(row):
    data = {
        "problem": normalize_problem(pick_value(row, COLUMN_ALIASES["problem"])),
        "spp": to_int(pick_value(row, COLUMN_ALIASES["spp"])),
        "flow": to_int(pick_value(row, COLUMN_ALIASES["flow"])),
        "pulse_amp": to_float(pick_value(row, COLUMN_ALIASES["pulse_amp"])),
        "quality": to_int(pick_value(row, COLUMN_ALIASES["quality"])),
        "confidence": to_int(pick_value(row, COLUMN_ALIASES["confidence"])),
        "temp_c": to_int(pick_value(row, COLUMN_ALIASES["temp_c"])),
        "vibration": normalize_choice(pick_value(row, COLUMN_ALIASES["vibration"]), VIBRATION_OPTIONS, "Unknown"),
        "spp_stable": normalize_choice(pick_value(row, COLUMN_ALIASES["spp_stable"]), SPP_STABLE_OPTIONS, "Unknown"),
        "downlink_enabled": to_bool(pick_value(row, COLUMN_ALIASES["downlink_enabled"])) or False,
    }
    data["problem"] = data["problem"] or infer_problem(data, row)
    return data

# -----------------------------
# UI
# -----------------------------

with st.sidebar:
    st.header("Job Info")
    rig = st.text_input("Rig / Well", "")
    operator = st.text_input("MWD Operator", "")
    st.divider()
    st.caption("Prototype only. Follow company procedures and rig-site authority.")

input_mode = st.radio("Input Mode", ["Manual", "CSV / Live Data"], horizontal=True)
auto_data = {}
auto_ready = False
auto_run = False
data_source = "Manual entry"

if input_mode == "CSV / Live Data":
    uploaded_file = st.file_uploader("CSV readings", type=["csv"])
    auto_run = st.checkbox("Auto diagnose latest row", value=True)
    if uploaded_file is not None:
        try:
            rows = read_csv_upload(uploaded_file)
            if rows:
                latest_row = rows[-1]
                auto_data = row_to_data(latest_row)
                auto_ready = True
                data_source = f"CSV latest row: {uploaded_file.name}"
                st.write(f"Rows received: {len(rows)}")
                st.dataframe([latest_row], use_container_width=True)
                st.info(f"Inferred problem: {auto_data['problem']}")
            else:
                st.warning("CSV received, but no populated data rows were found.")
        except Exception as exc:
            st.error(f"Could not read CSV data: {exc}")

defaults = auto_data if auto_ready else {}
problem_default = defaults.get("problem", PROBLEM_OPTIONS[0])
vibration_default = defaults.get("vibration", "Normal")
spp_stable_default = defaults.get("spp_stable", "Yes")

col1, col2 = st.columns([1, 1])
with col1:
    problem = st.selectbox("Select Problem", PROBLEM_OPTIONS, index=PROBLEM_OPTIONS.index(problem_default))
    spp = st.number_input("Standpipe Pressure (psi)", min_value=0, value=clamp_int(defaults.get("spp"), 0), step=50)
    flow = st.number_input("Flow Rate (GPM)", min_value=0, value=clamp_int(defaults.get("flow"), 0), step=10)
    pulse_amp = st.number_input("Pulse Amplitude (psi)", min_value=0.0, value=float(defaults.get("pulse_amp") or 0.0), step=0.5)
with col2:
    quality = st.number_input("Decoder Quality (%)", min_value=0, max_value=100, value=clamp_int(defaults.get("quality"), 0, 100))
    confidence = st.number_input("Decoder Confidence (%)", min_value=0, max_value=100, value=clamp_int(defaults.get("confidence"), 0, 100))
    temp_c = st.number_input("Downhole Temp (°C)", min_value=0, value=clamp_int(defaults.get("temp_c"), 0), step=1)
    vibration = st.selectbox("Vibration Status", VIBRATION_OPTIONS, index=VIBRATION_OPTIONS.index(vibration_default))
    spp_stable = st.selectbox("Is SPP Stable?", SPP_STABLE_OPTIONS, index=SPP_STABLE_OPTIONS.index(spp_stable_default))
    downlink_enabled = st.checkbox("Downlink Enabled", value=bool(defaults.get("downlink_enabled", False)))

run_clicked = st.button("Diagnose", type="primary")
run = run_clicked or (input_mode == "CSV / Live Data" and auto_ready and auto_run)

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
    st.write(f"**Data Source:** {data_source}")
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
Data Source: {data_source}
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
