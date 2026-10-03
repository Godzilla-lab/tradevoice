#!/usr/bin/env bash
# Before vs after for the speech fixes (E11) on consented market voice notes, using the server's keys.
# Copy the notes + expected.csv to the server first (docs/TESTING.md, "Speech before vs after"), then:
#   sudo bash /opt/tradevoice/app/deploy/server/speech_ab.sh ~/notes
# Writes FOLDER/speech_ab.csv (it holds the words heard: keep it private, delete it when done). Wakes N-ATLaS.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "Run it with sudo: sudo bash $0 FOLDER"; exit 1; }
[ -f "${1:-}/expected.csv" ] || { echo "Usage: sudo bash $0 FOLDER   (FOLDER has the notes and expected.csv)"; exit 1; }
SRC=$(realpath "$1"); shift
WORK=$(mktemp -d /var/tmp/tv-speech-ab.XXXXXX)          # the app user can't read your home folder: work on a copy
trap 'rm -rf "$WORK"' EXIT
cp -r "$SRC"/. "$WORK"/ && chown -R tradevoice "$WORK"
cd /opt/tradevoice/app
runuser -u tradevoice -- /opt/tradevoice/venv/bin/python scripts/speech_ab.py "$WORK" --out "$WORK/speech_ab.csv" "$@"
cp "$WORK/speech_ab.csv" "$SRC/speech_ab.csv" && chown --reference="$SRC" "$SRC/speech_ab.csv"
echo "Saved: $SRC/speech_ab.csv"
