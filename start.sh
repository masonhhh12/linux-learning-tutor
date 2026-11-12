#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/backend"

if ! curl --silent --fail --max-time 5 \
  http://127.0.0.1:11434/api/tags > /dev/null; then
  echo "Ollama is not responding."
  echo "Start it with: sudo systemctl start ollama"
  exit 1
fi

echo "Starting Linux Learning Tutor..."
echo "Open http://localhost:8000 in your browser"
echo "Press Ctrl+C to stop the tutor."

exec ./venv/bin/python -m uvicorn main:app \
  --host 0.0.0.0 --port 8000 --reload
