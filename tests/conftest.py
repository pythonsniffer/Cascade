import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# isolated config + db per test session, so tests never touch the dev instance
_TMP = tempfile.mkdtemp(prefix="cascade-test-")
os.environ["CASCADE_CONFIG_DIR"] = str(Path(_TMP) / "config")
os.environ["CASCADE_DATA_DIR"] = str(Path(_TMP) / "data")
os.environ["CASCADE_DATABASE_URL"] = f"sqlite:///{Path(_TMP) / 'test.db'}"


@pytest.fixture(scope="session")
def app_state():
    from backend.api.state import state
    state.boot()
    return state


@pytest.fixture(scope="session")
def client(app_state):
    from fastapi.testclient import TestClient
    from backend.main import app
    # lifespan would re-boot; state is already booted and boot() is idempotent enough
    with TestClient(app) as c:
        yield c


class FakeBox:
    """Stands in for one ultralytics Boxes row.

    xyxy must be tensor-like (i.e. expose .tolist()), matching what ultralytics
    actually returns — otherwise the double passes where the real detector fails.
    """
    def __init__(self, cls, conf, xyxy):
        import numpy as np
        self.cls = cls
        self.conf = conf
        self.xyxy = np.array([xyxy], dtype=float)


class FakeResult:
    def __init__(self, boxes):
        self.boxes = boxes


class FakeYOLO:
    """Test double for the fine-tuned detector.

    Used ONLY to exercise the defect code path in tests. The running application
    never substitutes this for the real detector — with no best.pt it emits nothing.
    """
    def __init__(self, per_image):
        self.per_image = per_image
        self.calls = 0

    def predict(self, path, **kw):
        self.calls += 1
        return [FakeResult(self.per_image)]
