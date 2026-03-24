# Geyserwise API

FastAPI server for local control of Geyserwise Delta T solar geyser controller via [tinytuya](https://github.com/jasonacox/tinytuya).

Designed for integration with [Homebridge](https://homebridge.io) HTTP plugins to expose your geyser to HomeKit.

## Features

- 🌡️ Read tank and solar collector temperatures
- 🔥 Monitor element and pump status
- ⏰ Control block temperatures (4 time-based setpoints)
- 🏖️ Toggle holiday mode
- ⚡ Full local control (no cloud dependency)
- 🍎 Homebridge-compatible endpoints

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

Copy `.env.example` to `.env` and fill in your device details:

```bash
cp .env.example .env
```

You'll need:
- `GEYSERWISE_DEVICE_ID` - Device ID from Tuya IoT Platform
- `GEYSERWISE_LOCAL_KEY` - Local key from Tuya IoT Platform
- `GEYSERWISE_IP` - Local IP address of your Geyserwise

Use [tinytuya wizard](https://github.com/jasonacox/tinytuya#setup-wizard) to discover these values.

### 3. Run

```bash
python main.py
# or
uvicorn main:app --host 0.0.0.0 --port 8099
```

API docs available at: http://localhost:8099/docs

## API Endpoints

### Status

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Full device status |
| `/status` | GET | Raw DP values |
| `/tank` | GET | Tank temperature |
| `/collector` | GET | Solar collector temperature |
| `/element` | GET | Element status (On/Off) |
| `/pump` | GET | Solar pump status (On/Off) |

### Control

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/power/on` | POST | Turn power on |
| `/power/off` | POST | Turn power off |
| `/block/{1-4}/{temp}` | POST | Set block temperature (30-75°C) |
| `/blocks/{temp}` | POST | Set all blocks to same temp |
| `/holiday/on` | POST | Enable holiday mode |
| `/holiday/off` | POST | Disable holiday mode |

### Homebridge Endpoints

These endpoints follow the format expected by `homebridge-http-thermostat`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/homebridge/block/{1-4}/temperature` | GET | Get block temp (plain number) |
| `/homebridge/block/{1-4}/set/{temp}` | GET | Set block temp |
| `/homebridge/holiday/status` | GET | Get holiday mode (0/1) |
| `/homebridge/holiday/set/{0\|1}` | GET | Set holiday mode |

## Homebridge Integration

Install [homebridge-http-thermostat](https://github.com/kiwi-cam/homebridge-http-thermostat):

```bash
npm install -g homebridge-http-thermostat
```

Add to your Homebridge config:

```json
{
  "accessory": "Thermostat",
  "name": "Geyser Block 1",
  "apiroutes": {
    "currentTemperature": "http://localhost:8099/homebridge/block/1/temperature",
    "targetTemperature": "http://localhost:8099/homebridge/block/1/target",
    "setTargetTemperature": "http://localhost:8099/homebridge/block/1/set/%f"
  },
  "minTemp": 30,
  "maxTemp": 75
}
```

## Running as a Service (macOS)

Create a launchd plist at `~/Library/LaunchAgents/com.geyserwise.api.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.geyserwise.api</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/geyserwise-api/main.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/geyserwise-api</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/geyserwise-api.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/geyserwise-api.log</string>
</dict>
</plist>
```

Load with:

```bash
launchctl load ~/Library/LaunchAgents/com.geyserwise.api.plist
```

## Geyserwise DP Reference

| DP | Description | Type | Values |
|----|-------------|------|--------|
| 1 | Power | bool | true/false |
| 2 | Mode | string | "Timer" |
| 10 | Tank Temperature | int | °C |
| 13 | Element Status | string | "On"/"Off" |
| 101 | Pump Status | string | "On"/"Off" |
| 102 | Solar Differential | int | °C |
| 103 | Block 1 Temp | int | 30-75°C |
| 104 | Block 2 Temp | int | 30-75°C |
| 105 | Block 3 Temp | int | 30-75°C |
| 106 | Block 4 Temp | int | 30-75°C |
| 107 | Anti-freeze Temp | int | °C |
| 108 | Collector Temperature | int | °C |
| 109 | Holiday Mode | int | 0/1 |

## License

MIT
