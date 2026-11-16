import os
import tempfile
import pytest
from sqlalchemy import inspect

os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.db")

from db import session, models

def test_init_and_session():
    session.init_db()
    db = session.get_session_factory()()
    try:
        d = models.Device(ip_address="192.168.1.2", hostname="test")
        db.add(d)
        db.commit()
        db.refresh(d)
        assert d.id is not None
        e = models.DNSEvent(domain="example.com", device_id=d.id)
        db.add(e)
        db.commit()
        assert db.query(models.DNSEvent).count() == 1
    finally:
        db.close()

def test_tables():
    insp = inspect(session.get_engine())
    assert "devices" in insp.get_table_names()
    assert "dns_events" in insp.get_table_names()