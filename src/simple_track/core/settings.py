"""Persisted user preferences."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional

from platformdirs import user_config_dir


@dataclass
class Settings:
    library: str = "peco-oo-setrack"  # the library shown in the parts bin
    last_folder: str = ""  # where layouts were last opened or saved
    show_connectors: bool = True
    unit: str = "mm"  # for baseboard sizes: mm, cm, m, in or ft


def default_path() -> Path:
    return Path(user_config_dir("Simple-Track")) / "settings.json"


class SettingsStore:
    def __init__(self, path: Optional[Path] = None):
        self.path = path or default_path()
        self.settings = self._load()

    def _load(self) -> Settings:
        try:
            raw = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return Settings()
        settings = Settings()
        for f in fields(Settings):
            if f.name in raw and type(raw[f.name]) is type(getattr(settings, f.name)):
                setattr(settings, f.name, raw[f.name])
        return settings

    def update(self, **changes) -> None:
        for name, value in changes.items():
            setattr(self.settings, name, value)
        self.save()

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(asdict(self.settings), indent=2))
        except OSError:
            pass
