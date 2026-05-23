import os
import pytest
from fastapi.testclient import TestClient

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.base import Base
from db.init_data import init_users, init_knowledge
from app.main import app
from app.dependencies import get_db
from db import session as db_session

# Use an in-memory database for tests (StaticPool so all connections share it)
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Monkeypatch db.session so that lifespan also uses the in-memory engine
db_session.engine = engine
db_session.SessionLocal = TestingSessionLocal

# Monkeypatch db.init_data.engine as well (module-level import)
import db.init_data as db_init_data
db_init_data.engine = engine


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


from api import auth as auth_api


@pytest.fixture(scope="function")
def client():
    auth_api._login_attempts.clear()

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    init_users(db)
    init_knowledge(db)
    db.close()

    with TestClient(app) as c:
        yield c

    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def auth_token(client):
    response = client.post("/api/login", json={"username": "alice", "password": "student123"})
    assert response.status_code == 200
    return response.json()["token"]


@pytest.fixture
def admin_token(client):
    response = client.post("/api/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    return response.json()["token"]
