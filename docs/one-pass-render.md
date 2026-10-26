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
  - "numpy>=1.26,<2"
  - "networkx>=3.4"
---
```

`ci-packages` is a **custom Quarto frontmatter field**, not a built-in Pixi or Quarto field. Its entries are conda-forge package specifications passed unchanged to `pixi exec --spec`. Names and version constraints follow the simple Pixi/Conda MatchSpec forms; quote specs containing punctuation as in the example. R package names have a `r-` prefix (e.g. `r-sf`). PyPI-only packages and package-specific channels are **not supported yet**.

The renderer merges requirements from all included posts, deduplicates package names, fails early on conflicting specs, then calls `quarto render . --to html` **once**. Versions without constraints can evolve between environment resolutions; this temporary environment is **not pinned** by `pixi.toml` or `pixi.lock`. An existing `pixi.toml` (if present) is not read by `pixi exec` in this workflow.

Core R, Python, Pandoc and `micromamba` are included centrally. Micromamba is **only a reticulate compatibility binary**; Pixi performs all environment solving, installation and caching. Users should never run `micromamba install`, `activate` or `conda_create` from individual posts.

## Opt-in cluster freeze: default Actions execution, optional CPU/GPU offload

The site default in `_quarto.yml` is `execute.freeze: false`. All ordinary QMD computation is performed by GitHub Actions, using only repository input files and the fetched datasets. Actions **never commits** generated `_freeze` outputs. Previously tracked legacy `_freeze` files are not used when freeze is disabled.

For a future heavy post, the author can compute its results on a CPU or GPU cluster and publish only its selected frozen execution results:

1. Add `execute:\n  freeze: true` in the heavy QMD frontmatter; keep the complete `ci-packages` declaration and data/code in the repository.
2. On the cluster, render the **single QMD** after provisioning its specialized environment, e.g. `python scripts/render-site.py --target posts/heavy/index.qmd`. Quarto always executes a single-document render, including when it is marked frozen.
3. Inspect the generated `_freeze/posts/heavy/index/execute-results/html.json` and supporting `figure-html` assets.
4. Stage the heavy QMD plus **only its own freeze subtree** using `git add posts/heavy/index.qmd` and `git add -f _freeze/posts/heavy/index/`; commit and push to the intended branch. The existing `.gitignore` ignores _freeze by default, so `git add -f` is intentional.
5. In global CI rendering, the renderer checks for a frozen HTML result, then **omits the heavy post's extra package requirements**. Quarto uses the pushed frozen output, while other posts are executed normally.

**Important:** `freeze: true` does not automatically invalidate when the QMD source or input data changes. After editing code or changing data, regenerate and push that post's frozen output from the cluster before publishing. Its artifacts should be generated with a compatible Quarto version and inspected before publication.

For ordinary posts, do not use `freeze: true`; they run on GitHub Actions. `freeze: auto` is a different, source-change-based caching policy and is *not* needed for this default approach.

The current code does not provide per-post environment isolation, PyPI-specific packages, exact-lock reproducibility or GPU cluster provisioning. Provisioning specialized cluster software is the user's responsibility; `--target` can use the regular Pixi environment when its dependencies are available on conda-forge.

The integration post `posts/pixi-onepass-test/index.qmd` forces a real R/Python bridge test. Existing CV PDF 404 warnings are unrelated to Pixi. The non-deploying CI workflow must pass before replacing production publishing.
