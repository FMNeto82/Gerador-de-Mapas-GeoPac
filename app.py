from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from pathlib import Path

import gdown
from flask import Flask, flash, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

import map_generator


ROOT = Path(__file__).resolve().parent
URL_PREFIX = "/gerador_de_mapas"
VECTORS_DIR = ROOT / "Vetores"
TRACKS_DIR = VECTORS_DIR / "Caminhamentos Terrestres"
EXTRA_VECTORS_DIR = VECTORS_DIR / "Referencias Extras"
OUTPUT_HTML = ROOT / "Mapa_Campo_LT_PGR_CAN.html"
OUTPUT_KMZ = ROOT / "Mapa_Campo_LT_PGR_CAN.kmz"
CONFIG_FILE = ROOT / "config.json"
ALLOWED_EXTENSIONS = {".kml", ".kmz", ".gpx"}
DEFAULT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1O5p5TUAw_R8thT9GVXGzjGlRMIXDIdEknbXSaHUAjH4/edit?usp=drivesdk"
DEFAULT_MAP_TITLE = "Mapa de Pontos e Caminhamentos LT Ponta Grossa - Canoinhas"
DEFAULT_TRACKS_DRIVE_FOLDER = "https://drive.google.com/drive/folders/1L035wiodAQnAHhvHYEHu0Q4lniZL6nhf"

app = Flask(__name__, static_url_path=f"{URL_PREFIX}/static")
app.secret_key = "troque-esta-chave-em-producao"


def default_config() -> dict:
    return {
        "map_title": DEFAULT_MAP_TITLE,
        "sheet_url": DEFAULT_SHEET_URL,
        "tracks_folder": str(TRACKS_DIR.relative_to(ROOT)),
        "lt_label": "LT 500kV Ponta Grossa - Canoinhas",
        "lt_color": "#d71920",
        "tracks_label": "Caminhamentos terrestres",
        "tracks_color": "#2f80ed",
        "tracks_drive_folder": DEFAULT_TRACKS_DRIVE_FOLDER,
        "points_label": "Pontos de controle",
        "extra_vectors_folder": str(EXTRA_VECTORS_DIR.relative_to(ROOT)),
        "extra_vectors_label": "Áreas e referências",
        "extra_vectors_color": "#7c3aed",
    }


def load_config() -> dict:
    config = default_config()
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            config.update({key: value for key, value in saved.items() if value})
        except json.JSONDecodeError:
            flash("O arquivo de configuracao esta invalido. Usando valores padrao.", "warning")
    return config


