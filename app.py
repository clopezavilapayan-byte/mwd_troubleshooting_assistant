import csv
import io
import json
import re
from datetime import datetime
from pathlib import Path

import streamlit as st

from engine.alert_engine import analyze_mwd_data
from engine.case_log import load_cases, save_case
from engine.image_analyzer import create_image_review_case, save_uploaded_image
from engine.procedures import PROCEDURES

RIG_MARK_SVG = """
<svg aria-hidden="true" width="48" height="48" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
  <path d="M24 4 8 44h32L24 4Z" fill="none" stroke="#f97316" stroke-width="3" stroke-linejoin="round"/>
  <path d="M24 4v40M14 28h20M18 18h12M13 40l22-28M35 40 13 12" fill="none" stroke="#f8fafc" stroke-width="2.4" stroke-linecap="round"/>
  <path d="M20 44h8" stroke="#f97316" stroke-width="3" stroke-linecap="round"/>
</svg>
"""

st.set_page_config(page_title="MWD Coach AI", page_icon="🛢️", layout="wide")

CASE_DIR = Path("data/cases")
CASE_DIR.mkdir(parents=True, exist_ok=True)
SURVEY_DIR = Path("data/survey_programs")
SURVEY_DIR.mkdir(parents=True, exist_ok=True)

MANUALS = [
    "SDI MWD Field Operations Manual",
    "MWDRun Decode Filter Guide",
    "MWDRun 2.9 Software Manual",
    "Mud Pulse Work Instructions",
    "Gamma Ray Operations Manual",
    "Gamma Ray Theory Manual",
    "WinLog 3.0 Software Manual",
]

KB_0001 = {
    "id": "KB-0001",
    "title": "No Sync During iCruise SHT – Visible Pulses, Pump Issue Suspected",
    "category": "Troubleshooting > Mud Pulse Decode > No Sync",
    "applies_to": ["MWDRun/DataModel 3.414", "MPX", "iCruise RSS", "High Speed 20", "300 ms", "Shallow Hole Test"],
    "symptoms": [
        "Visible pulses on oscilloscope",
        "No full sync / no decode",
        "Sync Hunt starts but does not complete",
        "Decode confidence may be high",
        "Filter may turn ON/OFF repeatedly",
        "Pump 2 around 800 psi SPP improved after switching to Pump 3 around 1150 psi",
    ],
    "recommended_settings": [
        "Up/Down threshold: 300/300 or 400/400 depending on standby pressure",
        "Minimum Extra Phases: 8",
        "Pressure Phase Factor: enabled at -5 µs/psi",
        "Pulse width: 300 ms",
        "Pattern set: High Speed 20",
        "Do not change FFT settings unless directed by engineering",
    ],
    "lesson": "Visible pulses with no sync can mean the pulser is working, but the pressure pattern is unstable/noisy. Verify decoder setup and pressure input, then evaluate mud pump performance before suspecting a downhole tool failure.",
}

PROBLEM_OPTIONS = ["No Pulses Detected", "Visible Pulses / No Sync", "Pulses Present But Not Decoding", "Weak Pulses", "Downlink Failed"]
VIBRATION_OPTIONS = ["Normal", "High", "Unknown"]
SPP_STABLE_OPTIONS = ["Yes", "No", "Unknown"]
PULSE_WIDTH_OPTIONS = ["300 ms", "500 ms", "Other"]

COLUMN_ALIASES = {
    "problem": ["problem", "issue", "event", "failure", "diagnosis"],
    "spp": ["spp", "standpipe_pressure", "standpipepressure", "pressure", "stand_pipe_pressure"],
    "flow": ["flow", "flow_rate", "flowrate", "gpm", "pump_rate", "pumprate"],
    "pulse_amp": ["pulse_amp", "pulse_amplitude", "pulseamplitude", "pulse_psi", "amplitude"],
    "quality": ["quality", "decoder_quality", "decode_quality", "signal_quality"],
    "confidence": ["confidence", "decoder_confidence", "decode_confidence"],
    "correlation": ["correlation", "corr", "decode_correlation"],
    "temp_c": ["temp_c", "temperature_c", "downhole_temp", "downhole_temperature", "temp"],
    "vibration": ["vibration", "vibration_status", "vibe_status"],
    "spp_stable": ["spp_stable", "pressure_stable", "standpipe_stable", "stable_spp"],
    "downlink_enabled": ["downlink_enabled", "downlink", "downlink_on"],
    "downlink_failed": ["downlink_failed", "downlink_fail"],
    "downlink_success": ["downlink_success", "downlink_ok"],
    "pulses_present": ["pulses_present", "pulse_present", "visible_pulses", "visible_pulse", "pulsing", "has_pulse"],
    "decoding": ["decoding", "decode", "decoded", "is_decoding"],
    "full_sync": ["full_sync", "sync", "synced", "sync_achieved", "decode_sync"],
    "sync_status": ["sync_status", "sync_state", "sync_hunt", "decoder_status"],
    "pattern_set": ["pattern_set", "pattern", "message_table", "patternset"],
    "pulse_width": ["pulse_width", "pulsewidth", "width", "pulse_ms"],
}

# -----------------------------
# Rule Engine
# -----------------------------

def add_step(steps, title, details, area="", priority="Normal"):
    steps.append({"area": area, "title": title, "details": details, "priority": priority})


