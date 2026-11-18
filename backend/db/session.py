from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from .config import get_database_url

_engine = None
_SessionLocal = None

# Additive columns for real provider provenance. Existing databases are upgraded
# in place; no stored DNS events are deleted or rewritten.
_DNS_EVENT_COLUMNS = {
    "source": "VARCHAR(32)",
    "source_event_id": "VARCHAR(64)",
    "client": "VARCHAR(255)",
    "client_name": "VARCHAR(255)",
    "reason": "VARCHAR(128)",
    "rules_json": "JSON",
    "upstream": "VARCHAR(512)",
    "confidence": "VARCHAR(32)",
    "association_status": "VARCHAR(16)",
}

_DEVICE_CURRENT_COLUMNS = {
    "is_current": "BOOLEAN NOT NULL DEFAULT 0",
    "network_subnet": "VARCHAR(64)",
    "last_scan_at": "DATETIME",
    "scan_status": "VARCHAR(16)",
}

_AUDIT_REPORT_COLUMNS = {
    "network_subnet": "VARCHAR(64)",
}

_POLICY_COLUMNS = {
    "config_json": "JSON",
}


def get_engine():
    global _engine
    if _engine is None:
        url = get_database_url()
        _engine = create_engine(
            url,
            connect_args={"check_same_thread": False}
            if url.startswith("sqlite")
            else {},
        )
    return _engine


def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=get_engine()
        )
    return _SessionLocal


def get_db():
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


def _upgrade_schema():
    engine = get_engine()
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    if "devices" in table_names:
        existing_devices = {
            column["name"] for column in inspector.get_columns("devices")
        }
        with engine.begin() as connection:
            for name, column_type in _DEVICE_CURRENT_COLUMNS.items():
                if name not in existing_devices:
                    connection.execute(
                        text(f"ALTER TABLE devices ADD COLUMN {name} {column_type}")
                    )
            if engine.dialect.name == "sqlite":
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_devices_is_current "
                        "ON devices(is_current)"
                    )
                )

    if "audit_reports" in table_names:
        existing_audits = {
            column["name"] for column in inspector.get_columns("audit_reports")
        }
        with engine.begin() as connection:
            for name, column_type in _AUDIT_REPORT_COLUMNS.items():
                if name not in existing_audits:
                    connection.execute(
                        text(f"ALTER TABLE audit_reports ADD COLUMN {name} {column_type}")
                    )

    if "policies" in table_names:
        existing_policies = {
            column["name"] for column in inspector.get_columns("policies")
        }
        with engine.begin() as connection:
            for name, column_type in _POLICY_COLUMNS.items():
                if name not in existing_policies:
                    connection.execute(
                        text(f"ALTER TABLE policies ADD COLUMN {name} {column_type}")
                    )

    if "dns_events" not in table_names:
        return
    existing = {column["name"] for column in inspector.get_columns("dns_events")}
    with engine.begin() as connection:
        for name, column_type in _DNS_EVENT_COLUMNS.items():
            if name not in existing:
                connection.execute(
                    text(f"ALTER TABLE dns_events ADD COLUMN {name} {column_type}")
                )
        if engine.dialect.name == "sqlite":
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_dns_event_source_id "
                    "ON dns_events(source, source_event_id) "
                    "WHERE source IS NOT NULL AND source_event_id IS NOT NULL"
                )
            )


def _backfill_audit_network_subnets():
    from .models import AuditReport

    db = get_session_factory()()
    try:
        reports = (
            db.query(AuditReport)
            .filter(AuditReport.network_subnet.is_(None))
            .all()
        )
        changed = False
        for report in reports:
            summary = report.summary_json
            if not isinstance(summary, dict):
                continue
            subnet = summary.get("network_subnet")
            if isinstance(subnet, str) and subnet.strip():
                report.network_subnet = subnet.strip()
                changed = True
        if changed:
            db.commit()
    finally:
        db.close()


def init_db():
    from .models import Base

    Base.metadata.create_all(bind=get_engine())
    _upgrade_schema()
    _backfill_audit_network_subnets()
