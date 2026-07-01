import json
from pathlib import Path

CASE_FILE = Path("data/case_history.json")


def load_cases():
    if not CASE_FILE.exists():
        return []
    return json.loads(CASE_FILE.read_text(encoding="utf-8"))


def save_case(data, alerts):
    CASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    cases = load_cases()
    cases.append(
        {
            "timestamp": data.get("timestamp"),
            "data": data,
            "alerts": alerts,
        }
    )
    CASE_FILE.write_text(json.dumps(cases, indent=2), encoding="utf-8")
