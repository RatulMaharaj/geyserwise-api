"""
Geyserwise Delta T API

FastAPI server for local control of Geyserwise solar geyser controller via tinytuya.
Designed to integrate with Homebridge HTTP plugins for HomeKit control.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

import httpx
import tinytuya
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration from environment variables."""
    device_id: str = Field(alias="GEYSERWISE_DEVICE_ID")
    local_key: str = Field(alias="GEYSERWISE_LOCAL_KEY")
    ip_address: str = Field(alias="GEYSERWISE_IP")
    version: float = Field(default=3.4, alias="GEYSERWISE_VERSION")
    port: int = Field(default=8099, alias="GEYSERWISE_API_PORT")
    webhook_url: str = Field(default="http://localhost:51830", alias="HOMEBRIDGE_WEBHOOK_URL")
    sync_interval: int = Field(default=30, alias="SYNC_INTERVAL_SECONDS")

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
        "populate_by_name": True,
    }


# DP Mappings for Geyserwise Delta T (keys are strings)
DP_POWER = "1"           # Power on/off (bool)
DP_MODE = "2"            # Mode: "Timer", etc.
DP_TANK_TEMP = "10"      # Current tank temperature
DP_ELEMENT = "13"        # Element status: "On"/"Off"
DP_PUMP = "101"          # Solar pump status: "On"/"Off"
DP_DIFFERENTIAL = "102"  # Solar differential (°C)
DP_BLOCK1 = "103"        # Block 1 temperature setpoint
DP_BLOCK2 = "104"        # Block 2 temperature setpoint
DP_BLOCK3 = "105"        # Block 3 temperature setpoint
DP_BLOCK4 = "106"        # Block 4 temperature setpoint
DP_ANTIFREEZE = "107"    # Anti-freeze temperature
DP_COLLECTOR = "108"     # Solar collector temperature
DP_HOLIDAY = "109"       # Holiday mode (0=off, 1=on)

BLOCK_DPS = {1: DP_BLOCK1, 2: DP_BLOCK2, 3: DP_BLOCK3, 4: DP_BLOCK4}

# Global device instance
device: Optional[tinytuya.Device] = None
settings: Optional[Settings] = None
sync_task: Optional[asyncio.Task] = None


