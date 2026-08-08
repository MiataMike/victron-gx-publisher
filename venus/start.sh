#!/bin/sh
APP_DIR=/data/victron-gx-publisher
RUN_DIR="$APP_DIR/run"
KEY_FILE="$APP_DIR/secrets/neocities_api_key"

mkdir -p "$RUN_DIR" "$APP_DIR/output" "$APP_DIR/secrets"

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
    logger -t victron-gx-publisher "started $name (pid $!)"
}

start_worker collector "$APP_DIR/venus/run-collector.sh"

if [ -s "$KEY_FILE" ]
then
    start_worker publisher "$APP_DIR/venus/run-publisher.sh"
else
    logger -t victron-gx-publisher "Neocities publisher disabled: no key at $KEY_FILE"
fi
