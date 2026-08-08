#!/bin/sh
APP_DIR=/data/victron-gx-publisher
set -a
. "$APP_DIR/venus/config.env"
set +a

while true
do
    PYTHONPATH="$APP_DIR/src" /usr/bin/python3 -m victron_gx_publisher.publisher 2>&1 |
        logger -t victron-gx-neocities
    logger -t victron-gx-neocities "publisher stopped; restarting in 30 seconds"
    sleep 30
done
