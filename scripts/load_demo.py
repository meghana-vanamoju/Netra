import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault(
    "NETRA_DB_PATH",
    os.path.join(os.path.dirname(__file__), "..", "backend", "netra_demo.db"),
)
from db.models import Device, DNSEvent
from db.session import get_session_factory, init_db

init_db()
db = get_session_factory()()
if db.query(Device).count() == 0:
    db.add(
        Device(
            ip_address="192.168.1.10",
            hostname="demo-phone",
            vendor="DemoVendor",
            discovery_source="synthetic-demo",
        )
    )
    db.commit()
if db.query(DNSEvent).count() == 0:
    db.add(
        DNSEvent(
            domain="ads.example.com",
            category="Advertising",
            device_id=1,
            source="synthetic-demo",
            confidence="none",
        )
    )
    db.commit()
print("demo loaded (synthetic data)")
