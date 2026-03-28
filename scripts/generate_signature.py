#!/usr/bin/env python3
"""SIGNATURE.sha256 생성 스크립트."""
import hashlib
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
EXTENSIONS = {".py", ".toml", ".md", ".txt"}
OUT = ROOT / "SIGNATURE.sha256"

entries = []
for f in sorted(ROOT.rglob("*")):
    if f.is_file() and f.suffix in EXTENSIONS and ".git" not in f.parts:
        if f.name == "SIGNATURE.sha256":
            continue
        digest = hashlib.sha256(f.read_bytes()).hexdigest()
        entries.append(f"{digest}  {f.relative_to(ROOT)}")

OUT.write_text("\n".join(entries) + "\n")
print(f"Wrote {len(entries)} entries to {OUT}")
