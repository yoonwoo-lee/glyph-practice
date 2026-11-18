#!/bin/bash
# One command to set up and start Glyph:   bash start.sh        (add --demo for no camera)
set -e
cd "$(dirname "$0")"

# Windows (Git Bash) has "python" or "py" instead of "python3", and venv/Scripts instead of venv/bin.
PY=python3
command -v python3 >/dev/null 2>&1 || PY=python
command -v "$PY" >/dev/null 2>&1 || PY="py -3"

if [ ! -d venv ]; then
  echo "[glyph] first run: setting up (about a minute)"
  $PY -m venv venv
fi
if [ -f venv/Scripts/activate ]; then
  source venv/Scripts/activate
else
  source venv/bin/activate
fi
# Install the libraries only when requirements.txt has changed since the last install. That keeps
# start-up quick, and means Glyph still starts where there is no internet (a venue's Wi-Fi, say).
STAMP=venv/.requirements-installed
if [ ! -f "$STAMP" ] || ! cmp -s requirements.txt "$STAMP"; then
  python -m pip install -q --upgrade pip || true
  if python -m pip install -q -r requirements.txt; then
    cp requirements.txt "$STAMP"
  elif python -c "import cv2, numpy, dotenv, fastapi, uvicorn, google.genai" 2>/dev/null; then
    echo "[glyph] could not check for library updates (no internet?). Starting with what is installed."
  else
    echo "[glyph] could not install the libraries Glyph needs. Check the internet connection and run this again."
    exit 1
  fi
fi

if [ ! -f .env ]; then
  if [ -f ../talking-menu/agent/.env ] && grep -q '^GEMINI_API_KEY=' ../talking-menu/agent/.env; then
    grep '^GEMINI_API_KEY=' ../talking-menu/agent/.env > .env
    echo "[glyph] copied your Gemini key from the talking-menu project into .env"
  else
    cp .env.example .env
    echo "[glyph] no key yet: put your Gemini key in .env (running with fake answers for now)"
  fi
fi

python run.py "$@"
