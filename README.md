# SDI FieldOps AI

Scientific Drilling International field operations prototype for real-time MWD monitoring, screenshot review, mud pulse troubleshooting, pump diagnostics, survey program checks, verified procedures, and field case capture.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Current features

- Live Monitor
  - Manual real-time-style rig data input
  - Alerts for no sync, weak pulses, decode confidence/correlation drops, lateral vibration, and stick-slip risk
  - Evidence, likely cause, recommended action, and verified procedure source for each alert
  - Save monitor snapshots into Case History
- Screenshot Review
  - Upload MWDRun, Pason, EDR, RSS, or rig-display screenshots
  - Preview uploaded images in the app
  - Confirm drilling and MWD values from the screenshot
  - Analyze confirmed values with the alert engine
  - Save screenshot cases into Case History
- Guided troubleshooting for:
  - No Pulses Detected
  - Visible Pulses / No Sync
  - Pulses Present But Not Decoding
  - Weak Pulses
  - Downlink Failed
- Pump Diagnostics AI
  - Pump Health Score
  - SPP ripple checks
  - Filter ON/OFF cycling checks
  - Sync Hunt stall/reset checks
  - Decode confidence and correlation checks
- CSV / Live Data diagnose mode
  - Reads the latest populated CSV row
  - Infers the problem from common rig-data column names
  - Auto-runs the diagnostic when data is received
- Survey Program Analyzer
  - Uploads text-based survey program PDFs
  - Extracts well, geomagnetic, coordinate, and survey QC fields
  - Compares survey program values against current DataModel / MWDRun setup
  - Saves survey program JSON records
- Verified Procedure Library
  - KB-0001 through KB-0004 procedure tracking
  - Verification status, source, revision, review date, procedure steps, and field notes
- Case History
  - Loads saved live-monitor cases
  - Displays alert snapshots as JSON for review
- KB-0001 field case:
  - iCruise SHT, MPX, MWDRun/DataModel 3.414
  - Pump 2 at ~800 psi visible pulses/no sync
  - Pump 3 at ~1150 psi improved signal
- New Field Case form for building a case-history database
- Downloadable reports and JSON case files

## Knowledge base manuals to index in the next build

- SDI MWD Field Operations Manual
- MWDRun Decode Filter Guide
- MWDRun 2.9 Software Manual
- Mud Pulse Work Instructions
- Gamma Ray Operations Manual
- Gamma Ray Theory Manual
- WinLog 3.0 Software Manual

## Next upgrades

- Add OCR from MWDRun / Pason screenshots
- Add computer vision extraction of visible parameters
- Add PDF knowledge search/RAG
- Add WITS/WITSML live rig data feed
- Add MWDRun log import
- Add waveform/spectrogram analysis
- Add trend plots by pump number and rig
- Add SME approval workflow for procedure revisions
