from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers import alerts, analytics, auth, devices, energy

openapi_tags = [
    {"name": "health", "description": "Service health and diagnostics."},
    {"name": "auth", "description": "Authentication (register/login/me)."},
    {"name": "devices", "description": "Device CRUD for the authenticated user."},
    {"name": "energy", "description": "Energy ingestion and queries (latest and historical ranges)."},
    {"name": "analytics", "description": "Aggregations and insights over energy data."},
    {"name": "alerts", "description": "Alert CRUD and evaluation/event history."},
]

app = FastAPI(
    title="Energy Monitor Backend API",
    description=(
        "Backend APIs for energy monitoring dashboard: auth, device management, energy ingestion/querying, "
        "analytics, and alerting.\n\n"
        "Auth uses Bearer JWT. Provide `Authorization: Bearer <token>` for protected endpoints."
    ),
    version="1.0.0",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["health"], summary="Health check", operation_id="health_check")
def health_check():
    """Health check endpoint."""
    return {"message": "Healthy"}


# Mount routers
app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(energy.router)
app.include_router(analytics.router)
app.include_router(alerts.router)
