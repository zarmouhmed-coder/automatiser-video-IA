import os
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = tempfile.mkdtemp(prefix="mvs-test-")
os.environ["MVS_DATA_DIR"] = _TMP
# modèles de voix / traduction déjà téléchargés (évite ~600 Mo de téléchargement par test)
_MODELS = Path(__file__).resolve().parents[2] / "data" / "models"
if _MODELS.exists():
    os.environ["MVS_MODELS_DIR"] = str(_MODELS)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.core import update_settings

    with TestClient(app) as c:
        # rendu réduit pour accélérer les tests (les paramètres réels restent ceux de l'utilisateur)
        update_settings({"video_width": 360, "video_height": 640, "video_fps": 12, "preview_fps": 8,
                         "preview_scale": 0.5, "video_preset": "ultrafast", "validation_mode": "detailed"})
        yield c


def wait_idle(timeout=600):
    from app.workflow import queue
    assert queue.wait_idle(timeout), "la file d'attente n'est pas revenue au repos"
