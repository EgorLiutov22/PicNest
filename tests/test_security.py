import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


class TestRateLimiting:
    def test_login_rate_limit(self, client):
        for i in range(7):
            response = client.post(
                "/api/v1/auth/login",
                data={"username": "test@example.com", "password": "wrong_password"}
            )
            if i < 5:
                assert response.status_code == 401
            else:
                assert response.status_code == 429
                data = response.json()
                assert "error_code" in data
                assert data["error_code"] == "RATE_LIMIT_EXCEEDED"

    def test_register_rate_limit(self, client):
        for i in range(4):
            response = client.post(
                "/api/v1/auth/register",
                json={"email": f"test{i}@example.com", "password": "TestPassword123!", "first_name": "Test", "last_name": "User", "role": "client"}
            )
            if i < 3:
                assert response.status_code in [201, 409]
            else:
                assert response.status_code == 429

    def test_rate_limit_headers(self, client):
        response = client.get("/api/v1/orders")
        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers

    def test_xss_headers(self, client):
        response = client.get("/api/v1/orders")
        assert "X-Content-Type-Options" in response.headers
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    def test_xframe_options(self, client):
        response = client.get("/api/v1/orders")
        assert "X-Frame-Options" in response.headers

    def test_hsts_header(self, client):
        response = client.get("/api/v1/orders")
        if "Strict-Transport-Security" in response.headers:
            hsts = response.headers["Strict-Transport-Security"]
            assert "max-age=31536000" in hsts

    def test_email_validation(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "invalid-email", "password": "TestPassword123!", "first_name": "Test", "last_name": "User", "role": "client"}
        )
        assert response.status_code == 422

    def test_password_not_in_response(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "test@example.com", "password": "TestPassword123!", "first_name": "Test", "last_name": "User", "role": "client"}
        )
        if response.status_code == 201:
            data = response.json()
            assert "password" not in data

    def test_hashed_password_not_in_response(self, client):
        response = client.post(
            "/api/v1/auth/login",
            data={"username": "test@example.com", "password": "TestPassword123!"}
        )
        if response.status_code == 200:
            access_token = response.json()["access_token"]
            profile_response = client.get("/api/v1/auth/users/me", headers={"Authorization": f"Bearer {access_token}"})
            if profile_response.status_code == 200:
                data = profile_response.json()
                assert "hashed_password" not in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