def pump_health_score(data):
    """Simple explainable scoring model for pump-related decode risk."""
    score = 100
    flags = []

    ripple = data.get("spp_max", 0) - data.get("spp_min", 0)
    avg_spp = data.get("spp_avg", 0)
    ripple_pct = (ripple / avg_spp * 100) if avg_spp else 0

    if ripple_pct >= 10:
        score -= 30
        flags.append(f"High SPP ripple: {ripple:.0f} psi ({ripple_pct:.1f}%).")
    elif ripple_pct >= 5:
        score -= 15
        flags.append(f"Moderate SPP ripple: {ripple:.0f} psi ({ripple_pct:.1f}%).")

    if data.get("filter_toggles", 0) >= 3:
        score -= 25
        flags.append("Filter is cycling ON/OFF while pumping.")
    elif data.get("filter_toggles", 0) >= 1:
        score -= 10
        flags.append("Filter toggled while pumping.")

    confidence = data.get("confidence", 0)
    if confidence and confidence < 60:
        score -= 20
        flags.append(f"Low decode confidence: {confidence}%.")
    elif confidence and confidence < 80:
        score -= 10
        flags.append(f"Marginal decode confidence: {confidence}%.")

    correlation = data.get("correlation", 0.0)
    if correlation and correlation < 1.5:
        score -= 20
        flags.append(f"Low correlation: {correlation}.")
    elif correlation and correlation < 2.5:
        score -= 10
        flags.append(f"Marginal correlation: {correlation}.")

    if data.get("sync_resets", 0) >= 3:
        score -= 20
        flags.append("Repeated Sync Hunt resets/stalls.")

    if data.get("spm_variation", 0.0) >= 2.0:
        score -= 15
        flags.append(f"SPM variation is high: ±{data['spm_variation']}.")

    if data.get("visible_pulses") and not data.get("full_sync"):
        score -= 10
        flags.append("Visible pulses but no full sync: suspect signal stability, pump noise, or setup mismatch.")

    score = max(0, min(100, score))
    return score, flags


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

    elif problem in ["Pulses Present But Not Decoding", "Visible Pulses / No Sync"]:
        causes += ["Tool/decoder programming mismatch", "Filter setting issue", "Pump instability/noise", "Bad pump valve/seat", "Transducer/channel issue", "Hydraulic noise", "Message table mismatch"]
        add_step(steps, "Verify waveform pulses", "Confirm pulses are visible and consistent in the waveform/spectrogram window.", "Area A - Inside Unit", "High")
        add_step(steps, "Confirm decoder setup", "Verify pulse width, pattern set, uplink type, and message table match the programmed tool.", "Area A - Decoder", "High")
        add_step(steps, "Set Minimum Extra Phases", "For the current field practice in this workflow, set Minimum Extra Phases to 8.", "Area A - Sync Decoder", "High")
        add_step(steps, "Set Pressure Phase Factor", "For MWDRun/DataModel 3.414 with MPX, enable Pressure Phase Factor and set it to -5 µs/psi unless engineering directs otherwise.", "Area A - Sync Decoder", "High")
        add_step(steps, "Verify Up/Down threshold", "Confirm Up/Down is not at the default 2000 psi. Use 300/300 or 400/400 based on standby pressure and actual SPP.", "Area A - Pump Detection", "High")
        if data["quality"] and data["quality"] < 70:
            add_step(steps, "Quality below target", f"Quality is {data['quality']}%. Check noise, filters, thresholds, and pulse shape.", "Area A - Decoder", "High")
        if data["confidence"] and data["confidence"] < 80:
            add_step(steps, "Confidence below target", f"Confidence is {data['confidence']}%. Verify sync, thresholds, mode match, and pump noise.", "Area A - Decoder", "High")
        add_step(steps, "Confirm pressure input", "Nominal SPP in the software should match the rig gauge. If not, verify pressure channel/transducer/cabling.", "Area B - Transducer", "High")
        add_step(steps, "Evaluate filter cycling", "If the log alternates Filter ON/OFF while pumping, investigate pump instability, wrong thresholds, or pressure fluctuations.", "Area B - Pump Diagnostics", "High")
        add_step(steps, "Switch mud pumps if available", "If visible pulses exist but Sync Hunt stalls, try another pump before suspecting the downhole tool. Compare SPP, ripple, confidence, correlation, and Sync Hunt.", "Area B - Pumps", "Critical")
        add_step(steps, "Do not tune FFT first", "Leave FFT/default filters alone unless directed. First verify up/down, min extra phases, pressure phase factor, transducer, tool programming, and pump health.", "Area A - Decoder", "Normal")

    elif problem == "Weak Pulses":
        causes += ["Low flow", "Partial pulser/orifice plugging", "LCM/debris", "Dampener issue", "Aerated mud", "Transducer sensitivity issue"]
        add_step(steps, "Compare flow to tool range", "Confirm flow rate is inside the pulser/orifice operating range.", "Area B - Pumps", "High")
        add_step(steps, "Try higher and lower flow", "Test controlled flow changes and observe pulse amplitude response.", "Area B - Pumps", "High")
        add_step(steps, "Check dampener setting", "Check dampener condition/precharge against rig procedure.", "Area B - Hydraulics", "Normal")
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
    if text in {"true", "yes", "y", "1", "on", "enabled", "pass", "ok", "synced", "decode"}:
        return True
    if text in {"false", "no", "n", "0", "off", "disabled", "fail", "failed", "no sync", "nosync"}:
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
    if "visible" in text and ("no sync" in text or "sync" in text):
        return "Visible Pulses / No Sync"
    if "no sync" in text or "sync hunt" in text or "sync stall" in text:
        return "Visible Pulses / No Sync"
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
    full_sync = to_bool(pick_value(row, COLUMN_ALIASES["full_sync"]))
    sync_status = str(pick_value(row, COLUMN_ALIASES["sync_status"]) or "").lower()

    if downlink_failed is True or downlink_success is False:
        return "Downlink Failed"
    if pulses_present is False:
        return "No Pulses Detected"
    if pulses_present is True and (decoding is False or full_sync is False or "no sync" in sync_status or "sync hunt" in sync_status or "stall" in sync_status):
        return "Visible Pulses / No Sync"
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
        "correlation": to_float(pick_value(row, COLUMN_ALIASES["correlation"])),
        "temp_c": to_int(pick_value(row, COLUMN_ALIASES["temp_c"])),
        "vibration": normalize_choice(pick_value(row, COLUMN_ALIASES["vibration"]), VIBRATION_OPTIONS, "Unknown"),
        "spp_stable": normalize_choice(pick_value(row, COLUMN_ALIASES["spp_stable"]), SPP_STABLE_OPTIONS, "Unknown"),
        "downlink_enabled": to_bool(pick_value(row, COLUMN_ALIASES["downlink_enabled"])) or False,
        "pattern_set": pick_value(row, COLUMN_ALIASES["pattern_set"]) or "High Speed 20",
        "pulse_width": normalize_choice(pick_value(row, COLUMN_ALIASES["pulse_width"]), PULSE_WIDTH_OPTIONS, "300 ms"),
        "sync_status": pick_value(row, COLUMN_ALIASES["sync_status"]) or "Sync Hunt",
    }
    data["problem"] = data["problem"] or infer_problem(data, row)
    return data


