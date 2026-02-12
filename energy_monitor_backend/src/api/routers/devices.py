from fastapi import APIRouter, Depends, HTTPException, status

from src.api import db
from src.api.schemas import ApiMessage, DeviceCreate, DeviceResponse, DeviceUpdate
from src.api.security import get_current_user

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get(
    "",
    response_model=list[DeviceResponse],
    summary="List devices",
    description="List all devices belonging to the authenticated user.",
    operation_id="devices_list",
)
def list_devices(current_user: dict = Depends(get_current_user)) -> list[DeviceResponse]:
    """List devices for current user."""
    rows = db.fetch_all(
        """
        SELECT id, name, location, model, manufacturer, serial_number, external_device_id,
               timezone, is_active, created_at, updated_at
        FROM devices
        WHERE user_id = %s
        ORDER BY created_at DESC
        """,
        (current_user["id"],),
    )
    return [DeviceResponse(**r) for r in rows]


@router.post(
    "",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create device",
    description="Create a new device for the authenticated user.",
    operation_id="devices_create",
)
def create_device(payload: DeviceCreate, current_user: dict = Depends(get_current_user)) -> DeviceResponse:
    """Create a device for current user."""
    # enforce unique per-user name (db constraint exists, but return nice error)
    existing = db.fetch_one("SELECT id FROM devices WHERE user_id=%s AND name=%s", (current_user["id"], payload.name))
    if existing:
        raise HTTPException(status_code=400, detail="Device name already exists")

    row = db.execute_returning_one(
        """
        INSERT INTO devices (
          user_id, name, location, model, manufacturer, serial_number, external_device_id, timezone
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id, name, location, model, manufacturer, serial_number, external_device_id,
                  timezone, is_active, created_at, updated_at
        """,
        (
            current_user["id"],
            payload.name,
            payload.location,
            payload.model,
            payload.manufacturer,
            payload.serial_number,
            payload.external_device_id,
            payload.timezone,
        ),
    )
    return DeviceResponse(**row)


def _get_device_or_404(user_id: str, device_id: str) -> dict:
    device = db.fetch_one(
        """
        SELECT id, name, location, model, manufacturer, serial_number, external_device_id,
               timezone, is_active, created_at, updated_at
        FROM devices
        WHERE id=%s AND user_id=%s
        """,
        (device_id, user_id),
    )
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.get(
    "/{device_id}",
    response_model=DeviceResponse,
    summary="Get device",
    description="Get a single device by id for the authenticated user.",
    operation_id="devices_get",
)
def get_device(device_id: str, current_user: dict = Depends(get_current_user)) -> DeviceResponse:
    """Get a device by id."""
    return DeviceResponse(**_get_device_or_404(str(current_user["id"]), device_id))


@router.put(
    "/{device_id}",
    response_model=DeviceResponse,
    summary="Update device",
    description="Update device fields (only for the authenticated user's device).",
    operation_id="devices_update",
)
def update_device(device_id: str, payload: DeviceUpdate, current_user: dict = Depends(get_current_user)) -> DeviceResponse:
    """Update a device by id."""
    _get_device_or_404(str(current_user["id"]), device_id)

    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        return DeviceResponse(**_get_device_or_404(str(current_user["id"]), device_id))

    # If name is changing, check uniqueness
    if "name" in fields:
        existing = db.fetch_one(
            "SELECT id FROM devices WHERE user_id=%s AND name=%s AND id<>%s",
            (current_user["id"], fields["name"], device_id),
        )
        if existing:
            raise HTTPException(status_code=400, detail="Device name already exists")

    set_clauses = []
    params = []
    for k, v in fields.items():
        set_clauses.append(f"{k}=%s")
        params.append(v)
    params.extend([device_id, current_user["id"]])

    row = db.execute_returning_one(
        f"""
        UPDATE devices
        SET {", ".join(set_clauses)}
        WHERE id=%s AND user_id=%s
        RETURNING id, name, location, model, manufacturer, serial_number, external_device_id,
                  timezone, is_active, created_at, updated_at
        """,
        tuple(params),
    )
    return DeviceResponse(**row)


@router.delete(
    "/{device_id}",
    response_model=ApiMessage,
    summary="Delete device",
    description="Deletes a device (and cascades readings/alerts per DB FK rules).",
    operation_id="devices_delete",
)
def delete_device(device_id: str, current_user: dict = Depends(get_current_user)) -> ApiMessage:
    """Delete a device."""
    affected = db.execute("DELETE FROM devices WHERE id=%s AND user_id=%s", (device_id, current_user["id"]))
    if affected == 0:
        raise HTTPException(status_code=404, detail="Device not found")
    return ApiMessage(message="Deleted")
