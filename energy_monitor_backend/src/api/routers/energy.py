from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api import db
from src.api.schemas import EnergyLatestResponse, EnergyQueryResponse, EnergyReadingIngest, EnergyReadingResponse
from src.api.security import get_current_user

router = APIRouter(prefix="/energy", tags=["energy"])


def _ensure_device_owned(user_id: str, device_id: str) -> None:
    owned = db.fetch_one("SELECT id FROM devices WHERE id=%s AND user_id=%s", (device_id, user_id))
    if not owned:
        raise HTTPException(status_code=404, detail="Device not found")


@router.post(
    "/devices/{device_id}/readings",
    response_model=EnergyReadingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest an energy reading",
    description="Insert (or upsert by device_id+ts) an energy reading for a device.",
    operation_id="energy_ingest_reading",
)
def ingest_reading(
    device_id: str,
    payload: EnergyReadingIngest,
    current_user: dict = Depends(get_current_user),
) -> EnergyReadingResponse:
    """
    Ingest a single reading for a device.

    Uses DB unique constraint (device_id, ts) to prevent duplicates.
    If a reading at the same timestamp already exists, it will be updated.
    """
    user_id = str(current_user["id"])
    _ensure_device_owned(user_id, device_id)

    row = db.execute_returning_one(
        """
        INSERT INTO energy_readings (user_id, device_id, ts, power_w, voltage_v, current_a, energy_wh, source)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (device_id, ts)
        DO UPDATE SET
          power_w = EXCLUDED.power_w,
          voltage_v = EXCLUDED.voltage_v,
          current_a = EXCLUDED.current_a,
          energy_wh = EXCLUDED.energy_wh,
          source = EXCLUDED.source
        RETURNING id, device_id, ts, power_w, voltage_v, current_a, energy_wh, source, created_at
        """,
        (
            user_id,
            device_id,
            payload.ts,
            payload.power_w,
            payload.voltage_v,
            payload.current_a,
            payload.energy_wh,
            payload.source,
        ),
    )
    return EnergyReadingResponse(**row)


@router.get(
    "/devices/{device_id}/latest",
    response_model=EnergyLatestResponse,
    summary="Get latest reading",
    description="Returns the latest reading for the device (or null fields if none).",
    operation_id="energy_latest",
)
def latest_reading(device_id: str, current_user: dict = Depends(get_current_user)) -> EnergyLatestResponse:
    """Get latest reading for a device."""
    user_id = str(current_user["id"])
    _ensure_device_owned(user_id, device_id)

    row = db.fetch_one(
        """
        SELECT ts, power_w, voltage_v, current_a, energy_wh, source
        FROM energy_readings
        WHERE user_id=%s AND device_id=%s
        ORDER BY ts DESC
        LIMIT 1
        """,
        (user_id, device_id),
    )
    if not row:
        return EnergyLatestResponse(device_id=device_id, ts=None, power_w=None, voltage_v=None, current_a=None, energy_wh=None, source=None)
    return EnergyLatestResponse(device_id=device_id, **row)


@router.get(
    "/devices/{device_id}/range",
    response_model=EnergyQueryResponse,
    summary="Query readings in a time range",
    description="Returns readings for a device between start and end timestamps (inclusive).",
    operation_id="energy_range",
)
def query_range(
    device_id: str,
    start: datetime = Query(..., description="Start timestamp (ISO-8601)."),
    end: datetime = Query(..., description="End timestamp (ISO-8601)."),
    limit: int = Query(5000, ge=1, le=20000, description="Maximum number of readings to return."),
    current_user: dict = Depends(get_current_user),
) -> EnergyQueryResponse:
    """Query readings for a device in a time range."""
    user_id = str(current_user["id"])
    _ensure_device_owned(user_id, device_id)
    if end < start:
        raise HTTPException(status_code=400, detail="end must be >= start")

    rows = db.fetch_all(
        """
        SELECT id, device_id, ts, power_w, voltage_v, current_a, energy_wh, source, created_at
        FROM energy_readings
        WHERE user_id=%s AND device_id=%s AND ts >= %s AND ts <= %s
        ORDER BY ts ASC
        LIMIT %s
        """,
        (user_id, device_id, start, end, limit),
    )
    return EnergyQueryResponse(
        device_id=device_id,
        start=start,
        end=end,
        readings=[EnergyReadingResponse(**r) for r in rows],
    )
