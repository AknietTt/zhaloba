#!/bin/sh
set -e

echo "Starting AutoPark backend..."
python -m uvicorn api:app --host 0.0.0.0 --port 8000 &

echo "Starting Telegram bot..."
python bot.py &

wait
