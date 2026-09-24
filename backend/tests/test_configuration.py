from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.controllers import configuration


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    # Use a synthetic project so tests never need the real local .env or key.
    project = tmp_path / "project"
    helper = project / "backend" / "controllers" / "configuration.py"
    helper.parent.mkdir(parents=True)
    monkeypatch.setattr(configuration, "__file__", str(helper))
    monkeypatch.delenv("GEOAPIFY_API_KEY", raising=False)
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    monkeypatch.chdir(tmp_path)
    return project / ".env"


@pytest.mark.parametrize(
    ("contents", "configured"),
    [
        (None, False),
        ("", False),
        ("GEOAPIFY_API_KEY=\n", False),
        ('GEOAPIFY_API_KEY="   "\n', False),
        ("GEOAPIFY_API_KEY=synthetic-test-only\n", True),
    ],
)
def test_health_configuration_contract(env_file, tmp_path, contents, configured):
    if contents is not None:
        env_file.write_text(contents)
    # A decoy in the working directory must not be used.
    Path(".env").write_text("GEOAPIFY_API_KEY=wrong-directory\n")

    with TestClient(create_app(tmp_path / "test.sqlite3")) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert response.json() == {
            "status": "ok",
            "geoapify": (
                "key is configured" if configured else "key is not configured"
            ),
        }
        schema = client.get("/openapi.json").json()
        health_schema = schema["components"]["schemas"]["HealthResponse"]
        assert set(health_schema["properties"]) == {"status", "geoapify"}
        assert schema["paths"]["/api/health"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/HealthResponse"
        }


@pytest.mark.parametrize("value", ["", " \t\n", "synthetic-environment-only"])
def test_process_environment_takes_precedence(env_file, monkeypatch, value):
    env_file.write_text("GEOAPIFY_API_KEY=synthetic-file-only\n")
    monkeypatch.setenv("GEOAPIFY_API_KEY", value)

    assert configuration.geoapify_key_is_configured() is bool(value.strip())


def test_health_uses_startup_configuration(env_file, tmp_path, monkeypatch):
    env_file.write_text("GEOAPIFY_API_KEY=synthetic-test-only\n")

    with TestClient(create_app(tmp_path / "test.sqlite3")) as client:
        env_file.write_text("GEOAPIFY_API_KEY=\n")
        monkeypatch.delenv("GEOAPIFY_API_KEY")
        assert client.get("/api/health").json()["geoapify"] == "key is configured"

    with TestClient(create_app(tmp_path / "test.sqlite3")) as client:
        assert client.get("/api/health").json()["geoapify"] == "key is not configured"
