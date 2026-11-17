import os, tempfile
os.environ["NETRA_DB_PATH"] = os.path.join(tempfile.mkdtemp(), "benchtest.db")
from benchmarking.runner import percentile, measure, run_all

def test_percentile():
    assert percentile([1,2,3,4], 50) == 2.5

def test_measure():
    r = measure(lambda: None, iterations=3)
    assert r["iterations"] == 3
    assert r["errors"] == 0

def test_run_all():
    rep = run_all(2, 10)
    assert "results" in rep
    assert rep["dataset_size"] == 10