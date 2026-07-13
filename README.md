# Victron GX Publisher

A Dockerized Python 3.12 daemon that subscribes to a Victron GX MQTT broker,
dynamically discovers solar chargers, and writes their combined lifetime yield
to JSON.

The daemon subscribes to `N/+/solarcharger/+/Yield/System`. The latest
`{"value": number}` payload for each charger is summed and atomically written
to `output/solar.json`. It never publishes to Victron `W/...` command topics.
If `VRM_PORTAL_ID` is configured, it publishes only the read-refresh request
`R/<portal-id>/keepalive`.

## Credentials

Do not use the GX SSH root password. Use the device password associated with
the Venus OS local network security profile.

Copy `.env.example` to `.env` for non-secret configuration. Both Git and the
Docker build context exclude `.env`. For quick local testing,
`MQTT_PASSWORD` can be placed there, but a mounted secret file is preferred
because environment variables can appear in container inspection output:

```sh
mkdir -p ~/.config/victron-gx-publisher
chmod 700 ~/.config/victron-gx-publisher
printf '%s' 'your-device-password' \
  > ~/.config/victron-gx-publisher/mqtt_password
chmod 600 ~/.config/victron-gx-publisher/mqtt_password
```

Set this non-secret reference in `.env`:

```dotenv
MQTT_PASSWORD_FILE=/run/secrets/gx_mqtt_password
```

Never commit `.env`, a password file, or a real credential in
`.env.example`.

## Run with Docker

Build the runtime image:

```sh
docker build -t victron-gx-publisher .
```

Run it with the password mounted read-only:

```sh
docker run --rm \
  --name victron-gx-publisher \
  --user "$(id -u):$(id -g)" \
  --env-file .env \
  -v "$HOME/.config/victron-gx-publisher/mqtt_password:/run/secrets/gx_mqtt_password:ro" \
  -v "$(pwd)/output:/app/output" \
  victron-gx-publisher
```

Current GX security profiles commonly use authenticated TLS on port 8883 with
a self-signed certificate. Those settings are the defaults. Set
`MQTT_TLS_INSECURE=false` and `MQTT_CA_CERT` to a mounted CA certificate when
certificate validation is available. If a container cannot resolve
`venus.local`, set `MQTT_HOST` to the GX device's LAN IP.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MQTT_HOST` | `venus.local` | GX MQTT hostname or IP |
| `MQTT_PORT` | `8883` | MQTT port |
| `MQTT_USERNAME` | unset | MQTT username, commonly `admin` |
| `MQTT_PASSWORD` | unset | Local-development password |
| `MQTT_PASSWORD_FILE` | unset | Preferred mounted password file |
| `MQTT_TLS` | `true` | Enable MQTT over TLS |
| `MQTT_TLS_INSECURE` | `true` | Allow the GX self-signed certificate |
| `MQTT_CA_CERT` | unset | Optional mounted CA certificate |
| `VRM_PORTAL_ID` | unset | Optional ID used to request a value refresh |
| `OUTPUT_PATH` | `output/solar.json` | JSON output path |
| `LOG_LEVEL` | `INFO` | Python logging level |

Example output:

```json
{
  "lifetime_yield_kwh": 1234.56,
  "charger_count": 2,
  "updated_at": "2026-07-13T12:30:00Z"
}
```

## Test

```sh
docker build --target test .
```

## Publish to Neocities

The Neocities publisher is a separate worker in the same image. It reads
`solar.json` from the shared output directory but receives no GX credential.
The MQTT collector receives no Neocities key.

Generate an API key using the
[official Neocities API](https://neocities.org/api), then store it outside the
repository:

```sh
mkdir -p ~/.config/victron-gx-publisher
chmod 700 ~/.config/victron-gx-publisher
read -rsp "Neocities API key: " NEOCITIES_KEY
printf '%s' "$NEOCITIES_KEY" \
  > ~/.config/victron-gx-publisher/neocities_api_key
unset NEOCITIES_KEY
chmod 600 ~/.config/victron-gx-publisher/neocities_api_key
```

Run the publisher alongside the MQTT collector:

```sh
docker run --rm \
  --name victron-neocities-publisher \
  --user "$(id -u):$(id -g)" \
  --env-file .env \
  -v "$HOME/.config/victron-gx-publisher/neocities_api_key:/run/secrets/neocities_api_key:ro" \
  -v "$(pwd)/output:/app/output:ro" \
  victron-gx-publisher \
  victron-gx-publish-neocities
```

The worker validates the JSON, waits for writes to settle, skips unchanged
content, and uploads it with Bearer authentication as multipart form data. It
never calls the Neocities delete API. Upload failures are retried with capped
exponential backoff and do not interrupt MQTT collection.

Neocities asks recurring API clients to limit updates to one per minute. The
default interval here is five minutes.

| Variable | Default | Purpose |
| --- | --- | --- |
| `NEOCITIES_API_KEY_FILE` | `/run/secrets/neocities_api_key` | Mounted API-key file |
| `NEOCITIES_REMOTE_PATH` | `solar.json` | Destination filename |
| `NEOCITIES_MIN_UPLOAD_INTERVAL` | `300` | Minimum seconds between uploads |
| `NEOCITIES_SETTLE_SECONDS` | `10` | Quiet period before upload |
| `NEOCITIES_POLL_SECONDS` | `2` | Local file polling interval |
| `NEOCITIES_REQUEST_TIMEOUT` | `15` | HTTP request timeout |
