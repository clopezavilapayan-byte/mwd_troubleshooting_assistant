# MWD Troubleshooting Assistant MVP

A starter prototype for an MWD diagnostic assistant.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Current features
- Problem selector
- Manual input for rig/MWD readings
- Rule-based troubleshooting steps
- No-pulse workflow
- Pulse-present/not-decoding workflow
- Weak pulse workflow
- Downlink-failed workflow
- Downloadable troubleshooting report

## Next upgrades
- Add PDF knowledge search/RAG
- Add WITS/WITSML or CSV/live data input
- Add waveform analysis
- Add job-history database and success-rate tracking
