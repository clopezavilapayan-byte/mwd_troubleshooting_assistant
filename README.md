# MWD Coach AI / MWD Troubleshooting Assistant

Streamlit MVP for MWD mud pulse troubleshooting, pump diagnostics, and field case capture.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Current features

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

- Add PDF knowledge search/RAG
- Add WITS/WITSML live rig data feed
- Add MWDRun log import
- Add waveform/spectrogram analysis
- Add trend plots by pump number and rig
