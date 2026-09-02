"""Config loader — the single source of truth for every varying literal.

Backend Instructions §3:
  - loads every config/*.json, allows env overrides (CASCADE_<FILE>_<KEY>)
  - exposes a typed Settings object; NO other module reads a raw literal
  - pnl_config.json and mappings.json are hot-reloadable
  - validates on load; fails fast with a clear message
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
DEFAULTS_DIR = Path(__file__).resolve().parent / "defaults"

# Files the loader manages. Name -> hot-reloadable?
CONFIG_FILES = {
    "line_config": False,
    "model_config": False,
    "mappings": True,
    "pnl_config": True,
}


class ConfigError(RuntimeError):
    """Raised when config or an artifact referenced by config is invalid/missing."""


def _coerce(raw: str) -> Any:
    """Parse an env override as JSON, falling back to the raw string."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _apply_env_overrides(name: str, data: dict) -> dict:
    """CASCADE_<FILE>_<KEY> overrides a top-level key. Nested keys use __ as separator."""
    prefix = f"CASCADE_{name.upper()}_"
    for env_key, raw in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        path = env_key[len(prefix):].lower().split("__")
        node = data
        for part in path[:-1]:
            node = node.setdefault(part, {})
            if not isinstance(node, dict):
                raise ConfigError(f"env override {env_key}: '{part}' is not an object")
        node[path[-1]] = _coerce(raw)
    return data


@dataclass
class Settings:
    """Typed view over the config directory. Reload-aware."""

    config_dir: Path
    artifacts_dir: Path
    data_dir: Path
    database_url: str
    line: dict = field(default_factory=dict)
    model: dict = field(default_factory=dict)
    mappings: dict = field(default_factory=dict)
    pnl: dict = field(default_factory=dict)
    _mtimes: dict = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)

    # ── derived, read-only helpers (so callers never index raw dicts) ──
    @property
    def n_stations(self) -> int:
        return int(self.line["n_stations"])

    @property
    def zones(self) -> dict:
        return self.line["zones"]

    def zone_of(self, station_id: int) -> str:
        for zname, z in self.zones.items():
            if z["start"] <= station_id <= z["end"]:
                return zname
        raise ConfigError(f"station {station_id} falls outside configured zones")

    @property
    def tick_interval_s(self) -> float:
        return float(self.line["tick"]["interval_s"])

    @property
    def visual_classes(self) -> list[str]:
        return list(self.mappings["VISUAL_CLASSES"])

    @property
    def defect_types(self) -> list[str]:
        return list(self.mappings["DEFECT_TYPES"])

    @property
    def camera_to_station(self) -> dict[str, int]:
        return {k: int(v) for k, v in self.mappings["CAMERA_TO_STATION"].items()}

    @property
    def visual_to_process(self) -> dict[str, str]:
        return dict(self.mappings["VISUAL_TO_PROCESS"])

    @property
    def default_station(self) -> int:
        return int(self.mappings["DEFAULT_STATION"])

    @property
    def min_lift(self) -> float:
        return float(self.model["chains"]["min_lift"])

    def artifact(self, *parts: str) -> Path:
        return self.artifacts_dir.joinpath(*parts)

    # ── P&L access with explicit "missing" semantics (never default silently) ──
    PNL_REQUIRED = (
        "downtime_cost_per_min", "downtime_minutes_avoided_per_flag",
        "scrap_cost_per_unit", "avg_units_that_would_carry_it",
        "defect_caught_value", "inspection_cost_per_check", "false_alarm_cost",
        "vehicles_per_shift", "shifts_per_day",
    )

    def pnl_value(self, key: str) -> float | None:
        """Return a P&L assumption, or None if absent — the caller must flag it."""
        v = self.pnl.get(key)
        if v is None or isinstance(v, (dict, list, str)):
            return None
        return float(v)

    def missing_pnl_fields(self) -> list[str]:
        return [k for k in self.PNL_REQUIRED if self.pnl_value(k) is None]

    # ── hot reload ──
    def _path(self, name: str) -> Path:
        return self.config_dir / f"{name}.json"

    def _read(self, name: str) -> dict:
        p = self._path(name)
        if not p.exists():
            raise ConfigError(f"config file missing: {p}")
        try:
            data = json.loads(p.read_text())
        except json.JSONDecodeError as e:
            raise ConfigError(f"config file {p} is not valid JSON: {e}") from e
        self._mtimes[name] = p.stat().st_mtime
        return _apply_env_overrides(name, data)

    def reload_if_changed(self) -> list[str]:
        """Re-read hot-reloadable files whose mtime moved. Returns changed names."""
        changed = []
        with self._lock:
            for name, hot in CONFIG_FILES.items():
                if not hot:
                    continue
                p = self._path(name)
                if p.exists() and p.stat().st_mtime != self._mtimes.get(name):
                    setattr(self, "pnl" if name == "pnl_config" else "mappings", self._read(name))
                    changed.append(name)
        return changed

    def write(self, name: str, data: dict) -> None:
        """Persist a hot-reloadable config file and refresh the in-memory view."""
        if not CONFIG_FILES.get(name):
            raise ConfigError(f"{name} is not hot-reloadable")
        with self._lock:
            self._path(name).write_text(json.dumps(data, indent=2))
            setattr(self, "pnl" if name == "pnl_config" else "mappings", self._read(name))

    def effective(self) -> dict:
        """The full effective config, for GET /config."""
        return {
            "line_config": self.line,
            "model_config": self.model,
            "mappings": self.mappings,
            "pnl_config": self.pnl,
            "paths": {
                "config_dir": str(self.config_dir),
                "artifacts_dir": str(self.artifacts_dir),
                "database_url": self.database_url,
            },
        }


