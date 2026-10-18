from pathlib import Path

from flask import Blueprint, abort, current_app, send_from_directory

web = Blueprint("web", __name__)


@web.get("/")
def index():
    directory = Path(current_app.config["FRONTEND_DIST"])
    if not (directory / "index.html").is_file():
        return "Frontend is not built. Run npm install and npm run build in frontend/.", 503
    return send_from_directory(directory, "index.html")


@web.get("/<path:filename>")
def assets(filename):
    if filename == "api" or filename.startswith("api/"):
        abort(404)
    return send_from_directory(current_app.config["FRONTEND_DIST"], filename)
