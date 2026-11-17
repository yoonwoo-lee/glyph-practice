#!/bin/bash
# One command to set up and start Glyph:   bash start.sh        (add --demo for no camera)
set -e
cd "$(dirname "$0")"

if [ ! -d venv ]; then
  echo "[glyph] first run: setting up (about a minute)"
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

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
