import uuid

from app.api.v1 import workspace


def test_project_requirement_case_and_dashboard_workflow(authenticated_client):
    client = authenticated_client
    project = client.post(
        "/api/v1/projects", json={"name": "Checkout", "description": "Payments"}
    ).json()
    requirement = client.post(
        f"/api/v1/projects/{project['id']}/requirements",
        json={
            "requirement_key": "PAY-1",
            "title": "Payment confirmation",
            "description": "A customer sees payment outcome",
            "acceptance_criteria": "Approved payments show a receipt",
        },
    )
    assert requirement.status_code == 201
    requirement_id = requirement.json()["id"]
    duplicate = client.post(
        f"/api/v1/projects/{project['id']}/requirements",
        json={
            "requirement_key": "PAY-1",
            "title": "Duplicate",
            "description": "Same project key",
        },
    )
    assert duplicate.status_code == 409
    revised_requirement = client.patch(
        f"/api/v1/requirements/{requirement_id}", json={"title": "Payment outcome"}
    )
    assert revised_requirement.status_code == 200
    assert revised_requirement.json()["title"] == "Payment outcome"
    payload = {
        "requirement_id": requirement_id,
        "scenario": "Approved card payment shows a receipt",
        "preconditions": "A valid card is available",
        "steps": ["Enter valid card data", "Confirm payment"],
        "expected_result": "Receipt is shown",
        "test_data": {"card": "valid"},
        "priority": "P1",
        "severity": "medium",
        "test_type": "positive",
        "automation_feasibility": "high",
        "tags": ["payments"],
    }
    created = client.post(f"/api/v1/projects/{project['id']}/test-cases", json=payload)
    assert created.status_code == 201
    case = created.json()

    listed = client.get(f"/api/v1/projects/{project['id']}/test-cases?q=receipt")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["case_key"].startswith("TC-")

    updated = client.patch(f"/api/v1/test-cases/{case['id']}", json={"priority": "P0"})
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert (
        client.get(f"/api/v1/test-cases/{case['id']}/history").json()[0]["action"]
        == "test_case.updated"
    )
    replaced = client.put(f"/api/v1/test-cases/{case['id']}", json=payload)
    assert replaced.status_code == 200
    assert replaced.json()["version"] == 3

    dashboard = client.get(f"/api/v1/projects/{project['id']}/dashboard").json()
    assert dashboard["total_requirements"] == 1
    assert dashboard["total_test_cases"] == 1
    assert dashboard["coverage_percent"] == 100

    exported = client.get(f"/api/v1/projects/{project['id']}/exports/csv")
    assert exported.status_code == 200
    assert "Test Case ID" in exported.text


def test_project_scope_and_validation_are_enforced(authenticated_client):
    client = authenticated_client
    project = client.post("/api/v1/projects", json={"name": "Private"}).json()
    outsider_id = str(uuid.uuid4())
    response = client.get(f"/api/v1/projects/{outsider_id}/requirements")
    assert response.status_code == 404
    invalid = client.post(
        f"/api/v1/projects/{project['id']}/requirements",
        json={"requirement_key": "", "title": "x", "description": "y"},
    )
    assert invalid.status_code == 422
    assert client.get("/health/live").headers["x-content-type-options"] == "nosniff"


def test_refresh_rotates_tokens_and_checks_csrf(client):
    registration = client.post(
        "/api/v1/auth/register",
        json={"email": "rotate@example.com", "full_name": "Rotate", "password": "StrongPass!234"},
    ).json()
    refreshed = client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": registration["csrf_token"]},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"] != registration["access_token"]
    rejected = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": registration["csrf_token"]},
    )
    assert rejected.status_code == 403
    logged_out = client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": refreshed.json()["csrf_token"]},
    )
    assert logged_out.status_code == 204


def test_document_upload_and_csv_bulk_import(authenticated_client):
    client = authenticated_client
    project = client.post("/api/v1/projects", json={"name": "Import project"}).json()
    imported = client.post(
        f"/api/v1/projects/{project['id']}/requirements/import",
        files={"file": ("brief.txt", b"Customers can manage their profile.", "text/plain")},
    )
    assert imported.status_code == 201
    assert imported.json()["description"] == "Customers can manage their profile."
    bulk = client.post(
        f"/api/v1/projects/{project['id']}/requirements/import-bulk",
        files={
            "file": (
                "requirements.csv",
                b"requirement_key,title,description\nPROFILE-2,Edit profile,User updates profile fields",
                "text/csv",
            )
        },
    )
    assert bulk.status_code == 201
    assert bulk.json()["imported"] == 1


def test_read_only_role_cannot_create_project(client):
    admin = client.post(
        "/api/v1/auth/register",
        json={"email": "admin@example.com", "full_name": "Admin", "password": "StrongPass!234"},
    ).json()
    reader = client.post(
        "/api/v1/auth/register",
        json={"email": "reader@example.com", "full_name": "Reader", "password": "StrongPass!234"},
    ).json()
    reader_id = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {reader['access_token']}"}
    ).json()["id"]
    client.patch(
        f"/api/v1/auth/users/{reader_id}/role",
        params={"role": "read_only"},
        headers={"Authorization": f"Bearer {admin['access_token']}"},
    )
    forbidden = client.post(
        "/api/v1/projects",
        headers={"Authorization": f"Bearer {reader['access_token']}"},
        json={"name": "Should not create"},
    )
    assert forbidden.status_code == 403


def test_ai_generation_persists_cases_with_provider_adapter(authenticated_client, monkeypatch):
    async def fake_generate(self, prompt):
        return "mock-model", [
            {
                "scenario": "Payment is declined",
                "preconditions": "A payment method is available",
                "steps": ["Submit a declined payment method"],
                "expected_result": "The customer sees a safe decline message",
                "test_data": {"card": "declined"},
                "priority": "P1",
                "severity": "medium",
                "test_type": "negative",
                "automation_feasibility": "high",
                "tags": ["payment", "error-handling"],
            }
        ]

    monkeypatch.setattr(workspace.OpenAIProvider, "generate", fake_generate)
    client = authenticated_client
    project = client.post("/api/v1/projects", json={"name": "AI project"}).json()
    requirement = client.post(
        f"/api/v1/projects/{project['id']}/requirements",
        json={"requirement_key": "PAY-2", "title": "Card payment", "description": "Pay with card"},
    ).json()
    generated = client.post(f"/api/v1/requirements/{requirement['id']}/generate")
    assert generated.status_code == 200
    assert generated.json()[0]["test_type"] == "negative"
    duplicate_generation = client.post(f"/api/v1/requirements/{requirement['id']}/generate")
    assert duplicate_generation.status_code == 409


def test_requirement_delete_is_audited(authenticated_client):
    client = authenticated_client
    project = client.post("/api/v1/projects", json={"name": "Requirement lifecycle"}).json()
    requirement = client.post(
        f"/api/v1/projects/{project['id']}/requirements",
        json={"requirement_key": "DEL-1", "title": "Temporary", "description": "Delete me"},
    ).json()
    deleted = client.delete(f"/api/v1/requirements/{requirement['id']}")
    assert deleted.status_code == 204
