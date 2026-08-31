import os
import tempfile
from pathlib import Path

TEST_ROOT = Path(tempfile.mkdtemp(prefix="fincontract-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test.db'}"
os.environ["CHROMA_MODE"] = "persistent"
os.environ["CHROMA_PATH"] = str(TEST_ROOT / "chroma")
os.environ["UPLOAD_DIR"] = str(TEST_ROOT / "uploads")
os.environ["REPORT_DIR"] = str(TEST_ROOT / "reports")
os.environ["USE_REDIS"] = "false"
os.environ["DOCUMENT_ENCRYPTION_KEY"] = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
os.environ["ADMIN_AUDIT_TOKEN"] = "test-admin-token"
