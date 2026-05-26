"""S1 sample-test: run pandoc HTML->markdown first-pass on 10 random TRA folders.

Run from `<project root>` via `pixi run python <this>`. Input paths resolve
relative to `<project root>/TRA-contracts/`; the output directory resolves
relative to this script's own location so the script is relocatable.
"""

from __future__ import annotations

import random
import subprocess
from pathlib import Path

ROOT = Path("TRA-contracts")
OUT_DIR = Path(__file__).resolve().parent
SEED = 20260518
SAMPLE_SIZE = 10


def main() -> None:
    # Enumerate every TRA-<date>/ directory that contains at least one .htm/.html file
    candidates: list[Path] = []
    for firm_dir in sorted(ROOT.iterdir()):
        if not firm_dir.is_dir():
            continue
        for sub in sorted(firm_dir.iterdir()):
            if not sub.is_dir() or not sub.name.startswith("TRA-"):
                continue
            html_files = sorted(
                p for p in sub.iterdir() if p.suffix.lower() in {".htm", ".html"}
            )
            if html_files:
                candidates.append(sub)

    rng = random.Random(SEED)
    sampled = sorted(rng.sample(candidates, SAMPLE_SIZE))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Record seed and sample list
    seed_lines = [
        "# Sample seed and resolved sample",
        "",
        f"- Seed: `{SEED}` (derived from 2026-05-18)",
        f"- Population: {len(candidates)} `TRA-contracts/<firm>/TRA-<date>/` directories carrying at least one `.htm`/`.html` file",
        f"- Sample size: {SAMPLE_SIZE}",
        "",
        "## Sampled directories (relative to project root)",
        "",
    ]
    for p in sampled:
        seed_lines.append(f"- `{p}`")
    (OUT_DIR / "sample_seed.md").write_text("\n".join(seed_lines) + "\n")

    # Convert every HTML in each sampled folder
    written: list[Path] = []
    failed: list[tuple[Path, str]] = []
    for sub in sampled:
        firm_slug = sub.parent.name
        contract_dirname = sub.name
        for html in sorted(sub.iterdir()):
            if html.suffix.lower() not in {".htm", ".html"}:
                continue
            out_name = f"{firm_slug}__{contract_dirname}__{html.name}.pandoc.md"
            out_path = OUT_DIR / out_name
            cmd = [
                "pandoc",
                "--from=html",
                "--to=markdown_strict",
                "--wrap=preserve",
                str(html),
                "-o",
                str(out_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                failed.append((html, result.stderr.strip()))
            else:
                written.append(out_path)

    print(f"Wrote {len(written)} pandoc.md files to {OUT_DIR}")
    if failed:
        print(f"FAILED: {len(failed)}")
        for h, err in failed:
            print(f"  {h}: {err}")
    print(f"Sampled {len(sampled)} folders from {len(candidates)} candidates.")


if __name__ == "__main__":
    main()
