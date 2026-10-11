import os
import sys
import tempfile

# Point the app at a throwaway SQLite DB *before* anything imports api.core.db,
# so tests never touch notifications.db or production Postgres.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["TEST_DATABASE_URL"] = f"sqlite:///{_tmp.name}"
os.environ.pop("POSTGRES_URL", None)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Never send real email or call real LLMs from tests, even if a test forgets to mock
os.environ["SENDER_EMAIL"] = ""
os.environ["SENDER_PASSWORD"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["OPENROUTER_API_KEY"] = ""

os.environ["APP_PASSCODE"] = ""  # tests that need the lock set it themselves