def extract_pdf_text(uploaded_file):
    """Best-effort PDF text extraction. Scanned PDFs still need manual entry or OCR."""
    if uploaded_file is None:
        return ""
    data = uploaded_file.read()
    uploaded_file.seek(0)
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages)
    except Exception as exc:
        return f"PDF_TEXT_EXTRACTION_ERROR: {exc}"


def find_value(text, label, stop_labels=None):
    """Extract label values from survey text such as 'Well Name: ABC Rig: XYZ'."""
    stop_labels = stop_labels or []
    labels = [re.escape(x) for x in stop_labels]
    stop_pattern = "|".join(labels) if labels else r"\n"
    pattern = rf"{re.escape(label)}\s*:?\s*(.*?)(?=\s+(?:{stop_pattern})\s*:|\n|$)"
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return " ".join(match.group(1).split()).strip()


def parse_survey_program_text(text):
    """Parse common survey program fields from a PDF text block."""
    if not text:
        return {}

    fields = {}
    labels = [
        "Well Name",
        "Rig",
        "Revision",
        "Basin",
        "Operator",
        "Pad",
        "Survey Contractor",
        "Country",
        "AFE #",
        "County, State",
        "Coordinate System",
        "Geo Datum",
        "Map Zone",
        "Vertical Datum",
        "North Reference",
        "TVD Reference",
        "Latitude",
        "Longitude",
        "Northings",
        "Eastings",
        "Survey Calculation Method",
        "FAC Sigma Level",
    ]
    for label in labels:
        key = label.lower().replace(" ", "_").replace(",", "").replace("#", "number")
        fields[key] = find_value(text, label, labels)

    geomag_row = re.search(
        r"(\d{2}/\d{2}/\d{4})\s+([\d,]+)\s+([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)",
        text,
    )
    if geomag_row:
        fields.update(
            {
                "geomag_date": geomag_row.group(1),
                "total_field_nt": geomag_row.group(2),
                "declination_deg": geomag_row.group(3),
                "dip_angle_deg": geomag_row.group(4),
                "grid_convergence_deg": geomag_row.group(5),
                "total_correction_deg": geomag_row.group(6),
            }
        )

    intervals = []
    if "Surface to" in text and "SCP" in text:
        intervals.append(
            {
                "hole_section": "Surface to SCP",
                "start_depth_ft": "0.00",
                "end_depth_ft": fields.get("scp_depth_ft", "1,153.00") or "1,153.00",
                "survey_method": "MWD" if "MWD" in text else "",
                "magnetic_reference": "IFR1" if "IFR1" in text else "",
                "corrections": "Batch Process: MSA" if "Batch Process" in text and "MSA" in text else "",
                "error_model": "OWSG Rev. 2 - MWD+IFR1+MS" if "MWD+IFR1+MS" in text else "",
            }
        )

    td_match = re.search(r"SCP\s+to\s+TD\s+([\d,.]+)\s+([\d,.]+)", text, re.IGNORECASE)
    if td_match or "SCP to TD" in text:
        intervals.append(
            {
                "hole_section": "SCP to TD",
                "start_depth_ft": td_match.group(1) if td_match else "1,153.00",
                "end_depth_ft": td_match.group(2) if td_match else "29,005.00",
                "survey_method": "MWD" if "MWD" in text else "",
                "magnetic_reference": "IFR1" if "IFR1" in text else "",
                "corrections": "Real Time: MSA+SAG" if "MSA+SAG" in text else "",
                "error_model": "OWSG Rev. 2 - MWD+IFR1+SAG+MS" if "MWD+IFR1+SAG+MS" in text else "",
            }
        )
    fields["survey_intervals"] = intervals
    return fields


