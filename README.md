# Victron GX Publisher

A dependency-free service that runs directly on Venus OS. It discovers every
`com.victronenergy.solarcharger.*` service on the system D-Bus, reads each
`/Yield/System` value, sums the values, and atomically writes:

```json
{
  "lifetime_yield_kwh": 157.78,
  "charger_count": 2,
  "updated_at": "2026-08-08T12:30:00Z"
}
```

A separate optional worker uploads that JSON to Neocities.

## Native Venus design

The application originally ran in Docker on another computer and connected to
Venus through MQTT. The native version instead:

- reads the authoritative values directly from the local Venus system D-Bus
- discovers current and future solar chargers dynamically
- needs no Docker, MQTT client, portal ID, password, TLS, or third-party package
- stores the application and output on the update-persistent `/data` partition
- starts through `/data/rc.local` and restarts after failures
- keeps bounded logs under `/data/victron-gx-publisher/logs`

## Install on Venus OS

Enable SSH on LAN. Clone the branch on your normal computer and copy it to the
GX device:

```sh
git clone --branch venus-os-native --single-branch \
  https://github.com/MiataMike/victron-gx-publisher.git
scp -r victron-gx-publisher root@venus.local:/data/victron-gx-publisher
ssh root@venus.local /data/victron-gx-publisher/venus/install.sh
```

The installer must run from `/data/victron-gx-publisher`. It preserves an
existing `/data/rc.local` and only appends its idempotent startup hook.

Check operation:

```sh
tail -f /data/victron-gx-publisher/logs/collector.log
cat /data/victron-gx-publisher/output/solar.json
```

Stop or restart it:

```sh
/data/victron-gx-publisher/venus/stop.sh
/data/victron-gx-publisher/venus/start.sh
```

Configuration is in `venus/config.env`. `POLL_SECONDS` defaults to 30.
Firmware replaces the Venus root filesystem but preserves `/data`.

## Enable Neocities publishing

Create the key file:

```sh
mkdir -p /data/victron-gx-publisher/secrets
chmod 700 /data/victron-gx-publisher/secrets
printf '%s' 'your-neocities-api-key' \
  > /data/victron-gx-publisher/secrets/neocities_api_key
chmod 600 /data/victron-gx-publisher/secrets/neocities_api_key
/data/victron-gx-publisher/venus/start.sh
```

The uploader validates JSON, waits for writes to settle, skips unchanged
content, and retries failed uploads with capped exponential backoff.

## Development and test

```sh
python -m pip install -e '.[test]'
pytest
```

The tests mock the Venus `dbus` executable, so they run without GX hardware.
