import os
import sys
import tempfile

# Point the app at a throwaway SQLite DB *before* anything imports api.core.db,
# so tests never touch notifications.db or production Postgres.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ.pop("POSTGRES_URL", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