def survey_warnings(fields, current):
    warnings = []
    expected_north = fields.get("north_reference", "").upper()
    if expected_north and current.get("north_reference") and expected_north != current["north_reference"].upper():
        warnings.append(f"North reference mismatch: program says {expected_north}, current setup says {current['north_reference']}.")

    expected_method = fields.get("survey_calculation_method", "").lower()
    if expected_method and current.get("survey_calc_method") and expected_method != current["survey_calc_method"].lower():
        warnings.append(f"Survey calculation method mismatch: program says {fields.get('survey_calculation_method')}, current setup says {current['survey_calc_method']}.")

    numeric_checks = [
        ("declination_deg", "declination", "Declination"),
        ("grid_convergence_deg", "grid_convergence", "Grid convergence"),
        ("total_correction_deg", "total_correction", "Total correction"),
    ]
    for program_key, current_key, label in numeric_checks:
        if fields.get(program_key) and current.get(current_key) not in [None, ""]:
            try:
                program_value = float(str(fields[program_key]).replace(",", ""))
                current_value = float(str(current[current_key]).replace(",", ""))
                if abs(program_value - current_value) > 0.05:
                    warnings.append(f"{label} mismatch: program says {fields[program_key]} deg, current setup says {current[current_key]} deg.")
            except ValueError:
                pass
    return warnings


def build_report(job, data, causes, steps, pump_score=None, pump_flags=None):
    lines = [
        "MWD Coach AI Troubleshooting Report",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Rig/Well: {job.get('rig','')}",
        f"Operator: {job.get('operator','')}",
        f"Data Source: {data.get('data_source', 'Manual entry')}",
        f"Problem: {data.get('problem','')}",
        f"SPP: {data.get('spp',0)} psi",
        f"Flow: {data.get('flow',0)} GPM",
        f"Pulse Amplitude: {data.get('pulse_amp') or 0} psi",
        f"Quality: {data.get('quality') or 0}%",
        f"Confidence: {data.get('confidence') or 0}%",
        f"Correlation: {data.get('correlation') or 0}",
        f"Pattern Set: {data.get('pattern_set', '')}",
        f"Pulse Width: {data.get('pulse_width', '')}",
        f"Sync Status: {data.get('sync_status', '')}",
        f"Temperature: {data.get('temp_c') or 0} C",
        f"Vibration: {data.get('vibration','')}",
        f"SPP Stable: {data.get('spp_stable','')}",
        f"Downlink Enabled: {data.get('downlink_enabled', False)}",
        "",
    ]
    if pump_score is not None:
        lines += [f"Pump Health Score: {pump_score}/100", "Pump Flags:"] + [f"- {x}" for x in (pump_flags or [])] + [""]
    lines += ["Likely Causes:"] + [f"- {c}" for c in causes] + ["", "Recommended Steps:"]
    lines += [f"{i}. [{s['priority']}] {s['title']} ({s['area']}): {s['details']}" for i, s in enumerate(steps, 1)]
    return "\n".join(lines)

# -----------------------------
# UI
# -----------------------------

st.markdown(
    f"""
    <div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;margin:0.1rem 0 0.4rem;">
        <span style="display:inline-flex;align-items:center;">{RIG_MARK_SVG}</span>
        <h1 style="margin:0;line-height:1.15;">MWD Coach AI</h1>
    </div>
    """,
    unsafe_allow_html=True,
)
st.caption("Real-time MWD troubleshooting assistant for mud pulse decode, pump diagnostics, survey checks, verified procedures, and field case capture.")

with st.sidebar:
    st.header("Job Info")
    rig = st.text_input("Rig / Well", "")
    operator = st.text_input("MWD Operator", "")
    st.divider()
    st.header("Knowledge Base")
    for manual in MANUALS:
        st.checkbox(manual, value=True, key=f"manual_{manual}")
    st.divider()
    st.caption("Prototype only. Follow company procedures, rig-site authority, and engineering guidance.")

job = {"rig": rig, "operator": operator}

live_tab, screenshot_tab, tab1, tab2, tab3, procedures_tab, history_tab, tab4, tab5 = st.tabs(
    [
        "Live Monitor",
        "Screenshot Review",
        "Diagnose",
        "Pump Diagnostics AI",
        "Survey Program Analyzer",
        "Verified Procedures",
        "Case History",
        "KB-0001 Case",
        "New Field Case",
    ]
)

