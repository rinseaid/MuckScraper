"""Optional CSS themes, independent of light/dark appearance and account data."""
import json
import re
from pathlib import PurePosixPath

from flask import url_for


# Local font stacks keep preview and reading usable offline, without a CDN.
FONT_CHOICES = {
    "system": {"label": "System sans", "family": 'system-ui, -apple-system, "Segoe UI", sans-serif'},
    "arial": {"label": "Arial", "family": 'Arial, Helvetica, sans-serif'},
    "verdana": {"label": "Verdana", "family": 'Verdana, Geneva, sans-serif'},
    "georgia": {"label": "Georgia", "family": 'Georgia, "Times New Roman", serif'},
    "palatino": {"label": "Palatino", "family": '"Palatino Linotype", "Book Antiqua", Palatino, Georgia, serif'},
    "times": {"label": "Times New Roman", "family": '"Times New Roman", Times, serif'},
}


def theme_settings(environ):
    themes = {
        "classic": {"label": "Classic", "stylesheet": ""},
    }
    custom = json.loads(environ.get("READER_THEMES") or "{}")
    if not isinstance(custom, dict):
        raise ValueError("READER_THEMES must be a JSON object")
    for name, theme in custom.items():
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name) or name in (*themes, "default"):
            raise ValueError("READER_THEMES requires unique theme ids (lowercase slugs)")
        if not isinstance(theme, dict) or not isinstance(theme.get("label"), str) or not theme["label"].strip():
            raise ValueError("Each reader theme requires a label")
        path = theme.get("stylesheet", "")
        if not isinstance(path, str) or not path.endswith(".css") or not path.startswith("css/") or any(
            part in path for part in ("..", "\\", ":", "?", "#")
        ) or PurePosixPath(path).is_absolute():
            raise ValueError("Reader theme stylesheets must be local css/*.css paths")
        themes[name] = {"label": theme["label"].strip(), "stylesheet": path}

    desktop = environ.get("READER_THEME_DESKTOP") or "classic"
    mobile = environ.get("READER_THEME_MOBILE") or desktop
    if desktop not in themes or mobile not in themes:
        raise ValueError("Reader theme defaults must name registered themes")
    return {"themes": themes, "desktop": desktop, "mobile": mobile, "fonts": FONT_CHOICES}


def init_app(app, environ):
    enabled = environ.get("READER_APPEARANCE_ENABLED", "false").strip().lower()
    if enabled not in {"true", "false", "1", "0"}:
        raise ValueError("READER_APPEARANCE_ENABLED must be true or false")
    if enabled not in {"true", "1"}:
        return
    settings = theme_settings(environ)
    app.config["READER_THEME_SETTINGS"] = settings

    @app.context_processor
    def inject_reader_themes():
        return {"reader_themes": {
            "desktop": settings["desktop"], "mobile": settings["mobile"], "fonts": settings["fonts"],
            "themes": {name: {"label": theme["label"], "url": url_for("static", filename=theme["stylesheet"]) if theme["stylesheet"] else ""}
                       for name, theme in settings["themes"].items()},
        }}