def save_config(config: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_app_path(value: str) -> Path:
    path = Path((value or "").strip())
    if not path.is_absolute():
        path = ROOT / path
    return path


def clean_hex_color(value: str, fallback: str) -> str:
    value = (value or "").strip()
    return value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else fallback


def google_sheet_csv_url(sheet_url: str) -> str:
    clean_url = (sheet_url or "").strip()
    match = re.search(r"/spreadsheets/d/([^/]+)", clean_url)
    if not match:
        return clean_url
    gid_match = re.search(r"[?&#]gid=(\d+)", clean_url)
    gid = gid_match.group(1) if gid_match else "0"
    return f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv&gid={gid}"


def drive_folder_id(folder_url: str) -> str:
    value = (folder_url or "").strip()
    match = re.search(r"/folders/([a-zA-Z0-9_-]+)", value)
    if match:
        return match.group(1)
    id_match = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", value)
    if id_match:
        return id_match.group(1)
    return value


def clear_vector_files(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(target_dir.rglob("*"), reverse=True):
        if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS:
            path.unlink()
    for path in sorted((p for p in target_dir.rglob("*") if p.is_dir()), reverse=True):
        try:
            path.rmdir()
        except OSError:
            pass


def sync_tracks_from_drive(folder_url: str, target_dir: Path) -> list[str]:
    folder_id = drive_folder_id(folder_url)
    if not folder_id:
        raise ValueError("Informe o link ou ID da pasta do Google Drive dos caminhamentos.")
    copied: list[str] = []
    with tempfile.TemporaryDirectory(prefix="geopac-drive-") as temp_name:
        temp_dir = Path(temp_name)
        gdown.download_folder(id=folder_id, output=str(temp_dir), quiet=True, use_cookies=False)
        clear_vector_files(target_dir)
        for source in sorted(temp_dir.rglob("*")):
            if not source.is_file() or source.suffix.lower() not in ALLOWED_EXTENSIONS:
                continue
            relative_path = source.relative_to(temp_dir)
            target = target_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(relative_path.as_posix())
    return copied


def ensure_dirs() -> None:
    config = load_config()
    VECTORS_DIR.mkdir(exist_ok=True)
    resolve_app_path(config["tracks_folder"]).mkdir(parents=True, exist_ok=True)
    resolve_app_path(config["extra_vectors_folder"]).mkdir(parents=True, exist_ok=True)


def save_uploaded_file(file_storage, target_dir: Path, forced_name: str | None = None) -> bool:
    if not file_storage or not file_storage.filename:
        return False
    original = secure_filename(file_storage.filename)
    suffix = Path(original).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Arquivo ignorado por extensao invalida: {file_storage.filename}")
    filename = forced_name or original
    target_dir.mkdir(parents=True, exist_ok=True)
    file_storage.save(target_dir / filename)
    return True


def current_status() -> dict:
    config = load_config()
    tracks_path = resolve_app_path(config["tracks_folder"])
    extras_path = resolve_app_path(config["extra_vectors_folder"])
    track_count = len([p for p in tracks_path.rglob("*") if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS])
    extra_count = len([p for p in extras_path.rglob("*") if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS])
    return {
        "has_lt": (VECTORS_DIR / "LT230kV PGR-CAN.kml").exists(),
        "track_count": track_count,
        "extra_count": extra_count,
        "has_map": OUTPUT_HTML.exists(),
        "has_kmz": OUTPUT_KMZ.exists(),
        "sheet_url": config["sheet_url"],
        "sheet_label": "Google Sheets" if "docs.google.com" in config["sheet_url"] else "Planilha configurada",
        "map_title": config["map_title"],
        "tracks_folder": config["tracks_folder"],
        "lt_label": config["lt_label"],
        "lt_color": config["lt_color"],
        "tracks_label": config["tracks_label"],
        "tracks_color": config["tracks_color"],
        "tracks_drive_folder": config["tracks_drive_folder"],
        "points_label": config["points_label"],
        "extra_vectors_folder": config["extra_vectors_folder"],
        "extra_vectors_label": config["extra_vectors_label"],
        "extra_vectors_color": config["extra_vectors_color"],
    }


@app.get("/")
def root_redirect():
    return redirect(url_for("index"))


@app.get(URL_PREFIX)
def prefix_redirect():
    return redirect(url_for("index"))


@app.route(f"{URL_PREFIX}/")
def index():
    ensure_dirs()
    return render_template("index.html", status=current_status())


@app.post(f"{URL_PREFIX}/settings")
def settings():
    config = load_config()
    config["map_title"] = request.form.get("map_title", "").strip() or DEFAULT_MAP_TITLE
    config["sheet_url"] = request.form.get("sheet_url", "").strip() or DEFAULT_SHEET_URL
    config["tracks_folder"] = request.form.get("tracks_folder", "").strip() or str(TRACKS_DIR.relative_to(ROOT))
    config["lt_label"] = request.form.get("lt_label", "").strip() or default_config()["lt_label"]
    config["lt_color"] = clean_hex_color(request.form.get("lt_color", ""), default_config()["lt_color"])
    config["tracks_label"] = request.form.get("tracks_label", "").strip() or default_config()["tracks_label"]
    config["tracks_color"] = clean_hex_color(request.form.get("tracks_color", ""), default_config()["tracks_color"])
    config["tracks_drive_folder"] = request.form.get("tracks_drive_folder", "").strip() or default_config()["tracks_drive_folder"]
    config["points_label"] = request.form.get("points_label", "").strip() or default_config()["points_label"]
    config["extra_vectors_folder"] = request.form.get("extra_vectors_folder", "").strip() or str(EXTRA_VECTORS_DIR.relative_to(ROOT))
    config["extra_vectors_label"] = request.form.get("extra_vectors_label", "").strip() or default_config()["extra_vectors_label"]
    config["extra_vectors_color"] = clean_hex_color(request.form.get("extra_vectors_color", ""), default_config()["extra_vectors_color"])
    save_config(config)
    resolve_app_path(config["tracks_folder"]).mkdir(parents=True, exist_ok=True)
    resolve_app_path(config["extra_vectors_folder"]).mkdir(parents=True, exist_ok=True)
    flash("Configuracoes salvas.", "success")
    return redirect(url_for("index"))


@app.post(f"{URL_PREFIX}/upload")
def upload():
    ensure_dirs()
    config = load_config()
    tracks_path = resolve_app_path(config["tracks_folder"])
    extras_path = resolve_app_path(config["extra_vectors_folder"])
    saved = 0
    try:
        if save_uploaded_file(request.files.get("lt_file"), VECTORS_DIR, "LT230kV PGR-CAN.kml"):
            saved += 1
        for track_file in request.files.getlist("track_files"):
            if save_uploaded_file(track_file, tracks_path):
                saved += 1
        for extra_file in request.files.getlist("extra_files"):
            if save_uploaded_file(extra_file, extras_path):
                saved += 1
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))

    if saved:
        flash(f"{saved} arquivo(s) enviado(s).", "success")
    else:
        flash("Nenhum arquivo foi enviado.", "warning")
    return redirect(url_for("index"))