with live_tab:
    st.subheader("Live Data Monitor")

    col1, col2, col3 = st.columns(3)
    with col1:
        live_spp = st.number_input("Standpipe Pressure (psi)", min_value=0.0, value=4568.0, step=25.0, key="live_spp")
        live_pump_rate = st.number_input("Pump Rate (GPM)", min_value=0.0, value=352.0, step=5.0, key="live_pump_rate")
        live_flow = st.number_input("Flow (%)", min_value=0.0, value=45.0, step=1.0, key="live_flow")
        live_pulse_pressure = st.number_input("Pulse Pressure (psi)", min_value=0.0, value=16.7, step=0.5, key="live_pulse_pressure")
    with col2:
        live_decode_confidence = st.number_input("Decode Confidence (%)", min_value=0.0, max_value=100.0, value=100.0, step=1.0, key="live_decode_confidence")
        live_correlation = st.number_input("Correlation", min_value=0.0, value=96.2, step=0.1, key="live_correlation")
        live_correlation_margin = st.number_input("Correlation Margin", min_value=0.0, value=29.0, step=0.5, key="live_correlation_margin")
        live_sync_status = st.selectbox("Sync Status", ["HST", "Sync Hunt", "No Sync", "Poor Sync"], key="live_sync_status")
    with col3:
        live_wob = st.number_input("WOB (klb)", min_value=0.0, value=13.7, step=0.5, key="live_wob")
        live_rpm = st.number_input("RPM", min_value=0.0, value=90.0, step=1.0, key="live_rpm")
        live_torque = st.number_input("Torque (klb-ft)", min_value=0.0, value=9.0, step=0.5, key="live_torque")
        live_lateral_vib = st.number_input("Lateral Vibration", min_value=0.0, value=16.7, step=0.5, key="live_lateral_vib")
        live_stick_slip = st.number_input("Stick-Slip Risk", min_value=0.0, value=0.0, step=0.5, key="live_stick_slip")

    live_data = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "rig_well": rig,
        "operator": operator,
        "spp": live_spp,
        "pump_rate": live_pump_rate,
        "flow": live_flow,
        "pulse_pressure": live_pulse_pressure,
        "decode_confidence": live_decode_confidence,
        "correlation": live_correlation,
        "correlation_margin": live_correlation_margin,
        "sync_status": live_sync_status,
        "wob": live_wob,
        "rpm": live_rpm,
        "torque": live_torque,
        "lateral_vib": live_lateral_vib,
        "stick_slip": live_stick_slip,
    }
    live_alerts = analyze_mwd_data(live_data)

    st.subheader("AI Assessment")
    if not live_alerts:
        st.success("No major abnormalities detected. Continue monitoring.")
    else:
        for alert in live_alerts:
            if alert["level"] == "CRITICAL":
                st.error(f'{alert["level"]}: {alert["problem"]}')
            elif alert["level"] == "WARNING":
                st.warning(f'{alert["level"]}: {alert["problem"]}')
            else:
                st.info(f'{alert["level"]}: {alert["problem"]}')

            st.markdown("**Evidence**")
            for item in alert["evidence"]:
                st.write(f"- {item}")

            st.markdown("**Likely Cause**")
            st.write(alert["likely_cause"])

            st.markdown("**Recommended Action**")
            for step in alert["recommended_action"]:
                st.write(f"- {step}")

            st.markdown("**Verified Procedure Source**")
            st.write(alert["procedure_source"])
            st.divider()

    if st.button("Save Current Monitor Case", key="save_live_monitor_case"):
        save_case(live_data, live_alerts)
        st.success("Case saved to Case History.")


with screenshot_tab:
    st.subheader("Screenshot Review")
    st.write("Upload screenshots from MWDRun, Pason, EDR, RSS, or rig displays. Review the image, confirm the values, then run the alert engine.")

    source_type = st.selectbox("Screenshot Type", ["MWDRun", "Pason / EDR", "RSS", "Other"], key="screenshot_source_type")
    uploaded_images = st.file_uploader(
        "Import Screenshot(s)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="screenshot_uploads",
    )
    screenshot_notes = st.text_area(
        "What problem are you trying to solve?",
        placeholder="Example: Visible pulses but no sync, decode confidence dropping, pump issue suspected...",
        key="screenshot_notes",
    )

    saved_image_cases = []
    if uploaded_images:
        st.markdown("### Uploaded Screenshots")
        for uploaded_file in uploaded_images:
            image_path = save_uploaded_image(uploaded_file, source_type)
            image_case = create_image_review_case(image_path, source_type, screenshot_notes)
            saved_image_cases.append(image_case)

            st.image(uploaded_file, caption=f"{source_type}: {uploaded_file.name}", use_column_width=True)
            st.info(f"Saved image for review: {image_path}")

    st.markdown("### Confirm Values From Screenshot")
    st.caption("Use the screenshot to verify these values. The AI will use confirmed values for troubleshooting.")

    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        screenshot_spp = st.number_input("Standpipe Pressure (psi)", min_value=0.0, value=4568.0, step=25.0, key="screenshot_spp")
        screenshot_pump_rate = st.number_input("Pump Rate (GPM)", min_value=0.0, value=352.0, step=5.0, key="screenshot_pump_rate")
        screenshot_flow = st.number_input("Flow (%)", min_value=0.0, value=45.0, step=1.0, key="screenshot_flow")
        screenshot_pulse_pressure = st.number_input("Pulse Pressure (psi)", min_value=0.0, value=16.7, step=0.5, key="screenshot_pulse_pressure")
    with sc2:
        screenshot_decode_confidence = st.number_input("Decode Confidence (%)", min_value=0.0, max_value=100.0, value=100.0, step=1.0, key="screenshot_decode_confidence")
        screenshot_correlation = st.number_input("Correlation", min_value=0.0, value=96.2, step=0.1, key="screenshot_correlation")
        screenshot_correlation_margin = st.number_input("Correlation Margin", min_value=0.0, value=29.0, step=0.5, key="screenshot_correlation_margin")
        screenshot_sync_status = st.selectbox("Sync Status", ["HST", "Sync Hunt", "No Sync", "Poor Sync"], key="screenshot_sync_status")
    with sc3:
        screenshot_wob = st.number_input("WOB (klb)", min_value=0.0, value=13.7, step=0.5, key="screenshot_wob")
        screenshot_rpm = st.number_input("RPM", min_value=0.0, value=90.0, step=1.0, key="screenshot_rpm")
        screenshot_torque = st.number_input("Torque (klb-ft)", min_value=0.0, value=9.0, step=0.5, key="screenshot_torque")
        screenshot_lateral_vib = st.number_input("Lateral Vibration", min_value=0.0, value=16.7, step=0.5, key="screenshot_lateral_vib")
        screenshot_stick_slip = st.number_input("Stick-Slip Risk", min_value=0.0, value=0.0, step=0.5, key="screenshot_stick_slip")

    screenshot_data = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "rig_well": rig,
        "operator": operator,
        "source": "Screenshot Review",
        "source_type": source_type,
        "spp": screenshot_spp,
        "pump_rate": screenshot_pump_rate,
        "flow": screenshot_flow,
        "pulse_pressure": screenshot_pulse_pressure,
        "decode_confidence": screenshot_decode_confidence,
        "correlation": screenshot_correlation,
        "correlation_margin": screenshot_correlation_margin,
        "sync_status": screenshot_sync_status,
        "wob": screenshot_wob,
        "rpm": screenshot_rpm,
        "torque": screenshot_torque,
        "lateral_vib": screenshot_lateral_vib,
        "stick_slip": screenshot_stick_slip,
        "image_cases": saved_image_cases,
        "problem_notes": screenshot_notes,
    }
    screenshot_alerts = analyze_mwd_data(screenshot_data)

    if st.button("Analyze Screenshot Case", key="analyze_screenshot_case"):
        st.subheader("AI Assessment")
        if not screenshot_alerts:
            st.success("No major abnormalities detected from the confirmed values.")
        else:
            for alert in screenshot_alerts:
                if alert["level"] == "CRITICAL":
                    st.error(f'{alert["level"]}: {alert["problem"]}')
                elif alert["level"] == "WARNING":
                    st.warning(f'{alert["level"]}: {alert["problem"]}')
                else:
                    st.info(f'{alert["level"]}: {alert["problem"]}')

                st.markdown("**Evidence**")
                for item in alert["evidence"]:
                    st.write(f"- {item}")

                st.markdown("**Likely Cause**")
                st.write(alert["likely_cause"])

                st.markdown("**Recommended Action**")
                for step in alert["recommended_action"]:
                    st.write(f"- {step}")

                st.markdown("**Verified Procedure Source**")
                st.write(alert["procedure_source"])
                st.divider()

        if saved_image_cases:
            st.markdown("### Image Review Case")
            for item in saved_image_cases:
                st.json(item)

    if st.button("Save Screenshot Case", key="save_screenshot_case"):
        save_case(screenshot_data, screenshot_alerts)
        st.success("Screenshot case saved to Case History.")

