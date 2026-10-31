#!/usr/bin/env bash
# Builds a standalone app in dist/CoilSpringDesigner/
set -e
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm CoilSpringDesigner.spec
echo "Done. Run dist/CoilSpringDesigner/CoilSpringDesigner"
