#!/usr/bin/env python3
"""Render a Quarto site once using a Pixi exec environment from QMD metadata.

This experimental tool does not change pixi.toml or pixi.lock.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shlex
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parent.parent

# Core dependencies verified in the local NixOS R/Python Quarto smoke test.
# Additional dependencies are declared with ci-packages in QMD YAML front matter.
CORE_SPECS = (
    "r-base=4.5.*",
    "r-knitr",
    "r-rmarkdown",
    "r-downlit",  # Required for code-link: true in several legacy posts.
    "r-xml2",
    "r-reticulate",
    "python=3.12.*",
    "numpy",
    "micromamba",  # Needed for reticulate's Pixi Conda environment discovery.
    "pandoc=3.8.3",  # Needed for Nix Quarto 1.9.37 in local testing.
)

SKIP_DIRS = {
    ".git", ".pixi", ".quarto", "_freeze", "_site", "renv", "pyenv",
    "node_modules", "_extensions", "scripts",
}
NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:[=<>!~ ].*)?$")


def front_matter(path: Path) -> dict:
    """Read the initial YAML block, ignoring the rest of a Quarto document."""
    with path.open(encoding="utf-8-sig") as stream:
        if stream.readline().strip() != "---":
            return {}
        lines: list[str] = []
        for line in stream:
            if line.strip() in {"---", "..."}:
                break
            lines.append(line)
        else:
            raise ValueError(f"Missing closing YAML front matter fence: {path}")
    data = yaml.safe_load("".join(lines))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML front matter must be a mapping: {path}")
    return data


def specs_for(path: Path) -> tuple[list[str], bool]:
    data = front_matter(path)
    packages = data.get("ci-packages", [])
    if not isinstance(packages, list) or any(
        not isinstance(p, str) or not p.strip() for p in packages
    ):
        raise ValueError(f"ci-packages must be a list of nonempty strings: {path}")
    execution = data.get("execute", {}) or {}
    if not isinstance(execution, dict):
        raise ValueError(f"execute must be a mapping: {path}")
    return [p.strip() for p in packages], execution.get("freeze") is True


def spec_name(spec: str) -> str:
    match = NAME_RE.fullmatch(spec)
    if not match:
        raise ValueError(f"Invalid Pixi package specification: {spec!r}")
    return match.group(1).lower()


def find_documents(target: str) -> tuple[list[Path], bool]:
    path = (ROOT / target).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Target must be inside the repository")
    if not path.exists():
        raise ValueError(f"Target not found: {path}")
    if path.is_file():
        if path.suffix != ".qmd":
            raise ValueError("--target must be a QMD file or the repository root")
        return [path], False
    if path != ROOT:
        raise ValueError("Only a single QMD or the whole repository is supported")
    paths = sorted(
        p for p in ROOT.rglob("*.qmd")
        if not any(
            part in SKIP_DIRS or part.startswith((".", "_"))
            for part in p.relative_to(ROOT).parts[:-1]
        )
    )
    return paths, True


def aggregate_specs(paths: list[Path], whole_site: bool) -> tuple[list[str], list[str]]:
    by_name = {spec_name(s): (s, "core") for s in CORE_SPECS}
    frozen: list[str] = []
    for path in paths:
        packages, freeze = specs_for(path)
        relative = str(path.relative_to(ROOT))
        # Explicitly frozen docs require precomputed outputs for global renders.
        # A single-document Quarto render always executes, even with freeze true.
        if whole_site and freeze:
            frozen.append(relative)
            continue
        for spec in packages:
            name = spec_name(spec)
            earlier = by_name.get(name)
            if earlier is None:
                by_name[name] = (spec, relative)
            elif earlier[0] == spec:
                continue
            elif earlier[0] == name:
                # Explicit constraint overrides earlier unconstrained requirement.
                by_name[name] = (spec, relative)
            elif spec == name:
                # Generic requirement cannot weaken an existing constraint.
                continue
            else:
                raise ValueError(
                    f"Conflicting specs for {name}: {earlier[0]!r} ({earlier[1]}) "
                    f"vs {spec!r} ({relative}). A one-pass build needs a "
                    "compatible shared environment."
                )
    return [value[0] for value in by_name.values()], frozen


# This setup matches the successfully tested Pixi exec + R + Python command.
SHELL_SETUP = r'''
set -euo pipefail
export R_PROFILE_USER=/dev/null
export RETICULATE_USE_MANAGED_VENV=no
export QUARTO_R="$(command -v Rscript)"
export QUARTO_PYTHON="$(command -v python)"
export RETICULATE_PYTHON="$QUARTO_PYTHON"
export RETICULATE_CONDA="$(command -v micromamba)"
export QUARTO_PANDOC="$(command -v pandoc)"
printf 'Quarto: %s\n' "$(quarto --version)"
printf 'Pandoc: %s\n' "$(pandoc --version | head -n 1)"
printf 'R: %s\nPython: %s\n' "$QUARTO_R" "$QUARTO_PYTHON"
exec quarto render "$1" --to html
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target", default=".", metavar="PATH",
        help="Project root (default) or a single .qmd document for smoke testing",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show the collected specs and command; do not install or render",
    )
    args = parser.parse_args()

    try:
        paths, whole_site = find_documents(args.target)
        specs, frozen = aggregate_specs(paths, whole_site)
    except (ValueError, OSError, yaml.YAMLError) as error:
        parser.error(str(error))

    print(f"QMD documents inspected: {len(paths)}", flush=True)
    if frozen:
        print(f"Explicitly frozen docs (additional packages skipped): {len(frozen)}",
              flush=True)
    print(f"Pixi package specifications ({len(specs)}):", flush=True)
    for spec in specs:
        print(f"  {spec}", flush=True)

    command = ["pixi", "exec", "--channel", "conda-forge"]
    for spec in specs:
        command.extend(["--spec", spec])
    command.extend(["--", "bash", "-c", SHELL_SETUP, "quarto-pixi", args.target])

    if args.dry_run:
        print("\nSingle-render command:", flush=True)
        print(shlex.join(command), flush=True)
        return 0
    print("\nLaunching one Pixi environment and one Quarto render...", flush=True)
    return subprocess.run(command, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
