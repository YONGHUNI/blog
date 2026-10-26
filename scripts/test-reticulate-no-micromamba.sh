#!/usr/bin/env bash
# Compare three reticulate interpreter-selection methods in a Pixi environment
# that intentionally does NOT include micromamba or conda.
set -euo pipefail

pixi exec \
  --channel conda-forge \
  --spec 'r-base=4.5.*' \
  --spec r-reticulate \
  --spec 'python=3.12.*' \
  --spec numpy \
  -- bash -s <<'INNER_BASH'
set -u
export R_PROFILE_USER=/dev/null
export RETICULATE_USE_MANAGED_VENV=no
unset RETICULATE_PYTHON RETICULATE_CONDA RETICULATE_PYTHON_ENV RETICULATE_PYTHON_FALLBACK

PYTHON_PATH="$(command -v python)"
printf '\nPixi Python: %s\n' "$PYTHON_PATH"
printf 'Python version: '
"$PYTHON_PATH" --version
printf 'Rscript: %s\n' "$(command -v Rscript)"
printf 'micromamba on PATH: %s\n' "$(command -v micromamba || echo '(not found)')"
printf 'conda on PATH: %s\n' "$(command -v conda || echo '(not found)')"

for MODE in env use_python use_condaenv; do
  printf '\n========== Testing %s ==========\n' "$MODE"
  if [ "$MODE" = env ]; then
    export RETICULATE_PYTHON="$PYTHON_PATH"
  else
    unset RETICULATE_PYTHON
  fi

  if Rscript --vanilla - "$MODE" "$PYTHON_PATH" <<'RSCRIPT'
args <- commandArgs(trailingOnly = TRUE)
mode <- args[[1]]
python <- args[[2]]
library(reticulate)
cat('reticulate version:', as.character(packageVersion('reticulate')), '\n')
if (mode == 'use_python') {
  reticulate::use_python(python, required = TRUE)
} else if (mode == 'use_condaenv') {
  reticulate::use_condaenv(dirname(dirname(python)), required = TRUE)
}
config <- reticulate::py_config()
cat('Selected Python:', config$python, '\n')
cat('Python version:', as.character(config$version), '\n')
stopifnot(normalizePath(config$python) == normalizePath(python))
np <- reticulate::import('numpy')
stopifnot(as.numeric(np$mean(c(1, 2, 3))) == 2)
cat('NumPy import and mean: OK\n')
RSCRIPT
  then
    printf 'RESULT %s: PASS\n' "$MODE"
  else
    printf 'RESULT %s: FAIL (see reticulate diagnostic above)\n' "$MODE"
  fi
done

printf '\nAll three independent probes finished. Failures are diagnostic, not a shell-script error.\n'
INNER_BASH
