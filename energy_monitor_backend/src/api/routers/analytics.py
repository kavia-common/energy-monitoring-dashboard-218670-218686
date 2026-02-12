from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api import db
from src.api.schemas import AnalyticsSummaryResponse, AnalyticsTimeseriesPoint, AnalyticsTimeseriesResponse, InsightResponse
from src.api.security import get_current_user

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _ensure_device_owned(user_id: str, device_id: str) -> None:
    owned = db.fetch_one("SELECT id FROM devices WHERE id=%s AND user_id=%s", (device_id, user_id))
    if not owned:
        raise HTTPException(status_code=404, detail="Device not found")


@router.get(
    "/devices/{device_id}/summary",
    response_model=AnalyticsSummaryResponse,
    summary="Summary statistics",
    description="Compute avg/min/max power and approximate energy delta over a time range.",
    operation_id="analytics_summary",
)
def summary(
    device_id: str,
    start: datetime = Query(..., description="Start timestamp."),
    end: datetime = Query(..., description="End timestamp."),
    current_user: dict = Depends(get_current_user),
) -> AnalyticsSummaryResponse:
    """Compute summary statistics for a device and time range."""
    user_id = str(current_user["id"])
    _ensure_device_owned(user_id, device_id)
    if end < start:
        raise HTTPException(status_code=400, detail="end must be >= start")

    row = db.fetch_one(
        """
        SELECT
          COUNT(*)::int AS points,
          AVG(power_w) AS avg_power_w,
          MAX(power_w) AS max_power_w,
          MIN(power_w) AS min_power_w,
          (MAX(energy_wh) - MIN(energy_wh)) AS energy_wh_delta
        FROM energy_readings
        WHERE user_id=%s AND device_id=%s AND ts >= %s AND ts <= %s
        """,
        (user_id, device_id, start, end),
    )
    row = row or {"points": 0, "avg_power_w": None, "max_power_w": None, "min_power_w": None, "energy_wh_delta": None}
    return AnalyticsSummaryResponse(device_id=device_id, start=start, end=end, **row)


@router.get(
    "/devices/{device_id}/timeseries",
    response_model=AnalyticsTimeseriesResponse,
    summary="Bucketed time series",
    description="Return bucketed aggregates over a range using PostgreSQL time bucketing via date_bin().",
    operation_id="analytics_timeseries",
)
def timeseries(
    device_id: str,
    start: datetime = Query(..., description="Start timestamp."),
    end: datetime = Query(..., description="End timestamp."),
    bucket_seconds: int = Query(300, ge=60, le=86400, description="Bucket size in seconds."),
    current_user: dict = Depends(get_current_user),
) -> AnalyticsTimeseriesResponse:
    """Return bucketed aggregates for charting."""
    user_id = str(current_user["id"])
    _ensure_device_owned(user_id, device_id)
    if end < start:
        raise HTTPException(status_code=400, detail="end must be >= start")

    rows = db.fetch_all(
        """
        SELECT
          date_bin(make_interval(secs => %s), ts, %s) AS bucket_start,
          COUNT(*)::int AS points,
          AVG(power_w) AS avg_power_w,
          MAX(power_w) AS max_power_w,
          MIN(power_w) AS min_power_w
        FROM energy_readings
        WHERE user_id=%s AND device_id=%s AND ts >= %s AND ts <= %s
        GROUP BY 1
        ORDER BY 1 ASC
        """,
        (bucket_seconds, start, user_id, device_id, start, end),
    )
    series = [AnalyticsTimeseriesPoint(**r) for r in rows]
    return AnalyticsTimeseriesResponse(device_id=device_id, start=start, end=end, bucket_seconds=bucket_seconds, series=series)


@router.get(
    "/devices/{device_id}/insights",
    response_model=InsightResponse,
    summary="Basic insights",
    description="Provides simple heuristic insights (peak usage, average usage) for a time range.",
    operation_id="analytics_insights",
)
def insights(
    device_id: str,
    start: datetime = Query(..., description="Start timestamp."),
    end: datetime = Query(..., description="End timestamp."),
    current_user: dict = Depends(get_current_user),
) -> InsightResponse:
    """Return basic human-readable insights for the range."""
    user_id = str(current_user["id"])
    _ensure_device_owned(user_id, device_id)
    if end < start:
        raise HTTPException(status_code=400, detail="end must be >= start")

    peak = db.fetch_one(
        """
        SELECT ts, power_w
        FROM energy_readings
        WHERE user_id=%s AND device_id=%s AND ts >= %s AND ts <= %s AND power_w IS NOT NULL
        ORDER BY power_w DESC NULLS LAST
        LIMIT 1
        """,
        (user_id, device_id, start, end),
    )
    avg = db.fetch_one(
        """
        SELECT AVG(power_w) AS avg_power_w, COUNT(*)::int AS points
        FROM energy_readings
        WHERE user_id=%s AND device_id=%s AND ts >= %s AND ts <= %s
        """,
        (user_id, device_id, start, end),
    )

    out: list[str] = []
    points = (avg or {}).get("points") or 0
    if points == 0:
        out.append("No readings available in the selected range.")
    else:
        avg_power = (avg or {}).get("avg_power_w")
        if avg_power is not None:
            out.append(f"Average power over the range: {avg_power:.1f} W.")
        if peak and peak.get("power_w") is not None:
            out.append(f"Peak power: {peak['power_w']:.1f} W at {peak['ts'].isoformat()}.")

    return InsightResponse(device_id=device_id, start=start, end=end, insights=out)
