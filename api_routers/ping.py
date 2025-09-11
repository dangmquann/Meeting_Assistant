from fastapi import APIRouter, Depends
from typing import Dict
import os
from dependencies import get_services_health
from schemas.health import HealthResponse, ServiceStatus

router = APIRouter()

@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check(services: Dict = Depends(get_services_health)) -> HealthResponse:
    """Check service health status."""
    
    # Determine overall status (ok if all critical services are healthy)
    overall_status = "ok"
    for service_name, service in services.items():
        if service_name in ["mongodb", "database"] and service["status"] != "healthy":
            overall_status = "degraded"
    
    return HealthResponse(
        status=overall_status,
        version=os.getenv("APP_VERSION", "0.1.0"),
        environment=os.getenv("ENVIRONMENT", "development"),
        service_name="meeting-assistant",
        services=services
    )