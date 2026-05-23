def test_audit_logs_require_admin(client, auth_token):
    response = client.get("/api/audit", headers={"Authorization": f"Bearer {auth_token}"})
    assert response.status_code == 403


def test_audit_logs_admin_access(client, admin_token):
    response = client.get("/api/audit", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "logs" in data


def test_audit_metrics(client, admin_token):
    response = client.get("/api/audit/metrics", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200


def test_audit_export_csv(client, admin_token):
    response = client.get("/api/audit/export", headers={"Authorization": f"Bearer {admin_token}"})
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
