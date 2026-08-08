#!/bin/sh
APP_DIR=/data/victron-gx-publisher
RUN_DIR="$APP_DIR/run"
LOG_DIR="$APP_DIR/logs"
KEY_FILE="$APP_DIR/secrets/neocities_api_key"
SUPERVISOR_LOG="$LOG_DIR/supervisor.log"

mkdir -p "$RUN_DIR" "$LOG_DIR" "$APP_DIR/output" "$APP_DIR/secrets"

start_worker() {
    name="$1"
    script="$2"
    pid_file="$RUN_DIR/$name.pid"

    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null
    then
        return
    fi

    nohup "$script" >/dev/null 2>&1 &
    echo "$!" > "$pid_file"
    printf '%s started %s (pid %s)\n' "$(date -Iseconds 2>/dev/null || date)" "$name" "$!" >>"$SUPERVISOR_LOG"
}

start_worker collector "$APP_DIR/venus/run-collector.sh"

if [ -s "$KEY_FILE" ]
then
    start_worker publisher "$APP_DIR/venus/run-publisher.sh"
else
    printf '%s Neocities publisher disabled: no key at %s\n' "$(date -Iseconds 2>/dev/null || date)" "$KEY_FILE" >>"$SUPERVISOR_LOG"
fi
