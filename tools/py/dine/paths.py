import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PY = ROOT / "tools/py"
LIBEXEC = ROOT / "tools/libexec"
OUT = ROOT / "out"
APPS = ROOT / "apps"
VENV = ROOT / ".venv"
PMD = VENV / "bin/pymobiledevice3"


class DineError(Exception):
    """A tool step failed or a precondition is missing; the message says what to run."""


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise DineError(f"${name} not set: run through tools/dine (it sources env.sh)")
    return value


def app_dir(app: str) -> Path:
    d = APPS / app
    if not (d / "xtool.yml").exists():
        known = ", ".join(sorted(p.name for p in APPS.iterdir() if (p / "xtool.yml").exists()))
        raise DineError(f"no app {app!r} in apps/ (known: {known})")
    return d


def app_binary(app: str) -> Path:
    # Linux lldb wants the Mach-O inside the bundle, not the .app.
    return app_dir(app) / f"xtool/{app}.app/{app}"
