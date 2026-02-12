from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ApiMessage(BaseModel):
    message: str = Field(..., description="Human-readable message.")


# -------------------------
# Auth
# -------------------------
class RegisterRequest(BaseModel):
    email: str = Field(..., description="User email address.")
    password: str = Field(..., min_length=8, description="User password (min 8 chars).")
    full_name: Optional[str] = Field(None, description="Optional user full name.")


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address.")
    password: str = Field(..., description="User password.")


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token.")
    token_type: str = Field("bearer", description="Token type.")


class UserMeResponse(BaseModel):
    id: str = Field(..., description="User ID (uuid).")
    email: str = Field(..., description="User email.")
    full_name: Optional[str] = Field(None, description="Full name.")
    is_active: bool = Field(..., description="Whether user is active.")
    created_at: datetime = Field(..., description="Created timestamp.")
    updated_at: datetime = Field(..., description="Updated timestamp.")
    last_login_at: Optional[datetime] = Field(None, description="Last login timestamp.")


# -------------------------
# Devices
# -------------------------
class DeviceBase(BaseModel):
    name: str = Field(..., description="Device display name (unique per user).")
    location: Optional[str] = Field(None, description="Optional location label.")
    model: Optional[str] = Field(None, description="Device model.")
    manufacturer: Optional[str] = Field(None, description="Device manufacturer.")
    serial_number: Optional[str] = Field(None, description="Device serial number.")
    external_device_id: Optional[str] = Field(None, description="External/system device id.")
    timezone: str = Field("UTC", description="IANA timezone, e.g., 'UTC'.")


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Device display name.")
    location: Optional[str] = Field(None, description="Optional location label.")
    model: Optional[str] = Field(None, description="Device model.")
    manufacturer: Optional[str] = Field(None, description="Device manufacturer.")
    serial_number: Optional[str] = Field(None, description="Device serial number.")
    external_device_id: Optional[str] = Field(None, description="External/system device id.")
    timezone: Optional[str] = Field(None, description="IANA timezone.")
    is_active: Optional[bool] = Field(None, description="Device active flag.")


class DeviceResponse(DeviceBase):
    id: str = Field(..., description="Device ID (uuid).")
    is_active: bool = Field(..., description="Device active flag.")
    created_at: datetime = Field(..., description="Created timestamp.")
    updated_at: datetime = Field(..., description="Updated timestamp.")


# -------------------------
# Energy Readings
# -------------------------
class EnergyReadingIngest(BaseModel):
    ts: datetime = Field(..., description="Timestamp of the reading (UTC recommended).")
    power_w: Optional[float] = Field(None, ge=0, description="Instantaneous power in watts.")
    voltage_v: Optional[float] = Field(None, ge=0, description="Voltage in volts.")
    current_a: Optional[float] = Field(None, ge=0, description="Current in amps.")
    energy_wh: Optional[float] = Field(None, ge=0, description="Energy in watt-hours (cumulative or interval).")
    source: str = Field("device", description="Source string, e.g. 'device' | 'manual'.")


class EnergyReadingResponse(EnergyReadingIngest):
    id: int = Field(..., description="Reading ID.")
    device_id: str = Field(..., description="Device ID.")
    created_at: datetime = Field(..., description="Created timestamp.")


class EnergyLatestResponse(BaseModel):
    device_id: str = Field(..., description="Device ID.")
    ts: Optional[datetime] = Field(None, description="Timestamp of latest reading (null if none).")
    power_w: Optional[float] = Field(None, description="Latest power (W).")
    voltage_v: Optional[float] = Field(None, description="Latest voltage (V).")
    current_a: Optional[float] = Field(None, description="Latest current (A).")
    energy_wh: Optional[float] = Field(None, description="Latest energy (Wh).")
    source: Optional[str] = Field(None, description="Reading source.")


class EnergyQueryResponse(BaseModel):
    device_id: str = Field(..., description="Device ID.")
    start: datetime = Field(..., description="Query start.")
    end: datetime = Field(..., description="Query end.")
    readings: list[EnergyReadingResponse] = Field(..., description="Readings ordered by time.")


