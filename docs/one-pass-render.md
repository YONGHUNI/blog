# Nix + Pixi + Quarto: build and publishing

The blog runs on **one Nix development environment, one shared Pixi Exec environment, and one whole-site Quarto render**. The production `.github/workflows/publish.yml` contains a single job and publishes to the existing `gh-pages` branch without rerendering.

## Normal build

```bash
nix develop
python -m unittest discover -s scripts -p 'test_*.py' -v
python scripts/render-site.py --dry-run
python scripts/render-site.py
```

The GitHub Actions runner calls `nix develop -c python scripts/render-site.py` and then the Quarto publish action with `target: gh-pages` and `render: false`. Only `main` pushes and manual dispatches from `main` can publish. Publishing installs Quarto **1.9.37**, matching the Nix renderer, and clears only `.quarto/` (the disposable project cache) before `publish@v2 --no-render` to avoid Deno KV cache deserialization errors across CLI versions; `_site/` and manually committed `_freeze/` are preserved. `test-nix-pixi.yml` remains a non-deploying integration test on the refactor branch.

Nix and `flake.lock` pin the build-tool inputs. The current `pixi exec` environment is **not** controlled by `pixi.toml` or `pixi.lock` and can pick up newer compatible conda-forge packages between runs. For stricter reproducibility, constrain `ci-packages` versions or migrate to a locked Pixi project later.

## Per-document runtime dependencies

In the YAML header of an ordinary `.qmd` file:

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

`ci-packages` is **our custom convention**, not a built-in Quarto or Pixi field. The renderer merges package names and version restrictions into **one** conda-forge `pixi exec --spec` environment. The combined constraints must be compatible. PyPI-only and channel-specific specifications are not supported.

The shared runtime contains R, Python, Pandoc, `reticulate`, and a Micromamba **binary used only as a compatibility shim** for `reticulate` to detect the Pixi interpreter. Do not add `conda install`, `micromamba activate`, `renv::restore`, or custom Python environment setup to individual posts.

## Optional CPU/GPU cluster precomputation

The site default is `execute.freeze: false`: ordinary posts are actually executed in GitHub Actions on each build. There are currently **no posts that require externally frozen computation**.

When one is needed:

1. Set `execute: {freeze: true}` in only the heavy post's YAML header. Declare its computational dependencies under `ci-packages`; they are intentionally excluded from the Actions' shared environment for frozen documents.
2. On the cluster, render the **single document** with its computational environment. A targeted Quarto render executes the code even when `freeze: true` is set. The standard command for supported conda-forge environments is `python scripts/render-site.py --target posts/heavy/index.qmd`.
3. Inspect `_freeze/posts/heavy/index/execute-results/html.json` and all linked figures/resources. Commit the QMD and its selected artifacts: `git add posts/heavy/index.qmd`, `git add -f _freeze/posts/heavy/index/`, then commit and push.
4. On a whole-site Actions render, `scripts/render-site.py` requires the committed frozen HTML result, skips installing the heavy post's extra packages, and lets Quarto reuse the precomputed result. All other posts run normally.

The `_freeze/` directory is ignored by Git unless files are explicitly force-added. A global render can remove obsolete freeze outputs. The publisher therefore considers **only modified, already tracked** `_freeze` files for its optional bot commit. It skips when there are none and **does not stage deletions or new ignored files**. To change a frozen post's computation or data, rerun the heavy document on the cluster and explicitly push fresh frozen outputs before publishing. `freeze: true` does not invalidate automatically.

## Maintenance and migration notes

- The retired `renv/`, `pyenv/`, `renv.R`, and temporary Micromamba diagnostics are removed from the active source tree. Their historical contents are recoverable in Git history. The `data/renv` educational article remains unchanged.
- Internal developer documentation is kept in `docs/` and excluded from the published Quarto site by `project.render`.
- The retired standalone integration-test blog post is removed. The CI validates actual legacy R/Python posts and their HTML output; the Python metadata/unit tests remain in `scripts/test_render_site.py`.
- Existing nonfatal warnings about remote CV PDF resources may appear during publication.

## Automatic execution cache (Git-tracked)

Ordinary posts now use `freeze: auto`. A successful full-site render records SHA-256 fingerprints of each QMD with a frozen HTML execution result in `scripts/freeze-manifest.json`. On later builds the renderer omits the extra `ci-packages` requirements for a document **only when** its saved fingerprint matches and its frozen HTML result exists. Missing results or changed source force full dependency installation and execution; explicit `freeze: true` remains reserved for precomputed cluster jobs.

After a successful publish, Actions stages generated `_freeze/` outputs and the manifest. It commits and pushes to `main` only when the staging area differs. Quarto's HTML site is rebuilt on every push; previously computed R/Python chunks are not rerun when unchanged. External data and runtime version changes do not automatically invalidate Quarto freeze: regenerate affected documents deliberately.

For historical artifacts, the first build with this configuration creates the baseline freeze cache. The bot commits with `[skip ci]` to avoid feedback loops.
