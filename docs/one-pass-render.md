# One-pass Nix + Pixi + Quarto rendering (migration branch)

This branch uses **one cached Pixi Exec environment and one Quarto invocation** to render the entire site. The `main` branch and its existing `.github/workflows/publish.yml` remain untouched until the test branch passes and a publishing migration is reviewed.

## Local workflow

```bash
nix develop
python -m unittest discover -s scripts -p 'test_*.py' -v
python scripts/render-site.py --dry-run
python scripts/render-site.py
```

For an isolated post execution test, use:

```bash
python scripts/render-site.py --target posts/pixi-onepass-test/index.qmd
```

**A single-post render always executes code even when `freeze: true` is set.** A whole-site render respects Quarto's freeze settings.

## Declare dependencies in the .qmd header

```yaml
---
title: "Spatial Analysis"
ci-packages:
  - r-sf
  - r-spdep
  - "numpy=2.*"
  - "networkx>=3.4"
---
```

`ci-packages` is a **custom Quarto frontmatter field**, not a built-in Pixi or Quarto field. Its entries are conda-forge package specifications passed unchanged to `pixi exec --spec`. Names and version constraints follow the simple Pixi/Conda MatchSpec forms; quote specs containing punctuation as in the example. R package names have a `r-` prefix (e.g. `r-sf`). PyPI-only packages and package-specific channels are **not supported yet**.

The renderer merges requirements from all included posts, deduplicates package names, fails early on conflicting specs, then calls `quarto render . --to html` **once**. Versions without constraints can evolve between environment resolutions; this temporary environment is **not pinned** by `pixi.toml` or `pixi.lock`. An existing `pixi.toml` (if present) is not read by `pixi exec` in this workflow.

Core R, Python, Pandoc and `micromamba` are included centrally. Micromamba is **only a reticulate compatibility binary**; Pixi performs all environment solving, installation and caching. Users should never run `micromamba install`, `activate` or `conda_create` from individual posts.

## Freeze strategy and limitations

- Existing posts with expensive computations can use `execute: {freeze: true}` during migration to preserve previously committed `_freeze` results. A targeted render always executes the code.
- `execute: {freeze: auto}` is suitable for new posts or migrated posts whose full computations can be re-executed in CI.
- Core packages are always resolved. Post-specific packages on explicitly frozen posts are omitted from the **whole-site** package union, but included in `--target` renders.
- The integration post `posts/pixi-onepass-test/index.qmd` has `freeze: false` to **force** real R + Python execution and check `reticulate` imports Pixi's Python.
- The current code does not support per-post environment isolation, PyPI-specific packages, exact-lock reproducibility or GPU-specific dependencies.
- Existing CV PDF 404 warnings are unrelated to Pixi.
- This non-deploying test workflow must pass before replacing the production publishing workflow.