with tab1:
    st.subheader("Guided Troubleshooting")
    input_mode = st.radio("Input Mode", ["Manual", "CSV / Live Data"], horizontal=True, key="diagnose_input_mode")
    auto_data = {}
    auto_ready = False
    auto_run = False
    data_source = "Manual entry"

    if input_mode == "CSV / Live Data":
        uploaded_file = st.file_uploader("CSV readings", type=["csv"], key="diagnose_csv_upload")
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
    pulse_width_default = defaults.get("pulse_width", "300 ms")

    col1, col2 = st.columns([1, 1])
    with col1:
        problem = st.selectbox("Select Problem", PROBLEM_OPTIONS, index=PROBLEM_OPTIONS.index(problem_default))
        spp = st.number_input("Standpipe Pressure (psi)", min_value=0, value=clamp_int(defaults.get("spp"), 0), step=50)
        flow = st.number_input("Flow Rate (GPM)", min_value=0, value=clamp_int(defaults.get("flow"), 0), step=10)
        pulse_amp = st.number_input("Pulse Amplitude (psi)", min_value=0.0, value=float(defaults.get("pulse_amp") or 0.0), step=0.5)
        pattern_set = st.text_input("Pattern Set", str(defaults.get("pattern_set") or "High Speed 20"))
        pulse_width = st.selectbox("Pulse Width", PULSE_WIDTH_OPTIONS, index=PULSE_WIDTH_OPTIONS.index(pulse_width_default))
    with col2:
        quality = st.number_input("Decoder Quality (%)", min_value=0, max_value=100, value=clamp_int(defaults.get("quality"), 0, 100))
        confidence = st.number_input("Decoder Confidence (%)", min_value=0, max_value=100, value=clamp_int(defaults.get("confidence"), 0, 100))
        correlation = st.number_input("Correlation", min_value=0.0, value=float(defaults.get("correlation") or 0.0), step=0.1)
        sync_status = st.text_input("Sync Status", str(defaults.get("sync_status") or "Sync Hunt"))
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
            "correlation": correlation,
            "temp_c": temp_c if temp_c > 0 else None,
            "vibration": vibration,
            "spp_stable": spp_stable,
            "downlink_enabled": downlink_enabled,
            "pattern_set": pattern_set,
            "pulse_width": pulse_width,
            "sync_status": sync_status,
            "data_source": data_source,
        }
        causes, steps = diagnose(data)

        st.subheader("AI Diagnostic Summary")
        st.write(f"**Data Source:** {data_source}")
        st.write(f"**Problem:** {problem}")
        st.write(f"**Likely Causes:** {', '.join(causes)}")
        if problem == "Visible Pulses / No Sync":
            st.info("Field logic: visible pulses with no sync means the pulser may be working. Verify decoder settings, pressure input, and pump health before suspecting the downhole tool.")

        st.subheader("Recommended Troubleshooting Steps")
        for i, step in enumerate(steps, 1):
            with st.expander(f"{i}. [{step['priority']}] {step['title']} — {step['area']}", expanded=i <= 5):
                st.write(step["details"])
                st.checkbox("Completed", key=f"step_{i}")

        report = build_report(job, data, causes, steps)
        st.download_button("Download Report", report, file_name="mwd_troubleshooting_report.txt")

