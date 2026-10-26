from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"
STATIC = ROOT / "backend" / "app" / "static"


def run(command: list[str], *, cwd: Path) -> None:
    print("+", " ".join(command), flush=True)

    if os.name == "nt" and command[0].lower() == "npm":
        # Windows needs a shell to resolve npm.cmd correctly.
        subprocess.run(
            subprocess.list2cmdline(command),
            cwd=cwd,
            check=True,
            shell=True,
        )
    else:
        # Linux and macOS can execute npm directly.
        subprocess.run(command, cwd=cwd, check=True)


def main() -> None:
    if not (FRONTEND / "package-lock.json").exists():
        raise FileNotFoundError(
            "frontend/package-lock.json is required for a reproducible build"
        )

    run(["npm", "ci", "--no-audit", "--no-fund"], cwd=FRONTEND)
    run(["npm", "run", "build"], cwd=FRONTEND)

    if not (DIST / "index.html").exists():
        raise FileNotFoundError(
            f"Vite build did not create {DIST / 'index.html'}"
        )

    if STATIC.exists():
        shutil.rmtree(STATIC)

    STATIC.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(DIST, STATIC)

    print(f"Copied frontend build to {STATIC}", flush=True)


if __name__ == "__main__":
    main()
