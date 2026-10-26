# Nix + Pixi migration (stage 1)

This is an isolated, **non-deploying** migration trial. The current Quarto Publish workflow and `renv` installation remain unchanged until a replacement has been tested.

- `flake.nix` provides the Pixi executable and Quarto CLI.
- `pixi.toml` defines a baseline CPU-oriented R/Python runtime and native GIS dependencies.
- `pixi.lock` is **not yet committed**. The first CI verification resolves the environment and uploads the generated lockfile. Review and commit that file before treating this as a reproducible environment.
- The `gpu` feature and compatibility fixes to older posts are deliberately postponed.

On Linux with Nix installed:

```bash
nix develop -c pixi install
nix develop -c pixi run check-r
nix develop -c pixi run check-python
```

Do not render the entire website with this trial yet. The repository still auto-activates `renv` from `.Rprofile`, and some posts refer to Micromamba-specific Python paths.
