import os, tempfile
os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "ur.db")
from db.session import init_db
init_db()
from discovery.router.capabilities import detect_capabilities

def test_caps():
    c = detect_capabilities({})
    assert "local_discovery" in c
    assert c["local_discovery"] == "supported"