@app.post(f"{URL_PREFIX}/generate")
def generate():
    ensure_dirs()
    config = load_config()
    try:
        tracks_path = resolve_app_path(config["tracks_folder"])
        copied_tracks = sync_tracks_from_drive(config["tracks_drive_folder"], tracks_path)
        result = map_generator.main(
            map_title=config["map_title"],
            control_points_csv_url=google_sheet_csv_url(config["sheet_url"]),
            tracks_dir=tracks_path,
            lt_label=config["lt_label"],
            lt_color=config["lt_color"],
            tracks_label=config["tracks_label"],
            tracks_color=config["tracks_color"],
            points_label=config["points_label"],
            extra_vectors_dir=resolve_app_path(config["extra_vectors_folder"]),
            extra_vectors_label=config["extra_vectors_label"],
            extra_vectors_color=config["extra_vectors_color"],
        )
    except Exception as exc:
        flash(f"Nao foi possivel gerar o mapa: {exc}", "error")
        return redirect(url_for("index"))

    summary = result["summary"]
    flash(
        f"Mapa gerado com {summary['points']} pontos de controle, "
        f"{len(copied_tracks)} caminhamento(s) sincronizado(s) e "
        f"{summary['tracks_km']:.1f} km percorridos.",
        "success",
    )
    return redirect(url_for("index"))


@app.get(f"{URL_PREFIX}/mapa")
def map_view():
    if not OUTPUT_HTML.exists():
        flash("Gere o mapa antes de visualizar.", "warning")
        return redirect(url_for("index"))
    return send_file(OUTPUT_HTML)


@app.get(f"{URL_PREFIX}/download")
def download():
    if not OUTPUT_HTML.exists():
        flash("Gere o mapa antes de baixar.", "warning")
        return redirect(url_for("index"))
    return send_file(OUTPUT_HTML, as_attachment=True, download_name="Mapa_Campo_LT_PGR_CAN.html")


@app.get(f"{URL_PREFIX}/download-kmz")
def download_kmz():
    config = load_config()
    try:
        map_generator.create_kmz(
            map_title=config["map_title"],
            control_points_csv_url=google_sheet_csv_url(config["sheet_url"]),
            tracks_dir=resolve_app_path(config["tracks_folder"]),
            output_path=OUTPUT_KMZ,
            lt_label=config["lt_label"],
            lt_color=config["lt_color"],
            tracks_label=config["tracks_label"],
            tracks_color=config["tracks_color"],
            points_label=config["points_label"],
            extra_vectors_dir=resolve_app_path(config["extra_vectors_folder"]),
            extra_vectors_label=config["extra_vectors_label"],
            extra_vectors_color=config["extra_vectors_color"],
        )
    except Exception as exc:
        flash(f"Nao foi possivel gerar o KMZ: {exc}", "error")
        return redirect(url_for("index"))
    return send_file(OUTPUT_KMZ, as_attachment=True, download_name="Mapa_Campo_LT_PGR_CAN.kmz")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "80"))
    app.run(host="0.0.0.0", port=port, debug=False)
