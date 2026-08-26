from __future__ import annotations

import json
from pathlib import Path


DEFAULTS = {
    "follow_cursor_position": False,
    "walk_speed": 5,
    "do_not_disturb": False,
    "screen_intro_shown": False,
}
CONFIG_PATH = Path(__file__).resolve().parent.parent / "settings.json"


def load_config() -> dict:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {**DEFAULTS, **{k: data[k] for k in DEFAULTS if k in data}}


def save_config(config: dict) -> None:
    clean = {k: config.get(k, value) for k, value in DEFAULTS.items()}
    CONFIG_PATH.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
