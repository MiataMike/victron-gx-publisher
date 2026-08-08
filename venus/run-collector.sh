#!/bin/sh
APP_DIR=/data/victron-gx-publisher
set -a
. "$APP_DIR/venus/config.env"
set +a

while true
do
    PYTHONPATH="$APP_DIR/src" /usr/bin/python3 -m victron_gx_publisher.daemon 2>&1 |
        logger -t victron-gx-publisher
    logger -t victron-gx-publisher "collector stopped; restarting in 5 seconds"
    sleep 5
done
