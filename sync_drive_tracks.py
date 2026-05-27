from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import gdown

import map_generator


ROOT = Path(__file__).resolve().parent
TRACKS_DIR = ROOT / "Vetores" / "Caminhamentos Terrestres"
DRIVE_FOLDER_ID = os.environ.get("LOCUS_DRIVE_FOLDER_ID", "1L035wiodAQnAHhvHYEHu0Q4lniZL6nhf")
TRACK_EXTENSIONS = {".kml", ".kmz", ".gpx"}


def remove_previous_tracks() -> None:
    TRACKS_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(TRACKS_DIR.rglob("*"), reverse=True):
        if path.is_file() and path.suffix.lower() in TRACK_EXTENSIONS:
            path.unlink()
    for path in sorted((p for p in TRACKS_DIR.rglob("*") if p.is_dir()), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass


def copy_track_files(source_dir: Path) -> list[str]:
    copied: list[str] = []
    for source in sorted(source_dir.rglob("*")):
        if not source.is_file() or source.suffix.lower() not in TRACK_EXTENSIONS:
            continue
        relative_path = source.relative_to(source_dir)
        target = TRACKS_DIR / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(relative_path.as_posix())
    return copied


def sync_drive_folder() -> list[str]:
    with tempfile.TemporaryDirectory(prefix="locus-drive-") as temp_name:
        temp_dir = Path(temp_name)
        gdown.download_folder(id=DRIVE_FOLDER_ID, output=str(temp_dir), quiet=True, use_cookies=False)
        remove_previous_tracks()
        return copy_track_files(temp_dir)


def main() -> dict:
    copied = sync_drive_folder()
    result = map_generator.main()
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "drive_folder_id": DRIVE_FOLDER_ID,
        "copied_tracks": len(copied),
        "copied_files": copied,
        "map": result,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    main()