def _seed_config_dir(config_dir: Path) -> None:
    """Copy defaults into the editable config dir for any file not yet present."""
    config_dir.mkdir(parents=True, exist_ok=True)
    for name in CONFIG_FILES:
        target = config_dir / f"{name}.json"
        if not target.exists():
            src = DEFAULTS_DIR / f"{name}.json"
            if not src.exists():
                raise ConfigError(f"default config missing: {src}")
            target.write_text(src.read_text())


def _validate(s: Settings) -> None:
    """Fail fast with a clear message (Backend Instructions §3)."""
    z = s.zones
    covered = sorted(i for zz in z.values() for i in range(zz["start"], zz["end"] + 1))
    if covered != list(range(s.n_stations)):
        raise ConfigError(
            f"line_config zones must cover stations 0..{s.n_stations - 1} exactly; got {len(covered)}")

    if not s.artifacts_dir.exists():
        raise ConfigError(
            f"artifacts dir not found: {s.artifacts_dir}. Run tools/export_artifacts.py first "
            f"(the backend never trains — see Architecture §7).")

    bcfg = s.model["bottleneck"]
    required = [bcfg["graph"], bcfg["normalization"], *bcfg["bstan_weights"]]
    missing = [f for f in required if not s.artifact(f).exists()]
    if missing:
        raise ConfigError(
            f"missing bottleneck artifacts in {s.artifacts_dir}: {missing}. "
            f"Run tools/export_artifacts.py to produce them.")

    if not s.artifact(s.model["chains"]["table"]).exists():
        raise ConfigError(f"missing chain table: {s.artifact(s.model['chains']['table'])}")

    # YOLO weights are optional-by-config: the defect layer degrades honestly without them,
    # but if the operator marked them required we refuse to start half-blind.
    if s.model["defect"].get("required") and not s.artifact(s.model["defect"]["yolo_weights"]).exists():
        raise ConfigError(
            f"model_config.defect.required is true but {s.artifact(s.model['defect']['yolo_weights'])} "
            f"is absent. Drop in the fine-tuned best.pt or set required=false.")

    for key in ("VISUAL_CLASSES", "DEFECT_TYPES", "VISUAL_TO_PROCESS", "CAMERA_TO_STATION"):
        if key not in s.mappings:
            raise ConfigError(f"mappings.json missing required key: {key}")

    unknown = set(s.visual_to_process) - set(s.visual_classes)
    if unknown:
        raise ConfigError(f"VISUAL_TO_PROCESS references unknown visual classes: {sorted(unknown)}")
    bad_targets = set(s.visual_to_process.values()) - set(s.defect_types)
    if bad_targets:
        raise ConfigError(f"VISUAL_TO_PROCESS maps to unknown process types: {sorted(bad_targets)}")
    for cam, st in s.camera_to_station.items():
        if not 0 <= st < s.n_stations:
            raise ConfigError(f"CAMERA_TO_STATION['{cam}'] = {st} is outside 0..{s.n_stations - 1}")


_settings: Settings | None = None


def load_settings(force: bool = False) -> Settings:
    """Load (once) and return the process-wide Settings."""
    global _settings
    if _settings is not None and not force:
        return _settings

    config_dir = Path(os.environ.get("CASCADE_CONFIG_DIR", REPO_DIR / "config")).resolve()
    _seed_config_dir(config_dir)

    data_dir = Path(os.environ.get("CASCADE_DATA_DIR", REPO_DIR / "data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    s = Settings(
        config_dir=config_dir,
        artifacts_dir=Path("."),          # replaced below once model_config is read
        data_dir=data_dir,
        database_url=os.environ.get("CASCADE_DATABASE_URL", f"sqlite:///{data_dir / 'cascade.db'}"),
    )
    s.line = s._read("line_config")
    s.model = s._read("model_config")
    s.mappings = s._read("mappings")
    s.pnl = s._read("pnl_config")

    art = os.environ.get("CASCADE_ARTIFACTS_DIR") or s.model["artifacts_dir"]
    art_path = Path(art)
    s.artifacts_dir = (art_path if art_path.is_absolute() else (REPO_DIR / art_path)).resolve()

    _validate(s)
    _settings = s
    return s


def get_settings() -> Settings:
    return load_settings()
