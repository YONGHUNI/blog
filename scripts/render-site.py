#!/usr/bin/env python3
"""Render a Quarto site once using a Pixi exec environment from QMD metadata.

This experimental tool does not change pixi.toml or pixi.lock.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "scripts" / "freeze-manifest.json"

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
# A deliberately small, validated subset of Conda MatchSpec: package name,
# optional comparison operator + version, and optional comma-separated bounds.
# Channel-qualified, URL and PyPI specs are deliberately unsupported.
NAME_RE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9_.-]*)"
    r"(?:\s*(?:===|==|=|>=|<=|>|<|!=|~=)\s*[A-Za-z0-9.*+_-]+"
    r"(?:\s*,\s*(?:===|==|=|>=|<=|>|<|!=|~=)\s*[A-Za-z0-9.*+_-]+)*)?$"
)


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


def render_inputs() -> list[Path]:
    """Resolve the QMD targets declared in Quarto's project.render.

    This keeps dependency collection scoped to documents that the site builds.
    The site's render patterns use ordinary file globs and explicit paths.
    """
    config = yaml.safe_load((ROOT / "_quarto.yml").read_text(encoding="utf-8"))
    patterns = (config or {}).get("project", {}).get("render")
    if not isinstance(patterns, list) or not patterns:
        raise ValueError("project.render must be a nonempty list in _quarto.yml")
    included: set[Path] = set()
    for pattern in patterns:
        if not isinstance(pattern, str) or not pattern:
            raise ValueError("project.render entries must be nonempty strings")
        exclude = pattern.startswith("!")
        glob = pattern[1:] if exclude else pattern
        if Path(glob).is_absolute() or ".." in Path(glob).parts:
            raise ValueError(f"Invalid project.render pattern: {pattern}")
        matches = {
            p for p in ROOT.glob(glob)
            if p.is_file() and p.suffix == ".qmd"
            and not any(part in SKIP_DIRS or part.startswith((".", "_"))
                        for part in p.relative_to(ROOT).parts[:-1])
        }
        if exclude:
            included.difference_update(matches)
        else:
            included.update(matches)
    return sorted(included)


def validate_posts(paths: list[Path]) -> None:
    """Fail early when a post would silently disappear from section listings."""
    rendered = set(paths)
    for post in sorted((ROOT / "posts").glob("*/index.qmd")):
        if post not in rendered:
            raise ValueError(f"Post excluded from project.render: {post.relative_to(ROOT)}")
        area = front_matter(post).get("area")
        if area not in ("research", "geek", "life"):
            raise ValueError(
                f"{post.relative_to(ROOT)}: area must be research, geek, or life "
                f"(got {area!r})"
            )


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
    paths = render_inputs()
    validate_posts(paths)
    return paths, True


def frozen_result_path(path: Path) -> Path:
    """The committed execution result expected from a separate Quarto render."""
    return ROOT / "_freeze" / path.relative_to(ROOT).with_suffix("") / "execute-results" / "html.json"


def freeze_fingerprint(path: Path) -> str:
    """Conservative source fingerprint: changed QMD always requires execution."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest() -> dict[str, str]:
    if not MANIFEST.exists():
        return {}
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in data.items()
    ):
        raise ValueError("Invalid freeze-manifest.json")
    return data


def write_manifest(paths: list[Path]) -> None:
    """Register successful QMD executions that produced frozen HTML outputs."""
    previous = load_manifest()
    current = {}
    for path in paths:
        key = path.relative_to(ROOT).as_posix()
        if frozen_result_path(path).is_file():
            current[key] = freeze_fingerprint(path)
        elif key in previous and previous[key] == freeze_fingerprint(path):
            # Quarto can omit freeze files for documents with no executable cells.
            continue
    MANIFEST.write_text(
        json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def aggregate_specs(paths: list[Path], whole_site: bool) -> tuple[list[str], list[str]]:
    by_name = {spec_name(s): (s, "core") for s in CORE_SPECS}
    frozen: list[str] = []
    manifest = load_manifest() if whole_site else {}
    for path in paths:
        packages, freeze = specs_for(path)
        relative = str(path.relative_to(ROOT))
        # Explicitly frozen docs require precomputed outputs for global renders.
        # A single-document Quarto render always executes, even with freeze true.
        if whole_site and freeze:
            result_path = frozen_result_path(path)
            if not result_path.is_file():
                raise ValueError(
                    f"{relative} declares execute.freeze: true, but no frozen HTML "
                    f"result exists at {result_path.relative_to(ROOT)}. "
                    "Render this document on the compute cluster, commit its "
                    "_freeze result, and then build the site."
                )
            frozen.append(relative)
            continue
        # Auto-freeze: skip extra runtime packages only when the previously
        # successful execution has an exact source match and a frozen result.
        if (whole_site and frozen_result_path(path).is_file()
                and manifest.get(relative) == freeze_fingerprint(path)):
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
    except (ValueError, OSError, json.JSONDecodeError, yaml.YAMLError) as error:
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
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode == 0 and whole_site:
        write_manifest(paths)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
