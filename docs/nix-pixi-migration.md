# Nix + Pixi migration status

The repository started with a proof-of-concept `pixi.toml` and a `pixi install` verification workflow. The chosen architecture is now **dynamic `pixi exec` + Quarto One-pass rendering**; see [one-pass-render.md](one-pass-render.md) for commands and the `ci-packages` contract.

- Nix supplies Quarto, Pixi, and Python + PyYAML for parsing .qmd frontmatter.
- Each post declares extra conda-forge package specs with `ci-packages`.
- A single `pixi exec` resolves the union with shared baseline R/Python/Pandoc specs.
- Micromamba remains solely to satisfy reticulate's Conda-detection compatibility logic; there is no user-managed Conda environment.
- The experimental branch's GitHub Actions workflow renders without publishing. The existing `main` publisher remains unchanged.
- Historical `renv` and `pyenv` artifacts may remain temporarily for rollback, but should no longer activate or install anything in the replacement renderer.
- Pixi Exec currently has no project lockfile. Package/version reproducibility requires explicit constraints or a later separate lockfile design.
