import pytest
from finpay import create_app


@pytest.fixture
def client():
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False})
    with app.test_client() as client:
        yield client


def test_unauthenticated_dashboard_redirects_to_login_requirement_5(client):
    """Requirement 5: Unauthenticated access to dashboard must redirect to login."""
    res = client.get("/dashboard", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


def test_unauthenticated_root_redirects(client):
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 302


def test_successful_login_and_dashboard_access(client):
    # Perform login
    login_res = client.post(
        "/login",
        data={"username": "analyst@finpay.com", "password": "password123"},
        follow_redirects=True,
    )
    assert login_res.status_code == 200
    # User is now on the dashboard
    assert b"Spending Analytics & Insights" in login_res.data
    assert b"Sign Out" in login_res.data


def test_invalid_login_rejected(client):
    res = client.post(
        "/login",
        data={"username": "analyst@finpay.com", "password": "wrongpassword"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Invalid email or password" in res.data


def test_logout_revokes_access(client):
    # Log in
    client.post(
        "/login",
        data={"username": "analyst@finpay.com", "password": "password123"},
    )
    # Log out
    logout_res = client.get("/logout", follow_redirects=False)
    assert logout_res.status_code == 302
    assert "/login" in logout_res.headers["Location"]

    # Now attempt to access dashboard again
    dash_res = client.get("/dashboard", follow_redirects=False)
    assert dash_res.status_code == 302
    assert "/login" in dash_res.headers["Location"]
