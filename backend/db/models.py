from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True)
    ip_address = Column(String(45), nullable=False, index=True)
    mac_address = Column(String(17), nullable=True, unique=True)
    hostname = Column(String(255), nullable=True)
    vendor = Column(String(255), nullable=True)
    discovery_source = Column(String(64), nullable=True)
    first_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen = Column(DateTime, default=datetime.utcnow, nullable=False)
    metadata_ = Column("metadata", JSON, nullable=True)
    dns_events = relationship("DNSEvent", back_populates="device")

class DNSEvent(Base):
    __tablename__ = "dns_events"
    id = Column(Integer, primary_key=True)
    domain = Column(String(255), nullable=False, index=True)
    query_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    query_type = Column(String(16), nullable=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True, index=True)
    category = Column(String(64), nullable=True)
    blocked = Column(Integer, nullable=True)  # 1/0/None
    device = relationship("Device", back_populates="dns_events")