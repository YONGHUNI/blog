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

The site default in `_quarto.yml` is `execute.freeze: false`. All ordinary QMD computation is performed by GitHub Actions, using only repository input files and the fetched datasets. Actions does not auto-add ignored/new `_freeze` outputs; the production bot can commit updates to already tracked freeze files only when they actually change. Previously tracked legacy `_freeze` files are not used when freeze is disabled.

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

## Production publishing: single job, one render, skip empty freeze commits

`.github/workflows/publish.yml` runs **one job** on `main` pushes (or a manual dispatch on `main` only).

1. Nix supplies the site tools; `scripts/render-site.py` assembles package specs and executes Quarto **once** in a shared Pixi environment.
2. Verify that the expected HTML documents exist in `_site/`.
3. `quarto-dev/quarto-actions/setup@v2` supplies the publisher CLI; `quarto-dev/quarto-actions/publish@v2` targets the existing `gh-pages` branch with `render: false`. This step only publishes the already rendered site and **must not render a second time**.
4. Finally, enumerate **existing, tracked `_freeze/` files whose contents were modified** with `git diff --name-only -z --diff-filter=M -- _freeze/`. Explicitly **exclude deletions**, which can result from Quarto re-running ordinary posts. If no modified files remain, skip the commit and push. Otherwise stage only those existing modified files and commit to `main` with `[skip ci]`.

`_freeze/` remains ignored by default. The bot intentionally does **not** add newly generated, ignored freeze files; only the author can push a new cluster-produced result by using `git add -f _freeze/posts/<name>/index/`. This preserves the ability to opt into CPU/GPU cluster computation without automatically publishing every local calculation cache.

Ordinary posts use `freeze: false`; Quarto can **delete** their old tracked `_freeze` files during a full render. The publisher **never commits those deletions**, and logs how many it excluded. It will commit only already tracked files whose *contents* changed and remain on disk. The author remains responsible for explicitly pushing newly generated CPU/GPU freeze outputs. If strict manual-only freeze control is later desired, remove the final bot commit step entirely.

The `test-nix-pixi.yml` workflow remains separate and **never publishes**. It performs the full Nix + Pixi integration test on the refactor branch. The test branch does not exercise the actual gh-pages publication; this must be verified after merging to `main`.
