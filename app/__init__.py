import os
from pathlib import Path

from flask import Flask

from .extensions import db


def create_app(test_config=None):
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///texter.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=16 * 1024,
        FRONTEND_DIST=Path(__file__).resolve().parent.parent / "frontend/dist/browser",
    )
    if test_config:
        app.config.update(test_config)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app)

    from .blueprints.api import api
    from .blueprints.web import web
    from .blueprints.database import database

    app.register_blueprint(api)
    app.register_blueprint(web)
    app.register_blueprint(database)
    return app