with tab2:
    st.subheader("Pump Diagnostics AI")
    st.write("Use this when you have visible pulses, Sync Hunt stalls, filter cycling, or suspected pump valve/seat issues.")
    c1, c2, c3 = st.columns(3)
    with c1:
        pump_number = st.selectbox("Active Pump", ["Pump 1", "Pump 2", "Pump 3", "Unknown"])
        spp_avg = st.number_input("Average SPP (psi)", min_value=0, value=0, step=25)
        spp_min = st.number_input("Minimum SPP (psi)", min_value=0, value=0, step=25)
        spp_max = st.number_input("Maximum SPP (psi)", min_value=0, value=0, step=25)
    with c2:
        spm_actual = st.number_input("Actual SPM", min_value=0.0, value=0.0, step=0.5)
        spm_target = st.number_input("Target SPM", min_value=0.0, value=0.0, step=0.5)
        spm_variation = st.number_input("SPM Variation ±", min_value=0.0, value=0.0, step=0.1)
    with c3:
        p_conf = st.number_input("Decode Confidence (%)", min_value=0, max_value=100, value=0, key="pump_conf")
        p_corr = st.number_input("Correlation", min_value=0.0, value=0.0, step=0.1, key="pump_corr")
        filter_toggles = st.number_input("Filter ON/OFF Toggles", min_value=0, value=0, step=1)
        sync_resets = st.number_input("Sync Hunt Resets/Stalls", min_value=0, value=0, step=1)

    visible_pulses = st.checkbox("Visible pulses on oscilloscope", value=True)
    full_sync = st.checkbox("Full sync/decode achieved", value=False)
    pump_changed = st.checkbox("Pump was changed during troubleshooting")
    new_pump_result = st.text_input("Pump change result", "Example: Pump 2 at 800 psi failed; Pump 3 at 1150 psi improved signal")

    if st.button("Calculate Pump Health Score"):
        pump_data = {
            "pump_number": pump_number,
            "spp_avg": spp_avg,
            "spp_min": spp_min,
            "spp_max": spp_max,
            "spm_actual": spm_actual,
            "spm_target": spm_target,
            "spm_variation": spm_variation,
            "confidence": p_conf,
            "correlation": p_corr,
            "filter_toggles": filter_toggles,
            "sync_resets": sync_resets,
            "visible_pulses": visible_pulses,
            "full_sync": full_sync,
        }
        score, flags = pump_health_score(pump_data)
        st.metric("Pump Health Score", f"{score}/100")
        if score < 50:
            st.error("High pump-related decode risk. Consider switching pumps before changing advanced decoder settings or suspecting the downhole tool.")
        elif score < 75:
            st.warning("Moderate pump-related decode risk. Verify pump stability, pressure ripple, dampener, and transducer signal.")
        else:
            st.success("Pump signal appears acceptable based on entered values. Continue checking tool programming/message table if sync still fails.")
        if flags:
            st.write("**Flags:**")
            for flag in flags:
                st.write(f"- {flag}")
        if pump_changed:
            st.info(f"Pump change note: {new_pump_result}")

with tab3:
    st.subheader("Survey Program Analyzer")
    st.write("Upload a survey program PDF or enter values manually. The app extracts key well, geomagnetic, and survey QC fields and compares them to the current setup.")

    uploaded_survey = st.file_uploader("Upload Survey Program PDF", type=["pdf"], key="survey_program_pdf")
    extracted_text = ""
    parsed = {}
    if uploaded_survey:
        extracted_text = extract_pdf_text(uploaded_survey)
        if extracted_text.startswith("PDF_TEXT_EXTRACTION_ERROR"):
            st.warning("Could not extract text from this PDF. Use manual entry below or add OCR in a future build.")
            st.caption(extracted_text)
        else:
            parsed = parse_survey_program_text(extracted_text)
            st.success("PDF text extracted. Review the parsed fields below.")

    st.markdown("### Parsed / Manual Survey Program Fields")
    c1, c2 = st.columns(2)
    with c1:
        well_name = st.text_input("Well Name", parsed.get("well_name", ""))
        rig_name = st.text_input("Rig", parsed.get("rig", ""))
        operator_name = st.text_input("Operator", parsed.get("operator", ""))
        county_state = st.text_input("County / State", parsed.get("county_state", ""))
        coord_system = st.text_input("Coordinate System", parsed.get("coordinate_system", ""))
        geo_datum = st.text_input("Geo Datum", parsed.get("geo_datum", ""))
        map_zone = st.text_input("Map Zone", parsed.get("map_zone", ""))
        north_ref = st.text_input("North Reference", parsed.get("north_reference", ""))
    with c2:
        geomag_date = st.text_input("Geomagnetic Date", parsed.get("geomag_date", ""))
        total_field = st.text_input("Total Field (nT)", parsed.get("total_field_nt", ""))
        declination = st.text_input("Declination (deg)", parsed.get("declination_deg", ""))
        dip_angle = st.text_input("Dip Angle (deg)", parsed.get("dip_angle_deg", ""))
        grid_conv = st.text_input("Grid Convergence (deg)", parsed.get("grid_convergence_deg", ""))
        total_corr = st.text_input("Total Correction (deg)", parsed.get("total_correction_deg", ""))
        tvd_ref = st.text_input("TVD Reference", parsed.get("tvd_reference", ""))
        calc_method = st.text_input("Survey Calculation Method", parsed.get("survey_calculation_method", ""))

    intervals = parsed.get("survey_intervals", [])
    if intervals:
        st.markdown("### Survey Intervals Detected")
        st.dataframe(intervals, use_container_width=True)
    else:
        st.info("No survey interval table was automatically detected. You can still save the header and geomagnetic values.")

    st.markdown("### Compare Against Current DataModel / MWDRun Setup")
    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        current_north = st.text_input("Current North Reference", "GRID")
        current_calc = st.text_input("Current Survey Calc Method", "Minimum Curvature")
    with cc2:
        current_declination = st.text_input("Current Declination", "")
        current_grid = st.text_input("Current Grid Conv.", "")
    with cc3:
        current_total = st.text_input("Current Total Correction", "")
        current_mag_ref = st.text_input("Current Magnetic Reference", "IFR1")

    survey_record = {
        "well_name": well_name,
        "rig": rig_name,
        "operator": operator_name,
        "county_state": county_state,
        "coordinate_system": coord_system,
        "geo_datum": geo_datum,
        "map_zone": map_zone,
        "north_reference": north_ref,
        "geomag_date": geomag_date,
        "total_field_nt": total_field,
        "declination_deg": declination,
        "dip_angle_deg": dip_angle,
        "grid_convergence_deg": grid_conv,
        "total_correction_deg": total_corr,
        "tvd_reference": tvd_ref,
        "survey_calculation_method": calc_method,
        "survey_intervals": intervals,
    }
    current_setup = {
        "north_reference": current_north,
        "survey_calc_method": current_calc,
        "declination": current_declination,
        "grid_convergence": current_grid,
        "total_correction": current_total,
        "magnetic_reference": current_mag_ref,
    }

    if st.button("Analyze Survey Program"):
        warns = survey_warnings(survey_record, current_setup)
        st.markdown("### Setup Check Results")
        if warns:
            for warning in warns:
                st.warning(warning)
        else:
            st.success("No mismatches detected from the entered values.")

        if "SAG" in json.dumps(intervals).upper():
            st.info("Survey program includes SAG correction in at least one interval. Verify real-time SAG setup after the listed depth threshold.")
        if "IFR" in json.dumps(intervals).upper() or "IFR" in current_mag_ref.upper():
            st.info("IFR magnetic reference detected. Verify the correct IFR version and correction workflow before surveys are accepted.")

    if st.button("Save Survey Program Record"):
        out_name = (well_name or "survey_program").lower().replace(" ", "_").replace("/", "_")
        out = SURVEY_DIR / f"{out_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        payload = {"created_at": datetime.now().isoformat(timespec="seconds"), "survey_program": survey_record, "current_setup": current_setup}
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        st.success(f"Saved survey program record: {out}")
        st.download_button("Download Survey Program JSON", json.dumps(payload, indent=2), file_name=out.name)


