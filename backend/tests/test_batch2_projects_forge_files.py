"""Batch 2 tests: Projects CRUD & task binding, FORGE editor save + AEGIS re-scan, and File Hub attach."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_project_edit_archive_delete_and_task_binding(client: TestClient, auth_headers: dict) -> None:
    # Create project
    created = client.post(
        "/api/v1/projects",
        headers=auth_headers["owner"],
        json={
            "name": "ULTRON Core v2",
            "description": "Batch 2 operational project",
            "repo_full_name": "epejuwon-sketch/ULTRON",
            "default_branch": "main",
            "budget_usd": 250.0,
        },
    )
    assert created.status_code == 201
    pid = created.json()["project_id"]

    # Update & archive project
    updated = client.patch(
        f"/api/v1/projects/{pid}",
        headers=auth_headers["owner"],
        json={
            "name": "ULTRON Core v2.1",
            "status": "PAUSED",
            "budget_usd": 500.0,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "ULTRON Core v2.1"
    assert updated.json()["status"] == "PAUSED"
    assert updated.json()["budget_usd"] == 500.0

    # Bind a task to the project
    task_res = client.post(
        "/api/v1/tasks",
        headers=auth_headers["owner"],
        json={
            "title": "Audit project auth",
            "objective": "Verify RBAC and tenant isolation on project endpoints",
            "preferred_agent_id": "AGT-20",
            "project_id": pid,
        },
    )
    assert task_res.status_code == 201
    assert task_res.json()["project_id"] == pid

    # Filter tasks by project_id
    listed_tasks = client.get(f"/api/v1/tasks?project_id={pid}", headers=auth_headers["owner"])
    assert listed_tasks.status_code == 200
    assert any(t["task_id"] == task_res.json()["task_id"] for t in listed_tasks.json()["tasks"])

    # RBAC isolation: viewer cannot update
    viewer_patch = client.patch(
        f"/api/v1/projects/{pid}",
        headers=auth_headers["viewer"],
        json={"name": "Unauthorized"},
    )
    assert viewer_patch.status_code == 403

    # Delete project
    deleted = client.delete(f"/api/v1/projects/{pid}", headers=auth_headers["owner"])
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


def test_forge_editor_save_aegis_rescan_and_file_project_attach(
    client: TestClient, auth_headers: dict
) -> None:
    # Create project for file attachment
    proj = client.post(
        "/api/v1/projects",
        headers=auth_headers["owner"],
        json={"name": "File Attach Target", "repo_full_name": "epejuwon-sketch/ULTRON"},
    )
    assert proj.status_code == 201
    pid = proj.json()["project_id"]

    # Generate file and attach/detach to project
    gen_file = client.post(
        "/api/v1/files/generate",
        headers=auth_headers["owner"],
        json={"filename": "spec.md", "content": "# Spec\nInitial content", "mime_type": "text/markdown"},
    )
    assert gen_file.status_code == 201
    fid = gen_file.json()["file_id"]

    attached = client.patch(
        f"/api/v1/files/{fid}",
        headers=auth_headers["owner"],
        json={"project_id": pid, "folder": "specs"},
    )
    assert attached.status_code == 200
    assert attached.json()["project_id"] == pid
    assert attached.json()["folder"] == "specs"

    proj_files = client.get(f"/api/v1/files?project_id={pid}", headers=auth_headers["owner"])
    assert proj_files.status_code == 200
    assert len(proj_files.json()["files"]) == 1

    detached = client.patch(
        f"/api/v1/files/{fid}",
        headers=auth_headers["owner"],
        json={"clear_project": True},
    )
    assert detached.status_code == 200
    assert detached.json()["project_id"] is None

    # FORGE generate + edit + AEGIS re-scan
    forge = client.post(
        "/api/v1/forge/projects",
        headers=auth_headers["owner"],
        json={
            "name": "Telemetry Micro App",
            "template": "web_app",
            "prompt": "Build a clean telemetry status widget.",
        },
    )
    assert forge.status_code == 201
    frg_id = forge.json()["forge_id"]
    files = forge.json()["files"]
    files["README.md"] = "# Telemetry Micro App\nUpdated inside FORGE code editor."

    saved = client.patch(
        f"/api/v1/forge/projects/{frg_id}",
        headers=auth_headers["owner"],
        json={"files": files},
    )
    assert saved.status_code == 200
    assert saved.json()["status"] == "VERIFIED"
    assert "Updated inside FORGE code editor." in saved.json()["files"]["README.md"]

    preview = client.get(f"/api/v1/forge/projects/{frg_id}/preview", headers=auth_headers["owner"])
    assert preview.status_code == 200
    assert "text/html" in preview.headers.get("content-type", "")
