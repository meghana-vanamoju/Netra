import os

DEFAULT_DB_PATH = os.path.join(os.getcwd(), "netra.db")

def get_database_url() -> str:
    path = os.environ.get("NETRA_DB_PATH", DEFAULT_DB_PATH)
    return f"sqlite:///{path}"
