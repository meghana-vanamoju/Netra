from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship

from sqlalchemy import Boolean

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
    is_current = Column(Boolean, nullable=False, default=False, index=True)
    network_subnet = Column(String(64), nullable=True, index=True)
    last_scan_at = Column(DateTime, nullable=True)
    scan_status = Column(String(16), nullable=True)
    extra = Column("metadata", JSON, nullable=True)
    dns_events = relationship("DNSEvent", back_populates="device")


class DNSEvent(Base):
    __tablename__ = "dns_events"
    id = Column(Integer, primary_key=True)
    domain = Column(String(255), nullable=False, index=True)
    query_timestamp = Column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )
    query_type = Column(String(16), nullable=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True, index=True)
    category = Column(String(64), nullable=True)
    blocked = Column(Integer, nullable=True)  # 1/0/None
    # Real-provider provenance and dedup fields. All nullable so legacy rows and
    # synthetic demo events remain valid.
    source = Column(String(32), nullable=True, index=True)
    source_event_id = Column(String(64), nullable=True)
    client = Column(String(255), nullable=True)
    client_name = Column(String(255), nullable=True)
    reason = Column(String(128), nullable=True)
    rules_json = Column(JSON, nullable=True)
    upstream = Column(String(512), nullable=True)
    confidence = Column(String(32), nullable=True)
    association_status = Column(String(16), nullable=True)
    device = relationship("Device", back_populates="dns_events")


class DeviceObservation(Base):
    __tablename__ = "device_observations"
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    ip_address = Column(String(45), nullable=False, index=True)
    mac_address = Column(String(17), nullable=True, index=True)
    network_subnet = Column(String(64), nullable=True, index=True)
    observed_at = Column(DateTime, nullable=False, index=True)
    source = Column(String(64), nullable=True)


class AuditReport(Base):
    __tablename__ = "audit_reports"
    id = Column(Integer, primary_key=True)
    scope = Column(String(64), nullable=False)  # network or device
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    network_subnet = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    findings_json = Column(JSON, nullable=True)
    summary_json = Column(JSON, nullable=True)


class Policy(Base):
    __tablename__ = "policies"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    description = Column(String(512), nullable=True)
    target = Column(String(255), nullable=True)
    action = Column(String(64), nullable=False)
    risk = Column(String(16), nullable=False)
    reversible = Column(Integer, nullable=False, default=1)
    status = Column(String(32), nullable=False, default="proposed")
    config_json = Column(JSON, nullable=True)
    dry_run_plan_id = Column(Integer, ForeignKey("dry_run_plans.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    approver = Column(String(128), nullable=True)


class DryRunPlan(Base):
    __tablename__ = "dry_run_plans"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    plan_json = Column(JSON, nullable=True)
    impact_json = Column(JSON, nullable=True)


class PolicyExecution(Base):
    __tablename__ = "policy_executions"
    id = Column(Integer, primary_key=True)
    policy_id = Column(Integer, ForeignKey("policies.id"), nullable=False)
    status = Column(String(32), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    details = Column(JSON, nullable=True)


class ConfigSnapshot(Base):
    __tablename__ = "config_snapshots"
    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    backend = Column(String(64), nullable=True)
    state_json = Column(JSON, nullable=True)
    checksum = Column(String(128), nullable=True)
    policy_id = Column(Integer, ForeignKey("policies.id"), nullable=True)
