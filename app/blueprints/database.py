import click
from flask import Blueprint

from ..extensions import db
from .. import models  # Register model metadata before creating tables.

database = Blueprint("database", __name__, cli_group="db")


@database.cli.command("init")
def init_db():
    """Create missing tables without deleting existing data."""
    db.create_all()
    click.echo("Database initialized.")
