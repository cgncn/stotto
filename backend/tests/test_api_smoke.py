"""
API smoke tests using TestClient (no real DB needed — uses in-memory SQLite).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.db.base import Base, get_db

# ── In-memory SQLite for tests ─────────────────────────────────────────────────
TEST_DB_URL = "sqlite:///./test.db"

engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_current_pool_empty(client):
    r = client.get("/weekly-pools/current")
    assert r.status_code == 404


def test_pool_not_found(client):
    r = client.get("/weekly-pools/9999")
    assert r.status_code == 404


def test_login_wrong_credentials(client):
    r = client.post("/auth/login", json={"email": "x@x.com", "password": "wrong"})
    assert r.status_code == 401


def test_admin_without_token(client):
    r = client.post("/admin/recompute-week/1")
    assert r.status_code == 403


def test_coupon_scenarios_empty_pool(client):
    r = client.get("/weekly-pools/1/coupon-scenarios")
    assert r.status_code == 404
