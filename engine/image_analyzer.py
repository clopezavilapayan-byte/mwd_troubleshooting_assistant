"""Image intake helpers for MWD Coach AI."""

from datetime import datetime
from pathlib import Path

UPLOAD_DIR = Path("data/uploaded_screenshots")


def save_uploaded_image(uploaded_file, source_type):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_source = source_type.replace(" ", "_").replace("/", "_")
    safe_name = Path(uploaded_file.name).name.replace(" ", "_")
    path = UPLOAD_DIR / f"{timestamp}_{safe_source}_{safe_name}"
    path.write_bytes(uploaded_file.getbuffer())
    return str(path)


def create_image_review_case(image_path, source_type, notes):
    return {
        "source_type": source_type,
        "image_path": image_path,
        "notes": notes,
        "status": "Pending value verification",
        "next_step": "Review screenshot and confirm extracted drilling/MWD values before alert analysis.",
    }
