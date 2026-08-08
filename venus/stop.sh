#!/bin/sh
RUN_DIR=/data/victron-gx-publisher/run

for name in collector publisher
do
    pid_file="$RUN_DIR/$name.pid"
    if [ -f "$pid_file" ]
    then
        pid="$(cat "$pid_file")"
        if kill -0 "$pid" 2>/dev/null
        then
            kill "$pid"
        fi
        rm -f "$pid_file"
    fi
done
