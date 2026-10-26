# One-pass Pixi Exec rendering (experimental)

This branch tests **one Pixi Exec environment and one Quarto render for the whole site**. Production publishing remains unchanged.

## Local commands

Run from the blog repository root on NixOS/Linux:

    nix develop
    python scripts/render-site.py --dry-run
    python scripts/render-site.py --target posts/_pixi_exec_smoke/index.qmd
    python scripts/render-site.py

The targeted smoke command uses the QMD you created locally. It was not added to the repository. The last command renders the entire site in one Quarto invocation.

## Per-post dependency metadata

Declare additional dependencies in a post's YAML front matter, e.g.:

    ---
    title: Spatial Autocorrelation
    ci-packages:
      - r-spdep
      - r-sf
      - 'numpy=2.*'
    ---

The ci-packages field is a custom convention parsed by scripts/render-site.py, **not a built-in Quarto option**.

The script collects QMD front matter, deduplicates requirements, rejects conflicting versions of the same package, and installs the union in one temporary Pixi Exec environment. Unlike per-post Pixi Exec, this does not isolate the execution environments of individual posts.

Documents explicitly using execute.freeze: true do not contribute additional packages when rendering the entire project, because their existing Quarto freeze results should be used. Rendering such a document by itself does execute its code.

## Test environment and known limitations

- Nix provides Pixi, Quarto, Python and PyYAML. Generated flake.lock is worth committing once reviewed.
- The temporary environment does not change pixi.toml or pixi.lock.
- Pandoc 3.8.3 and Micromamba are included to match the successful Quarto 1.9.37 / reticulate 1.47.0 NixOS smoke test.
- Existing QMDs have not been migrated. Some have hard-coded Micromamba paths or commands and may fail when re-executed.
- Existing posts currently do not declare ci-packages. Add them before forcing execution of code that needs extra packages.
- Explicitly frozen documents require committed, valid _freeze results. This prototype does not verify their presence or freshness.
- Extra package versions without explicit constraints are not locked across time in pixi exec.
- The production publish.yml is intentionally unchanged. End-to-end website rendering has not yet been verified.
