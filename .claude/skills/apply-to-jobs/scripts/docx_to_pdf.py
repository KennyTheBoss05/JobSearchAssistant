#!/usr/bin/env python3
"""Convert a .docx to PDF. Microsoft Word (Windows) if available, else LibreOffice.

    python docx_to_pdf.py <in.docx> [out.pdf]

Prints one JSON line: {"status":"ok","pdf":...,"engine":"word|libreoffice"}
or {"status":"error","error":...} with exit code 1. Stdlib only.
"""
from __future__ import annotations
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

# Paths go in via env vars so quotes/spaces in file names can't break the script.
WORD_PS = r"""
$ErrorActionPreference = 'Stop'
$w = New-Object -ComObject Word.Application
$w.Visible = $false; $w.DisplayAlerts = 0
try {
  $d = $w.Documents.Open($env:D2P_IN, $false, $true)
  $d.ExportAsFixedFormat($env:D2P_OUT, 17)
  $d.Close([ref]0)
} finally { $w.Quit() }
"""

SOFFICE_CANDIDATES = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
]


def via_word(src: Path, out: Path) -> str | None:
    """Returns an error string, or None on success."""
    env = {**os.environ, "D2P_IN": str(src), "D2P_OUT": str(out)}
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", WORD_PS],
                       env=env, capture_output=True, text=True, timeout=180)
    if r.returncode == 0 and out.exists():
        return None
    return (r.stderr or r.stdout).strip()[:300] or "Word conversion failed"


def find_soffice() -> str | None:
    return (shutil.which("soffice") or shutil.which("libreoffice")
            or next((p for p in SOFFICE_CANDIDATES if Path(p).exists()), None))


def via_libreoffice(soffice: str, src: Path, out: Path) -> str | None:
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(src)],
                           capture_output=True, text=True, timeout=180)
        produced = Path(tmp) / (src.stem + ".pdf")
        if not produced.exists():
            return (r.stderr or r.stdout).strip()[:300] or "LibreOffice conversion failed"
        shutil.move(str(produced), out)
    return None


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 2
    src = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve() if len(sys.argv) == 3 else src.with_suffix(".pdf")

    def done(**kw) -> int:
        print(json.dumps(kw))
        return 0 if kw["status"] == "ok" else 1

    if not src.is_file():
        return done(status="error", error=f"input not found: {src}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)  # so a stale PDF can't pass as success

    errors = []
    if os.name == "nt":
        err = via_word(src, out)
        if err is None:
            return done(status="ok", pdf=str(out), engine="word")
        errors.append(f"word: {err}")
    soffice = find_soffice()
    if soffice:
        err = via_libreoffice(soffice, src, out)
        if err is None:
            return done(status="ok", pdf=str(out), engine="libreoffice")
        errors.append(f"libreoffice: {err}")
    else:
        errors.append("libreoffice: not installed")
    return done(status="error", error="no working converter. Install Microsoft Word (Windows) "
                "or LibreOffice. Details: " + " | ".join(errors))


if __name__ == "__main__":
    sys.exit(main())
