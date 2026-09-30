import json
import os
import re
from pathlib import Path

_PATHS_FILE = Path(__file__).resolve().parent.parent / "configs" / "paths.json"
_TOKEN_RE = re.compile(r"\$\{(\w+)\}")

_paths_cache = None


def _load_paths():
    """
    Single source of truth for machine-specific locations.

    project_root resolution, in priority order:
      1. NIFTY_PROJECT_ROOT environment variable (set this from a launch
         script like run.sh/run.bat - the one place to change per machine).
      2. "project_root" in configs/paths.json, if explicitly set there.
      3. Auto-detected from where this file lives on disk - correct by
         definition on any machine/OS, since the code and the project
         always move together.

    Every config that references ${PROJECT_ROOT}, ${INPUT_DIR} or
    ${RESULTS_DIR} picks up whatever this resolves to, automatically.
    """
    global _paths_cache

    if _paths_cache is not None:
        return _paths_cache

    if _PATHS_FILE.exists():
        with _PATHS_FILE.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    else:
        raw = {}

    env_root = os.environ.get("NIFTY_PROJECT_ROOT")
    root = env_root or raw.get("project_root") or str(_PATHS_FILE.parent.parent)

    # Defaults derived fresh from project_root every time.
    defaults = {
        "input_dir": f"{root}/input data",
        "output_dir": f"{root}/output_data",
        "results_dir": f"{root}/output_data",
    }

    paths = {"project_root": root}

    if env_root:
        paths.update(defaults)
    else:
        for key, default_value in defaults.items():
            paths[key] = raw.get(key, default_value)

    paths.update(raw.get("extra", {}))

    _paths_cache = paths
    return paths


def _substitute(value):
    paths = _load_paths()

    if isinstance(value, str):
        def repl(match):
            key = match.group(1).lower()
            return str(paths.get(key, match.group(0)))

        return _TOKEN_RE.sub(repl, value)

    if isinstance(value, dict):
        return {k: _substitute(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_substitute(v) for v in value]

    return value


def load_json(path):
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)

    return _substitute(data)
