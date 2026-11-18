from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DeviceCreate(BaseModel):
    ip_address: str = Field(..., min_length=1)
    mac_address: Optional[str] = None
    hostname: Optional[str] = None
    vendor: Optional[str] = None
    discovery_source: Optional[str] = None
    metadata: Optional[dict] = None


class DeviceOut(BaseModel):
    id: int
    ip_address: str
    mac_address: Optional[str]
    hostname: Optional[str]
    vendor: Optional[str]
    discovery_source: Optional[str]
    first_seen: datetime
    last_seen: datetime
    is_current: bool = False
    network_subnet: Optional[str] = None
    last_scan_at: Optional[datetime] = None
    scan_status: Optional[str] = None
    metadata: Optional[dict] = Field(None, validation_alias="extra")

    class Config:
        from_attributes = True
