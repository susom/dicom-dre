#!/bin/bash
set -euo pipefail

WORKSPACE_DIR="$(pwd)"

BLUE='\033[0;34m'
NC='\033[0m'

# Git doesn't like the UID changes from bind-mounting the source into the container.
if ! git config --global --get-all safe.directory | grep -qx "${WORKSPACE_DIR}"; then
  git config --global --add safe.directory "${WORKSPACE_DIR}"
fi

# Convenience aliases.
if ! grep -q "#dicom-dre#" "${HOME}/.bashrc" 2>/dev/null; then
  {
    echo '#dicom-dre#'
    echo 'alias ll="ls -alF"'
    echo 'alias la="ls -A"'
    echo 'alias l="ls -CF"'
  } >> "${HOME}/.bashrc"
fi

# Sync dependencies and build the CFFI JPEG-DCT extension (and python-gdcm from source).
echo -e "${BLUE}Running uv sync...${NC}"
uv sync

# Compile the CFFI JPEG-DCT acceleration extension into src/dicom_dre/.
# Without this the engine silently falls back to the ~300x-slower pure-Python
# entropy codec. Building from src/ so the module 'dicom_dre._jpeg_dct_accel'
# lands at src/dicom_dre/_jpeg_dct_accel.*.so.
echo -e "${BLUE}Compiling JPEG-DCT acceleration extension...${NC}"
(cd src && uv run python -m dicom_dre._jpeg_dct_accel_build)
rm -f src/dicom_dre/_jpeg_dct_accel.c src/dicom_dre/_jpeg_dct_accel.o

# Install git hooks so PHI-protection checks run on commit, push, and commit-msg.
echo -e "${BLUE}Installing git hooks...${NC}"
uv run pre-commit install --hook-type pre-commit --hook-type pre-push --hook-type commit-msg
