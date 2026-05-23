def test_login_success(client):
    response = client.post("/api/login", json={"username": "alice", "password": "student123"})
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["user"]["role"] == "student"


def test_login_failure(client):
    response = client.post("/api/login", json={"username": "alice", "password": "wrong"})
    assert response.status_code == 401


def test_me_endpoint(client, auth_token):
    response = client.get("/api/me", headers={"Authorization": f"Bearer {auth_token}"})
    assert response.status_code == 200
    assert response.json()["user"]["username"] == "alice"


def test_me_unauthorized(client):
    response = client.get("/api/me")
    assert response.status_code == 401
