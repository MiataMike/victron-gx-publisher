# Victron GX Publisher

A dependency-free Python service that runs directly on Venus OS. It subscribes
to the GX device's local MQTT broker, dynamically discovers every solar charger,
sums `/Yield/System`, and atomically writes:

```json
{
  "lifetime_yield_kwh": 1234.56,
  "charger_count": 2,
  "updated_at": "2026-08-08T12:30:00Z"
}
```

A separate optional worker uploads that JSON to Neocities. The collector never
receives the Neocities key, never writes to Victron `W/...` command topics,
and has no third-party runtime packages.

## Why native Venus OS?

The application originally ran in a Python 3.12 Docker container on another
computer. The native version instead:

- uses the GX broker at `127.0.0.1:1883`
- needs no MQTT password or TLS for the loopback connection
- replaces `paho-mqtt` with a small MQTT 3.1.1 client
- stores the application and output under the update-persistent `/data` partition
- starts through `/data/rc.local` and restarts workers after failures
- sends logs to the Venus OS system log instead of growing log files on flash

## Install on Venus OS

Enable SSH on LAN. Clone the branch on your normal computer and copy it to the
GX device; this does not assume that the stripped-down Venus OS image includes
Git:

```sh
git clone --branch venus-os-native --single-branch \
  https://github.com/MiataMike/victron-gx-publisher.git
scp -r victron-gx-publisher root@venus.local:/data/victron-gx-publisher
ssh root@venus.local /data/victron-gx-publisher/venus/install.sh
```

If the repository is already at `/data/victron-gx-publisher`, simply update its
files and rerun `venus/install.sh`; the installation is idempotent.

The installer is intentionally conservative: it must run from
`/data/victron-gx-publisher`, preserves an existing `/data/rc.local`, and only
appends its startup hook if missing.

Check operation:

```sh
logread -f | grep victron-gx
cat /data/victron-gx-publisher/output/solar.json
```

Stop or restart it manually:

```sh
/data/victron-gx-publisher/venus/stop.sh
/data/victron-gx-publisher/venus/start.sh
```

Configuration is in `venus/config.env`. The local defaults should work without
credentials. If initial retained values do not arrive, set `VRM_PORTAL_ID` in
that file so the collector publishes the read-refresh request
`R/<portal-id>/keepalive`.

Venus OS firmware replaces the root filesystem but preserves `/data`; this is
why the application, configuration, output, and boot hook live there.

## Enable Neocities publishing

Create the key file on the GX device:

```sh
mkdir -p /data/victron-gx-publisher/secrets
chmod 700 /data/victron-gx-publisher/secrets
printf '%s' 'your-neocities-api-key' \
  > /data/victron-gx-publisher/secrets/neocities_api_key
chmod 600 /data/victron-gx-publisher/secrets/neocities_api_key
/data/victron-gx-publisher/venus/start.sh
```

The worker validates JSON, waits for writes to settle, skips unchanged content,
and retries failed uploads with capped exponential backoff. Its default minimum
upload interval is five minutes.

## Development and test

The package still runs on ordinary Python systems:

```sh
python -m pip install -e '.[test]'
pytest
```

Or use the existing container test:

```sh
docker build --target test .
```

The native MQTT implementation is deliberately limited to the features this
read-only collector needs: MQTT 3.1.1, wildcard subscriptions, QoS 0/1 incoming
messages, QoS 0 publishing, keepalive, optional authentication, and optional
TLS.
