"""
Module: test_version
Role: Test suite for /api/version endpoint (FTR-135)

Tests all evaluation criteria:
- EC-1: Response format (200 + JSON with name/version/env)
- EC-2: Custom env var values
- EC-3: Default values when env vars missing
- EC-4: No auth required
- EC-5: Method restrictions (POST → 405)
- EC-6: Swagger documentation availability

Uses:
  - fastapi.testclient:TestClient
  - config:Settings, get_settings
  - main:app

Glossary: None (example project)
"""

from fastapi.testclient import TestClient
from main import app
from config import Settings, get_settings


# Test fixtures for dependency override
def get_custom_settings():
    """Override settings with custom values for testing."""
    return Settings(name="testapp", version="2.0.0", env="staging")


def get_default_settings():
    """Override settings with explicit defaults (simulates missing env vars)."""
    return Settings(name="myapp", version="1.0.0", env="dev")


class TestVersionEndpoint:
    """Test suite for GET /api/version endpoint."""

    def test_endpoint_returns_200_with_json_structure(self):
        """EC-1: GET /api/version returns HTTP 200 with correct JSON keys."""
        # Setup custom settings
        app.dependency_overrides[get_settings] = get_custom_settings
        client = TestClient(app)

        # Execute request
        response = client.get("/api/version")

        # Verify status code
        assert response.status_code == 200

        # Verify JSON structure
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "env" in data

        # Cleanup
        app.dependency_overrides.clear()

    def test_endpoint_returns_custom_env_values(self):
        """EC-2: Values match custom environment variables."""
        # Setup custom settings
        app.dependency_overrides[get_settings] = get_custom_settings
        client = TestClient(app)

        # Execute request
        response = client.get("/api/version")

        # Verify custom values
        data = response.json()
        assert data["name"] == "testapp"
        assert data["version"] == "2.0.0"
        assert data["env"] == "staging"

        # Cleanup
        app.dependency_overrides.clear()

    def test_endpoint_returns_default_values(self):
        """EC-3: Default values when env vars are missing."""
        # Setup default settings
        app.dependency_overrides[get_settings] = get_default_settings
        client = TestClient(app)

        # Execute request
        response = client.get("/api/version")

        # Verify default values
        data = response.json()
        assert data["name"] == "myapp"
        assert data["version"] == "1.0.0"
        assert data["env"] == "dev"

        # Cleanup
        app.dependency_overrides.clear()

    def test_endpoint_requires_no_auth(self):
        """EC-4: No authentication required (GET without Authorization header)."""
        # Setup default settings
        app.dependency_overrides[get_settings] = get_default_settings
        client = TestClient(app)

        # Execute request WITHOUT Authorization header
        response = client.get("/api/version")

        # Verify success without auth
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "env" in data

        # Cleanup
        app.dependency_overrides.clear()

    def test_post_method_not_allowed(self):
        """EC-5: POST /api/version returns HTTP 405 Method Not Allowed."""
        # Setup default settings
        app.dependency_overrides[get_settings] = get_default_settings
        client = TestClient(app)

        # Execute POST request
        response = client.post("/api/version")

        # Verify method not allowed
        assert response.status_code == 405

        # Cleanup
        app.dependency_overrides.clear()

    def test_swagger_docs_available(self):
        """EC-6: Swagger documentation shows the endpoint."""
        # No settings override needed for docs
        client = TestClient(app)

        # Execute request to Swagger UI
        response = client.get("/docs")

        # Verify Swagger UI loads
        assert response.status_code == 200

        # Verify content type is HTML (Swagger UI)
        assert "text/html" in response.headers.get("content-type", "")

    def test_openapi_schema_includes_endpoint(self):
        """EC-6 (extended): OpenAPI schema includes /api/version endpoint."""
        client = TestClient(app)

        # Get OpenAPI schema
        response = client.get("/openapi.json")

        # Verify schema loads
        assert response.status_code == 200

        # Verify endpoint is in schema
        schema = response.json()
        assert "/api/version" in schema["paths"]
        assert "get" in schema["paths"]["/api/version"]

    def test_response_content_type_is_json(self):
        """Additional: Verify response content type is application/json."""
        app.dependency_overrides[get_settings] = get_default_settings
        client = TestClient(app)

        # Execute request
        response = client.get("/api/version")

        # Verify content type
        assert response.status_code == 200
        assert "application/json" in response.headers.get("content-type", "")

        # Cleanup
        app.dependency_overrides.clear()

    def test_endpoint_returns_valid_json(self):
        """Additional: Response body is valid JSON (no parsing errors)."""
        app.dependency_overrides[get_settings] = get_default_settings
        client = TestClient(app)

        # Execute request
        response = client.get("/api/version")

        # Verify JSON parsing succeeds
        assert response.status_code == 200
        try:
            data = response.json()
            assert isinstance(data, dict)
        except ValueError:
            assert False, "Response is not valid JSON"

        # Cleanup
        app.dependency_overrides.clear()


class TestVersionEndpointEdgeCases:
    """Edge case tests for version endpoint."""

    def test_multiple_requests_return_same_values(self):
        """Settings are consistent across multiple requests."""
        app.dependency_overrides[get_settings] = get_custom_settings
        client = TestClient(app)

        # Execute multiple requests
        response1 = client.get("/api/version")
        response2 = client.get("/api/version")

        # Verify consistency
        assert response1.json() == response2.json()

        # Cleanup
        app.dependency_overrides.clear()

    def test_put_method_not_allowed(self):
        """PUT /api/version returns HTTP 405."""
        app.dependency_overrides[get_settings] = get_default_settings
        client = TestClient(app)

        # Execute PUT request
        response = client.put("/api/version")

        # Verify method not allowed
        assert response.status_code == 405

        # Cleanup
        app.dependency_overrides.clear()

    def test_delete_method_not_allowed(self):
        """DELETE /api/version returns HTTP 405."""
        app.dependency_overrides[get_settings] = get_default_settings
        client = TestClient(app)

        # Execute DELETE request
        response = client.delete("/api/version")

        # Verify method not allowed
        assert response.status_code == 405

        # Cleanup
        app.dependency_overrides.clear()

    def test_patch_method_not_allowed(self):
        """PATCH /api/version returns HTTP 405."""
        app.dependency_overrides[get_settings] = get_default_settings
        client = TestClient(app)

        # Execute PATCH request
        response = client.patch("/api/version")

        # Verify method not allowed
        assert response.status_code == 405

        # Cleanup
        app.dependency_overrides.clear()
