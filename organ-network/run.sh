#!/usr/bin/env bash
# Start the API + dashboard, then open http://127.0.0.1:8000
set -e
python -m uvicorn app.main:app --reload --port 8000