with procedures_tab:
    st.subheader("Verified Procedure Library")
    for proc in PROCEDURES:
        with st.expander(f'{proc["id"]} - {proc["title"]}'):
            st.write(f'**Status:** {proc["verification_status"]}')
            st.write(f'**Source:** {proc["source"]}')
            st.write(f'**Revision:** {proc["revision"]}')
            st.write(f'**Last Reviewed:** {proc["last_reviewed"]}')
            st.write(f'**Reviewed By:** {proc["reviewed_by"]}')

            st.markdown("**Procedure Steps**")
            for step in proc["steps"]:
                st.write(f"- {step}")

            st.markdown("**Field Notes**")
            for note in proc["field_notes"]:
                st.write(f"- {note}")


with history_tab:
    st.subheader("Case History")
    monitor_cases = load_cases()
    if not monitor_cases:
        st.info("No live-monitor cases saved yet.")
    else:
        for case in reversed(monitor_cases):
            title = f'{case.get("timestamp", "Unknown time")} - {len(case.get("alerts", []))} alert(s)'
            with st.expander(title):
                st.json(case)


with tab4:
    st.subheader(f"{KB_0001['id']} — {KB_0001['title']}")
    st.write(f"**Category:** {KB_0001['category']}")
    st.write("**Applies To:** " + ", ".join(KB_0001["applies_to"]))
    st.write("**Symptoms:**")
    for x in KB_0001["symptoms"]:
        st.write(f"- {x}")
    st.write("**Recommended Settings:**")
    for x in KB_0001["recommended_settings"]:
        st.write(f"- {x}")
    st.info(KB_0001["lesson"])
    st.download_button("Download KB-0001 JSON", json.dumps(KB_0001, indent=2), file_name="kb_0001_icruise_sht_no_sync.json")

with tab5:
    st.subheader("Capture New Field Case")
    st.write("Save real cases so MWD Coach AI can learn from field history.")
    case_id = st.text_input("Case ID", f"KB-{datetime.now().strftime('%Y%m%d-%H%M')}")
    title = st.text_input("Case Title", "")
    tool_type = st.text_input("Tool Type", "MPX")
    software_version = st.text_input("Software Version", "MWDRun/DataModel 3.414")
    rss_type = st.text_input("RSS Type", "iCruise")
    symptoms = st.text_area("Symptoms", "Visible pulses\nNo sync\nSync Hunt stalls")
    actions = st.text_area("Actions Taken", "Verified decoder settings\nChecked pressure input\nSwitched pumps")
    resolution = st.text_area("Resolution / Root Cause", "")
    screenshots = st.text_input("Screenshot filenames / links", "")

    if st.button("Save Field Case"):
        case = {
            "id": case_id,
            "title": title,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "rig_well": rig,
            "operator": operator,
            "tool_type": tool_type,
            "software_version": software_version,
            "rss_type": rss_type,
            "symptoms": [s.strip() for s in symptoms.splitlines() if s.strip()],
            "actions_taken": [a.strip() for a in actions.splitlines() if a.strip()],
            "resolution_root_cause": resolution,
            "screenshots": screenshots,
        }
        out = CASE_DIR / f"{case_id.lower().replace(' ', '_')}.json"
        out.write_text(json.dumps(case, indent=2), encoding="utf-8")
        st.success(f"Saved case: {out}")
        st.download_button("Download Case JSON", json.dumps(case, indent=2), file_name=out.name)

st.divider()
st.caption("Next build: connect WITS/WITSML/CSV/MWDRun logs, add trend detection, and add PDF RAG search over the uploaded manuals.")