async def sync_to_homebridge():
    """Periodically sync device state to Homebridge webhooks."""
    while True:
        try:
            dps = get_status()
            async with httpx.AsyncClient() as client:
                # Sync block temperatures (as both current and target)
                for block_num in range(1, 5):
                    block_temp = dps.get(BLOCK_DPS[block_num], 0)
                    tank_temp = dps.get(DP_TANK_TEMP, 0)
                    # Update current temp (show tank temp) and target temp (block setpoint)
                    await client.get(
                        f"{settings.webhook_url}/?accessoryId=geyser-block-{block_num}&currenttemperature={tank_temp}"
                    )
                    await client.get(
                        f"{settings.webhook_url}/?accessoryId=geyser-block-{block_num}&targettemperature={block_temp}"
                    )
                    # Set heating state based on element status
                    element_on = dps.get(DP_ELEMENT) == "On"
                    current_state = 1 if element_on else 0  # 0=Off, 1=Heating
                    await client.get(
                        f"{settings.webhook_url}/?accessoryId=geyser-block-{block_num}&currentstate={current_state}"
                    )
                
                # Sync holiday mode
                holiday = dps.get(DP_HOLIDAY, 0) == 1
                await client.get(
                    f"{settings.webhook_url}/?accessoryId=geyser-holiday&state={'true' if holiday else 'false'}"
                )
        except Exception as e:
            print(f"Sync error: {e}")
        
        await asyncio.sleep(settings.sync_interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize device connection on startup."""
    global device, settings, sync_task
    settings = Settings()
    device = tinytuya.Device(
        dev_id=settings.device_id,
        address=settings.ip_address,
        local_key=settings.local_key,
        version=settings.version,
    )
    device.set_socketPersistent(True)
    
    # Start sync task
    sync_task = asyncio.create_task(sync_to_homebridge())
    
    yield
    
    # Cleanup
    if sync_task:
        sync_task.cancel()
    if device:
        device.close()


app = FastAPI(
    title="Geyserwise API",
    description="Local control of Geyserwise Delta T solar geyser controller",
    version="1.0.0",
    lifespan=lifespan,
)


# --- Response Models ---

class StatusResponse(BaseModel):
    power: bool
    mode: str
    tank_temp: int
    collector_temp: int
    element: str
    pump: str
    differential: int
    antifreeze: int
    holiday: bool
    blocks: dict[str, int]


class BlockResponse(BaseModel):
    block: int
    temperature: int


class HolidayResponse(BaseModel):
    holiday: bool


class PowerResponse(BaseModel):
    power: bool


# --- Helper Functions ---

def get_status() -> dict:
    """Get current device status."""
    result = device.status()
    if "Error" in result:
        raise HTTPException(status_code=503, detail=f"Device error: {result['Error']}")
    return result.get("dps", {})


def set_dp(dp: str, value) -> dict:
    """Set a DP value and return new status."""
    result = device.set_value(int(dp), value)
    if result and "Error" in result:
        raise HTTPException(status_code=503, detail=f"Device error: {result['Error']}")
    return get_status()


# --- API Endpoints ---

@app.get("/", response_model=StatusResponse)
async def root():
    """Get full device status."""
    dps = get_status()
    return StatusResponse(
        power=dps.get(DP_POWER, False),
        mode=dps.get(DP_MODE, "Unknown"),
        tank_temp=dps.get(DP_TANK_TEMP, 0),
        collector_temp=dps.get(DP_COLLECTOR, 0),
        element=dps.get(DP_ELEMENT, "Off"),
        pump=dps.get(DP_PUMP, "Off"),
        differential=dps.get(DP_DIFFERENTIAL, 0),
        antifreeze=dps.get(DP_ANTIFREEZE, 0),
        holiday=dps.get(DP_HOLIDAY, 0) == 1,
        blocks={
            "block1": dps.get(DP_BLOCK1, 0),
            "block2": dps.get(DP_BLOCK2, 0),
            "block3": dps.get(DP_BLOCK3, 0),
            "block4": dps.get(DP_BLOCK4, 0),
        },
    )


@app.get("/status")
async def status():
    """Get raw DP status."""
    return get_status()


# --- Power Control ---

@app.get("/power", response_model=PowerResponse)
async def get_power():
    """Get power state."""
    dps = get_status()
    return PowerResponse(power=dps.get(DP_POWER, False))


@app.post("/power/on", response_model=PowerResponse)
async def power_on():
    """Turn power on."""
    set_dp(DP_POWER, True)
    return PowerResponse(power=True)


@app.post("/power/off", response_model=PowerResponse)
async def power_off():
    """Turn power off."""
    set_dp(DP_POWER, False)
    return PowerResponse(power=False)


# --- Block Temperature Control ---

@app.get("/block/{block_num}", response_model=BlockResponse)
async def get_block(block_num: int):
    """Get block temperature (1-4)."""
    if block_num not in BLOCK_DPS:
        raise HTTPException(status_code=400, detail="Block must be 1-4")
    dps = get_status()
    return BlockResponse(block=block_num, temperature=dps.get(BLOCK_DPS[block_num], 0))


@app.post("/block/{block_num}/{temperature}", response_model=BlockResponse)
async def set_block(block_num: int, temperature: int):
    """Set block temperature (1-4, 30-75°C)."""
    if block_num not in BLOCK_DPS:
        raise HTTPException(status_code=400, detail="Block must be 1-4")
    if not 30 <= temperature <= 75:
        raise HTTPException(status_code=400, detail="Temperature must be 30-75°C")
    set_dp(BLOCK_DPS[block_num], temperature)
    return BlockResponse(block=block_num, temperature=temperature)


@app.get("/blocks")
async def get_blocks():
    """Get all block temperatures."""
    dps = get_status()
    return {
        "block1": dps.get(DP_BLOCK1, 0),
        "block2": dps.get(DP_BLOCK2, 0),
        "block3": dps.get(DP_BLOCK3, 0),
        "block4": dps.get(DP_BLOCK4, 0),
    }


@app.post("/blocks/{temperature}")
async def set_all_blocks(temperature: int):
    """Set all blocks to the same temperature."""
    if not 30 <= temperature <= 75:
        raise HTTPException(status_code=400, detail="Temperature must be 30-75°C")
    device.set_multiple_values({
        int(DP_BLOCK1): temperature,
        int(DP_BLOCK2): temperature,
        int(DP_BLOCK3): temperature,
        int(DP_BLOCK4): temperature,
    })
    return {"block1": temperature, "block2": temperature, "block3": temperature, "block4": temperature}


# --- Holiday Mode ---

@app.get("/holiday", response_model=HolidayResponse)
async def get_holiday():
    """Get holiday mode status."""
    dps = get_status()
    return HolidayResponse(holiday=dps.get(DP_HOLIDAY, 0) == 1)


@app.post("/holiday/on", response_model=HolidayResponse)
async def holiday_on():
    """Enable holiday mode."""
    set_dp(DP_HOLIDAY, 1)
    return HolidayResponse(holiday=True)


@app.post("/holiday/off", response_model=HolidayResponse)
async def holiday_off():
    """Disable holiday mode."""
    set_dp(DP_HOLIDAY, 0)
    return HolidayResponse(holiday=False)


# --- Temperature Readings (Read-only) ---

@app.get("/tank")
async def get_tank_temp():
    """Get current tank temperature."""
    dps = get_status()
    return {"temperature": dps.get(DP_TANK_TEMP, 0)}


@app.get("/collector")
async def get_collector_temp():
    """Get solar collector temperature."""
    dps = get_status()
    return {"temperature": dps.get(DP_COLLECTOR, 0)}


@app.get("/element")
async def get_element():
    """Get element status."""
    dps = get_status()
    return {"status": dps.get(DP_ELEMENT, "Off"), "on": dps.get(DP_ELEMENT) == "On"}


@app.get("/pump")
async def get_pump():
    """Get solar pump status."""
    dps = get_status()
    return {"status": dps.get(DP_PUMP, "Off"), "on": dps.get(DP_PUMP) == "On"}


# --- Homebridge HTTP Plugin Compatibility ---
# These endpoints follow the format expected by homebridge-http-thermostat

@app.get("/homebridge/block/{block_num}/temperature")
async def hb_get_temperature(block_num: int):
    """Get block temp for Homebridge (returns plain number)."""
    if block_num not in BLOCK_DPS:
        raise HTTPException(status_code=400, detail="Block must be 1-4")
    dps = get_status()
    return dps.get(BLOCK_DPS[block_num], 0)


@app.get("/homebridge/block/{block_num}/target")
async def hb_get_target(block_num: int):
    """Get target temp for Homebridge (same as current for blocks)."""
    return await hb_get_temperature(block_num)


@app.get("/homebridge/block/{block_num}/set/{temperature}")
async def hb_set_temperature(block_num: int, temperature: int):
    """Set block temp for Homebridge (GET endpoint for compatibility)."""
    if block_num not in BLOCK_DPS:
        raise HTTPException(status_code=400, detail="Block must be 1-4")
    if not 30 <= temperature <= 75:
        raise HTTPException(status_code=400, detail="Temperature must be 30-75°C")
    set_dp(BLOCK_DPS[block_num], temperature)
    return temperature


@app.get("/homebridge/holiday/status")
async def hb_holiday_status():
    """Get holiday mode for Homebridge (returns 0 or 1)."""
    dps = get_status()
    return dps.get(DP_HOLIDAY, 0)


@app.get("/homebridge/holiday/set/{state}")
async def hb_holiday_set(state: int):
    """Set holiday mode for Homebridge (0=off, 1=on)."""
    set_dp(DP_HOLIDAY, 1 if state else 0)
    return state


if __name__ == "__main__":
    import uvicorn
    settings = Settings()
    uvicorn.run(app, host="0.0.0.0", port=settings.port)
