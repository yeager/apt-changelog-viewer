"""Private, resilient settings storage for Apt Changelog Viewer."""

import json
import os
import tempfile


SETTINGS_DIR = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "apt-changelog-viewer",
)
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")
DEFAULT_SETTINGS = {
    "welcome_shown": False,
    "highlight_security_updates": True,
}


def load_settings():
    """Load settings, falling back safely when the file is missing or damaged."""
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as settings_file:
            settings = json.load(settings_file)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return dict(DEFAULT_SETTINGS)
    if not isinstance(settings, dict):
        return dict(DEFAULT_SETTINGS)
    settings = {**DEFAULT_SETTINGS, **settings}
    for name, default in DEFAULT_SETTINGS.items():
        if not isinstance(settings[name], bool):
            settings[name] = default
    return settings


def save_settings(settings):
    """Atomically save settings; preserve the old file if writing fails."""
    temporary_path = None
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=SETTINGS_DIR,
            prefix=".settings-",
            suffix=".tmp",
            delete=False,
        ) as settings_file:
            temporary_path = settings_file.name
            json.dump(settings, settings_file, indent=2, ensure_ascii=False)
            settings_file.flush()
            os.fsync(settings_file.fileno())
        os.replace(temporary_path, SETTINGS_FILE)
    except (OSError, TypeError, ValueError):
        if temporary_path:
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
        return False
    return True
