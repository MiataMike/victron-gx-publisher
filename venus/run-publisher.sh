#!/bin/sh
APP_DIR=/data/victron-gx-publisher
LOG_DIR="$APP_DIR/logs"
LOG_FILE="$LOG_DIR/publisher.log"
set -a
. "$APP_DIR/venus/config.env"
set +a
mkdir -p "$LOG_DIR"

while true
do
    if [ -f "$LOG_FILE" ] && [ "$(wc -c < "$LOG_FILE")" -gt 1048576 ]
    then
        mv -f "$LOG_FILE" "$LOG_FILE.1"
    fi
    PYTHONPATH="$APP_DIR/src" /usr/bin/python3 -m victron_gx_publisher.publisher >>"$LOG_FILE" 2>&1
    printf '%s publisher stopped; restarting in 30 seconds\n' "$(date -Iseconds 2>/dev/null || date)" >>"$LOG_FILE"
    sleep 30
done
