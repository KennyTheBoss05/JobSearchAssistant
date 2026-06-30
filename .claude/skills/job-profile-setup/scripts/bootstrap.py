#!/usr/bin/env python3
"""
bootstrap.py — recreate the job_engine/ data store from the skill's bundled seed.

Why this exists: the tracked defaults (engine_config.yaml, prompts/*.md, etc.) live
ONLY in this skill's assets/job_engine_seed/, so the suite is self-contained and
portable to any repo/machine. job_engine/ itself is gitignored runtime+personal data.
Run this once at the start of job-profile-setup (and it's safe to run anytime).

Safety: NEVER overwrites an existing file — a user's tuned engine_config.yaml or
edited prompts are left untouched. Only missing files are copied; runtime subdirs
are created. Prints a JSON summary of what it created vs. skipped.

Usage:
  python bootstrap.py                 # target = <repo root>/job_engine
  python bootstrap.py --target PATH   # explicit target dir
"""
from __future__ import annotations
import argparse, json, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve()
SEED = HERE.parent.parent / "assets" / "job_engine_seed"   # .../job-profile-setup/assets/job_engine_seed

def find_repo_root() -> Path:
    """Walk up to the directory that contains a `.claude` folder (the repo root)."""
    p = HERE
    for _ in range(8):
        if (p / ".claude").is_dir():
            return p
        p = p.parent
    # fallback: scripts -> job-profile-setup -> skills -> .claude -> root
    return HERE.parents[4]

# Runtime subdirs that hold generated/personal data (created empty if absent).
RUNTIME_DIRS = ["masters", "outputs", "screenshots", "browser_profile"]

def bootstrap(target: Path) -> dict:
    created, skipped = [], []
    target.mkdir(parents=True, exist_ok=True)

    if not SEED.is_dir():
        return {"status": "error", "error": f"seed not found at {SEED}"}

    # Copy every seed file, preserving relative structure, without overwriting.
    for src in sorted(SEED.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(SEED)
        dst = target / rel
        if dst.exists():
            skipped.append(str(rel))
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        created.append(str(rel))

    # Ensure runtime subdirs exist (with a .gitkeep so empty dirs persist if ever tracked).
    for d in RUNTIME_DIRS:
        sub = target / d
        if not sub.exists():
            sub.mkdir(parents=True, exist_ok=True)
            created.append(d + "/")

    return {"status": "ok", "target": str(target),
            "created": created, "skipped": skipped}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default="")
    args = ap.parse_args()
    target = Path(args.target).resolve() if args.target else (find_repo_root() / "job_engine")
    result = bootstrap(target)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("status") == "ok" else 1)

if __name__ == "__main__":
    main()
