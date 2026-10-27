"""Copie la documentation fournie avec EVA dans le workspace (sans jamais écraser)."""
import os
import shutil
from pathlib import Path


def seed_docs(workspace: Path) -> list[str]:
    src = Path(os.getenv("EVA_SEED_DOCS") or Path(__file__).resolve().parent.parent / "seed_docs")
    if not src.is_dir():
        return []
    copied = []
    for f in sorted(src.rglob("*.md")):
        dest = workspace / "eva" / f.relative_to(src)
        if dest.exists():
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, dest)
        copied.append(str(dest.relative_to(workspace)))
    return copied
