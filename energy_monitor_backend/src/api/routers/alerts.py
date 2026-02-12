from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api import db
from src.api.schemas import (
    AlertCreate,
    AlertEventResponse,
    AlertResponse,
    AlertUpdate,
    ApiMessage,
)
from src.api.security import get_current_user

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _get_alert_or_404(user_id: str, alert_id: str) -> dict:
    alert = db.fetch_one(
        """
        SELECT id, user_id, device_id, name, alert_type, metric, comparison, threshold, window_seconds,
               severity, is_enabled, cooldown_seconds, created_at, updated_at
        FROM alerts
        WHERE id=%s AND user_id=%s
        """,
        (alert_id, user_id),
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert


def _ensure_device_owned_if_set(user_id: str, device_id: Optional[str]) -> None:
    if not device_id:
        return
    owned = db.fetch_one("SELECT id FROM devices WHERE id=%s AND user_id=%s", (device_id, user_id))
    if not owned:
        raise HTTPException(status_code=404, detail="Device not found")


@router.get(
    "",
    response_model=list[AlertResponse],
    summary="List alerts",
    description="List all alerts for the current user.",
    operation_id="alerts_list",
)
def list_alerts(current_user: dict = Depends(get_current_user)) -> list[AlertResponse]:
    """List alerts for current user."""
    rows = db.fetch_all(
        """
        SELECT id, user_id, device_id, name, alert_type, metric, comparison, threshold, window_seconds,
               severity, is_enabled, cooldown_seconds, created_at, updated_at
        FROM alerts
        WHERE user_id=%s
        ORDER BY created_at DESC
        """,
        (current_user["id"],),
    )
    return [AlertResponse(**r) for r in rows]


@router.post(
    "",
    response_model=AlertResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create alert",
    description="Create an alert definition for the current user.",
    operation_id="alerts_create",
)
def create_alert(payload: AlertCreate, current_user: dict = Depends(get_current_user)) -> AlertResponse:
    """Create an alert."""
    user_id = str(current_user["id"])
    _ensure_device_owned_if_set(user_id, payload.device_id)

    existing = db.fetch_one("SELECT id FROM alerts WHERE user_id=%s AND name=%s", (user_id, payload.name))
    if existing:
        raise HTTPException(status_code=400, detail="Alert name already exists")

    row = db.execute_returning_one(
        """
        INSERT INTO alerts (
          user_id, device_id, name, alert_type, metric, comparison, threshold, window_seconds,
          severity, is_enabled, cooldown_seconds
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id, user_id, device_id, name, alert_type, metric, comparison, threshold, window_seconds,
                  severity, is_enabled, cooldown_seconds, created_at, updated_at
        """,
        (
            user_id,
            payload.device_id,
            payload.name,
            payload.alert_type,
            payload.metric,
            payload.comparison,
            payload.threshold,
            payload.window_seconds,
            payload.severity,
            payload.is_enabled,
            payload.cooldown_seconds,
        ),
    )
    return AlertResponse(**row)


@router.get(
    "/{alert_id}",
    response_model=AlertResponse,
    summary="Get alert",
    description="Get an alert by id.",
    operation_id="alerts_get",
)
def get_alert(alert_id: str, current_user: dict = Depends(get_current_user)) -> AlertResponse:
    """Get alert."""
    alert = _get_alert_or_404(str(current_user["id"]), alert_id)
    return AlertResponse(**alert)


@router.put(
    "/{alert_id}",
    response_model=AlertResponse,
    summary="Update alert",
    description="Update an alert definition.",
    operation_id="alerts_update",
)
def update_alert(alert_id: str, payload: AlertUpdate, current_user: dict = Depends(get_current_user)) -> AlertResponse:
    """Update alert definition."""
    user_id = str(current_user["id"])
    _get_alert_or_404(user_id, alert_id)

    fields = payload.model_dump(exclude_unset=True)
    if "device_id" in fields:
        _ensure_device_owned_if_set(user_id, fields["device_id"])

    if "name" in fields:
        existing = db.fetch_one(
            "SELECT id FROM alerts WHERE user_id=%s AND name=%s AND id<>%s",
            (user_id, fields["name"], alert_id),
        )
        if existing:
            raise HTTPException(status_code=400, detail="Alert name already exists")

    if not fields:
        return AlertResponse(**_get_alert_or_404(user_id, alert_id))

    set_clauses = []
    params = []
    for k, v in fields.items():
        set_clauses.append(f"{k}=%s")
        params.append(v)
    params.extend([alert_id, user_id])

    row = db.execute_returning_one(
        f"""
        UPDATE alerts
        SET {", ".join(set_clauses)}
        WHERE id=%s AND user_id=%s
        RETURNING id, user_id, device_id, name, alert_type, metric, comparison, threshold, window_seconds,
                  severity, is_enabled, cooldown_seconds, created_at, updated_at
        """,
        tuple(params),
    )
    return AlertResponse(**row)


@router.delete(
    "/{alert_id}",
    response_model=ApiMessage,
    summary="Delete alert",
    description="Delete an alert definition.",
    operation_id="alerts_delete",
)
def delete_alert(alert_id: str, current_user: dict = Depends(get_current_user)) -> ApiMessage:
    """Delete alert."""
    affected = db.execute("DELETE FROM alerts WHERE id=%s AND user_id=%s", (alert_id, current_user["id"]))
    if affected == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    return ApiMessage(message="Deleted")


@router.get(
    "/events",
    response_model=list[AlertEventResponse],
    summary="List alert events",
    description="List recent alert events for the current user.",
    operation_id="alert_events_list",
)
def list_events(
    device_id: Optional[str] = Query(None, description="Optional device filter."),
    alert_id: Optional[str] = Query(None, description="Optional alert filter."),
    limit: int = Query(200, ge=1, le=1000, description="Max events."),
    current_user: dict = Depends(get_current_user),
) -> list[AlertEventResponse]:
    """List alert events."""
    user_id = str(current_user["id"])
    where = ["user_id=%s"]
    params: list = [user_id]
    if device_id:
        where.append("device_id=%s")
        params.append(device_id)
    if alert_id:
        where.append("alert_id=%s")
        params.append(alert_id)

    rows = db.fetch_all(
        f"""
        SELECT id, user_id, alert_id, device_id, ts, status, message, metric_value,
               acknowledged_at, resolved_at, created_at
        FROM alert_events
        WHERE {" AND ".join(where)}
        ORDER BY ts DESC
        LIMIT %s
        """,
        tuple(params + [limit]),
    )
    return [AlertEventResponse(**r) for r in rows]


@router.post(
    "/events/{event_id}/ack",
    response_model=ApiMessage,
    summary="Acknowledge an alert event",
    description="Marks an alert event as acknowledged.",
    operation_id="alert_event_acknowledge",
)
def acknowledge_event(event_id: int, current_user: dict = Depends(get_current_user)) -> ApiMessage:
    """Acknowledge an event."""
    affected = db.execute(
        """
        UPDATE alert_events
        SET status='acknowledged', acknowledged_at=now()
        WHERE id=%s AND user_id=%s
        """,
        (event_id, current_user["id"]),
    )
    if affected == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    return ApiMessage(message="Acknowledged")


def _compare(value: float, op: str, threshold: float) -> bool:
    if op == "gt":
        return value > threshold
    if op == "gte":
        return value >= threshold
    if op == "lt":
        return value < threshold
    if op == "lte":
        return value <= threshold
    if op == "eq":
        return value == threshold
    if op == "neq":
        return value != threshold
    return False


@router.post(
    "/evaluate",
    response_model=ApiMessage,
    summary="Evaluate alerts",
    description="Evaluates enabled alerts against latest readings and inserts alert_events. Intended for polling/cron usage.",
    operation_id="alerts_evaluate",
)
def evaluate_alerts(current_user: dict = Depends(get_current_user)) -> ApiMessage:
    """
    Evaluate alerts.

    Current implementation:
    - threshold: compares latest metric value for the device (or each device if device_id is null)
    - offline: triggers if latest reading is older than window_seconds (default 900s)
    - anomaly: treated as threshold for now (simple implementation)
    """
    user_id = str(current_user["id"])
    alerts = db.fetch_all(
        """
        SELECT id, device_id, name, alert_type, metric, comparison, threshold, window_seconds,
               cooldown_seconds
        FROM alerts
        WHERE user_id=%s AND is_enabled=true
        """,
        (user_id,),
    )

    triggered_count = 0
    now = datetime.now(timezone.utc)

    for a in alerts:
        device_ids: list[str]
        if a["device_id"]:
            device_ids = [a["device_id"]]
        else:
            devices = db.fetch_all("SELECT id FROM devices WHERE user_id=%s AND is_active=true", (user_id,))
            device_ids = [str(d["id"]) for d in devices]

        for device_id in device_ids:
            # cooldown: skip if there is a recent triggered/suppressed event within cooldown
            recent = db.fetch_one(
                """
                SELECT ts
                FROM alert_events
                WHERE user_id=%s AND alert_id=%s AND device_id=%s AND status IN ('triggered','suppressed')
                ORDER BY ts DESC
                LIMIT 1
                """,
                (user_id, a["id"], device_id),
            )
            if recent:
                last_ts = recent["ts"]
                if last_ts and (now - last_ts) < timedelta(seconds=int(a["cooldown_seconds"] or 0)):
                    continue

            latest = db.fetch_one(
                """
                SELECT ts, power_w, voltage_v, current_a, energy_wh
                FROM energy_readings
                WHERE user_id=%s AND device_id=%s
                ORDER BY ts DESC
                LIMIT 1
                """,
                (user_id, device_id),
            )

            if a["alert_type"] == "offline":
                window = int(a["window_seconds"] or 900)
                if not latest or (now - latest["ts"]) > timedelta(seconds=window):
                    db.execute(
                        """
                        INSERT INTO alert_events (user_id, alert_id, device_id, status, message)
                        VALUES (%s,%s,%s,'triggered',%s)
                        """,
                        (user_id, a["id"], device_id, f"Device offline (no reading within {window}s)"),
                    )
                    triggered_count += 1
                continue

            # threshold / anomaly require metric value
            if not latest:
                continue
            metric = a["metric"]
            value = latest.get(metric)
            if value is None or a["threshold"] is None:
                continue
            if _compare(float(value), a["comparison"], float(a["threshold"])):
                db.execute(
                    """
                    INSERT INTO alert_events (user_id, alert_id, device_id, status, message, metric_value)
                    VALUES (%s,%s,%s,'triggered',%s,%s)
                    """,
                    (user_id, a["id"], device_id, f"{metric} {a['comparison']} {a['threshold']}", float(value)),
                )
                triggered_count += 1

    return ApiMessage(message=f"Evaluated alerts. Triggered {triggered_count} events.")