# -------------------------
# Analytics
# -------------------------
class AnalyticsSummaryResponse(BaseModel):
    device_id: str = Field(..., description="Device ID.")
    start: datetime = Field(..., description="Start time.")
    end: datetime = Field(..., description="End time.")
    points: int = Field(..., description="Number of data points used.")
    avg_power_w: Optional[float] = Field(None, description="Average power (W) across points.")
    max_power_w: Optional[float] = Field(None, description="Max power (W) across points.")
    min_power_w: Optional[float] = Field(None, description="Min power (W) across points.")
    energy_wh_delta: Optional[float] = Field(
        None, description="Approx delta in energy_wh over the range if available (max - min)."
    )


class AnalyticsTimeseriesPoint(BaseModel):
    bucket_start: datetime = Field(..., description="Bucket start timestamp.")
    avg_power_w: Optional[float] = Field(None, description="Average power in bucket.")
    max_power_w: Optional[float] = Field(None, description="Max power in bucket.")
    min_power_w: Optional[float] = Field(None, description="Min power in bucket.")
    points: int = Field(..., description="Points in bucket.")


class AnalyticsTimeseriesResponse(BaseModel):
    device_id: str = Field(..., description="Device ID.")
    start: datetime = Field(..., description="Start time.")
    end: datetime = Field(..., description="End time.")
    bucket_seconds: int = Field(..., description="Bucket size in seconds.")
    series: list[AnalyticsTimeseriesPoint] = Field(..., description="Bucketed series.")


class InsightResponse(BaseModel):
    device_id: str = Field(..., description="Device ID.")
    start: datetime = Field(..., description="Start time.")
    end: datetime = Field(..., description="End time.")
    insights: list[str] = Field(..., description="Human-readable insights.")


# -------------------------
# Alerts
# -------------------------
AlertType = Literal["threshold", "anomaly", "offline"]
AlertComparison = Literal["gt", "gte", "lt", "lte", "eq", "neq"]
AlertSeverity = Literal["low", "medium", "high", "critical"]


class AlertBase(BaseModel):
    name: str = Field(..., description="Alert name (unique per user).")
    alert_type: AlertType = Field(..., description="Alert type.")
    device_id: Optional[str] = Field(None, description="Optional device scope (null means all devices).")
    metric: str = Field("power_w", description="Metric name, e.g. power_w.")
    comparison: AlertComparison = Field("gt", description="Comparison operator.")
    threshold: Optional[float] = Field(None, description="Threshold for threshold/anomaly alerts.")
    window_seconds: Optional[int] = Field(None, ge=1, description="Optional evaluation window in seconds.")
    severity: AlertSeverity = Field("medium", description="Severity.")
    is_enabled: bool = Field(True, description="Whether alert is enabled.")
    cooldown_seconds: int = Field(300, ge=0, description="Cooldown to suppress repeated triggers.")


class AlertCreate(AlertBase):
    pass


class AlertUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Alert name.")
    alert_type: Optional[AlertType] = Field(None, description="Alert type.")
    device_id: Optional[str] = Field(None, description="Device scope (explicit null clears).")
    metric: Optional[str] = Field(None, description="Metric.")
    comparison: Optional[AlertComparison] = Field(None, description="Comparison.")
    threshold: Optional[float] = Field(None, description="Threshold.")
    window_seconds: Optional[int] = Field(None, ge=1, description="Window seconds.")
    severity: Optional[AlertSeverity] = Field(None, description="Severity.")
    is_enabled: Optional[bool] = Field(None, description="Enable/disable.")
    cooldown_seconds: Optional[int] = Field(None, ge=0, description="Cooldown seconds.")


class AlertResponse(AlertBase):
    id: str = Field(..., description="Alert ID (uuid).")
    user_id: str = Field(..., description="User ID.")
    created_at: datetime = Field(..., description="Created timestamp.")
    updated_at: datetime = Field(..., description="Updated timestamp.")


class AlertEventResponse(BaseModel):
    id: int = Field(..., description="Event ID.")
    user_id: str = Field(..., description="User ID.")
    alert_id: str = Field(..., description="Alert ID.")
    device_id: Optional[str] = Field(None, description="Device ID.")
    ts: datetime = Field(..., description="Event time.")
    status: Literal["triggered", "acknowledged", "resolved", "suppressed"] = Field(..., description="Event status.")
    message: Optional[str] = Field(None, description="Message.")
    metric_value: Optional[float] = Field(None, description="Observed metric value.")
    acknowledged_at: Optional[datetime] = Field(None, description="Acknowledged time.")
    resolved_at: Optional[datetime] = Field(None, description="Resolved time.")
    created_at: datetime = Field(..., description="Created timestamp.")
