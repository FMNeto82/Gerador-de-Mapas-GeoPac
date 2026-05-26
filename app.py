from __future__ import annotations

from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

import map_generator


ROOT = Path(__file__).resolve().parent
VECTORS_DIR = ROOT / "Vetores"
TRACKS_DIR = VECTORS_DIR / "Caminhamentos Terrestres"
OUTPUT_HTML = ROOT / "Mapa_Campo_LT_PGR_CAN.html"
ALLOWED_EXTENSIONS = {".kml", ".kmz"}

app = Flask(__name__)
app.secret_key = "troque-esta-chave-em-producao"


def ensure_dirs() -> None:
    VECTORS_DIR.mkdir(exist_ok=True)
    TRACKS_DIR.mkdir(exist_ok=True)


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
    track_count = len([p for p in TRACKS_DIR.glob("*") if p.suffix.lower() in ALLOWED_EXTENSIONS])
    return {
        "has_lt": (VECTORS_DIR / "LT230kV PGR-CAN.kml").exists(),
        "track_count": track_count,
        "has_map": OUTPUT_HTML.exists(),
    }


@app.route("/")
def index():
    ensure_dirs()
    return render_template("index.html", status=current_status())


@app.post("/upload")
def upload():
    ensure_dirs()
    saved = 0
    try:
        if save_uploaded_file(request.files.get("lt_file"), VECTORS_DIR, "LT230kV PGR-CAN.kml"):
            saved += 1
        for track_file in request.files.getlist("track_files"):
            if save_uploaded_file(track_file, TRACKS_DIR):
                saved += 1
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("index"))

    if saved:
        flash(f"{saved} arquivo(s) enviado(s).", "success")
    else:
        flash("Nenhum arquivo foi enviado.", "warning")
    return redirect(url_for("index"))


@app.post("/generate")
def generate():
    ensure_dirs()
    try:
        result = map_generator.main()
    except Exception as exc:
        flash(f"Nao foi possivel gerar o mapa: {exc}", "error")
        return redirect(url_for("index"))

    summary = result["summary"]
    flash(
        f"Mapa gerado com {summary['points']} pontos de controle e "
        f"{summary['tracks_km']:.1f} km percorridos.",
        "success",
    )
    return redirect(url_for("index"))


@app.get("/mapa")
def map_view():
    if not OUTPUT_HTML.exists():
        flash("Gere o mapa antes de visualizar.", "warning")
        return redirect(url_for("index"))
    return send_file(OUTPUT_HTML)


@app.get("/download")
def download():
    if not OUTPUT_HTML.exists():
        flash("Gere o mapa antes de baixar.", "warning")
        return redirect(url_for("index"))
    return send_file(OUTPUT_HTML, as_attachment=True, download_name="Mapa_Campo_LT_PGR_CAN.html")


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
