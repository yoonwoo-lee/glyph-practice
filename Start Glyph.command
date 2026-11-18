#!/bin/bash
# Mac: double-click this file to start Glyph with the camera. It picks the camera that sees a sheet
# of paper, and keeps the Mac awake while it runs. Close the window or press Ctrl+C to stop.
cd "$(dirname "$0")" || { echo "Could not open the Glyph folder."; read -r; exit 1; }
caffeinate -dis -w $$ &
bash start.sh --camera auto "$@"
echo
read -r -p "Glyph stopped. Press Enter to close this window."
