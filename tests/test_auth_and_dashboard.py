import io
import pytest
from finpay import create_app
from finpay.auth.models import user_store
from finpay.data.repository import repo


@pytest.fixture
def client():
    user_store.reset_for_testing()
    app = create_app({"TESTING": True, "WTF_CSRF_ENABLED": False})
    with app.test_client() as client:
        yield client
    user_store.reset_for_testing()


def test_unauthenticated_dashboard_redirects_to_login_requirement_5(client):
    """Requirement 5: Unauthenticated access to dashboard must redirect to login."""
    res = client.get("/dashboard", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


def test_unauthenticated_root_redirects(client):
    res = client.get("/", follow_redirects=False)
    assert res.status_code == 302


def test_successful_login_and_dashboard_access(client):
    login_res = client.post(
        "/login",
        data={"username": "analyst@finpay.com", "password": "password123"},
        follow_redirects=True,
    )
    assert login_res.status_code == 200
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
    client.post(
        "/login",
        data={"username": "analyst@finpay.com", "password": "password123"},
    )
    logout_res = client.get("/logout", follow_redirects=False)
    assert logout_res.status_code == 302
    assert "/login" in logout_res.headers["Location"]

    dash_res = client.get("/dashboard", follow_redirects=False)
    assert dash_res.status_code == 302
    assert "/login" in dash_res.headers["Location"]


# New User Registration / Signup Tests
def test_signup_successful(client):
    unique_email = "newanalyst_test@finpay.com"
    res = client.post(
        "/signup",
        data={
            "full_name": "Jordan Miller",
            "username": unique_email,
            "password": "strongpassword123",
            "confirm_password": "strongpassword123",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Jordan Miller" in res.data
    assert b"Sign Out" in res.data

    # Verify user was created in store with Analyst role
    created = user_store.get_by_username(unique_email)
    assert created is not None
    assert created.role == "Analyst"
    assert created.full_name == "Jordan Miller"


def test_signup_duplicate_email_rejected(client):
    res = client.post(
        "/signup",
        data={
            "full_name": "Imposter",
            "username": "analyst@finpay.com",  # already exists
            "password": "password123",
            "confirm_password": "password123",
        },
        follow_redirects=True,
    )
    assert b"already exists" in res.data


def test_signup_password_mismatch_rejected(client):
    res = client.post(
        "/signup",
        data={
            "full_name": "Bob",
            "username": "bob_mismatch@finpay.com",
            "password": "password123",
            "confirm_password": "password456",
        },
        follow_redirects=True,
    )
    assert b"Passwords do not match" in res.data


# Role-Based Access Control (RBAC) Tests
def test_analyst_cannot_access_admin_portal(client):
    # Log in as Analyst
    client.post(
        "/login",
        data={"username": "analyst@finpay.com", "password": "password123"},
    )
    # Attempt to access /admin
    res = client.get("/admin", follow_redirects=True)
    assert res.status_code == 200
    # Should be redirected back to dashboard with flash warning
    assert b"Access denied: Administrator privileges required" in res.data


def test_admin_can_access_admin_portal(client):
    # Log in as Admin
    login_res = client.post(
        "/login",
        data={"username": "admin@finpay.com", "password": "adminpassword"},
        follow_redirects=True,
    )
    assert login_res.status_code == 200

    # Access /admin
    admin_res = client.get("/admin")
    assert admin_res.status_code == 200
    assert b"Analyst Oversight & Audit Control" in admin_res.data
    assert b"Registered Analysts" in admin_res.data
    assert b"Platform Activity" in admin_res.data


def test_admin_api_rbac_protection(client):
    # Unauthenticated -> 302 or 403
    unauth_res = client.get("/api/admin/analysts")
    assert unauth_res.status_code in (302, 403)

    # Analyst -> 403 Forbidden
    client.post("/login", data={"username": "analyst@finpay.com", "password": "password123"})
    analyst_res = client.get("/api/admin/analysts")
    assert analyst_res.status_code == 403

    # Admin -> 200 OK
    client.get("/logout")
    client.post("/login", data={"username": "admin@finpay.com", "password": "adminpassword"})
    admin_res = client.get("/api/admin/analysts")
    assert admin_res.status_code == 200
    data = admin_res.get_json()
    assert "analysts" in data
    assert data["count"] >= 1


# Multi-Tenant Data Isolation Test
def test_multi_tenant_data_isolation(client):
    # User A registers and uploads private CSV
    email_a = "analyst_a@bank.com"
    client.post(
        "/signup",
        data={"full_name": "Analyst A", "username": email_a, "password": "password123", "confirm_password": "password123"},
    )
    user_a = user_store.get_by_username(email_a)

    csv_a = "date,description,amount,category\n2024-01-01,Confidential Flight A,999.00,Transportation\n"
    client.post("/api/upload", data={"file": (io.BytesIO(csv_a.encode()), "a.csv")}, content_type="multipart/form-data")

    # Verify User A sees Confidential Flight A
    res_a = client.get("/api/transactions")
    data_a = res_a.get_json()
    assert any("Confidential Flight A" in tx["description"] for tx in data_a["transactions"])

    # Log out User A and sign up User B
    client.get("/logout")
    email_b = "analyst_b@bank.com"
    client.post(
        "/signup",
        data={"full_name": "Analyst B", "username": email_b, "password": "password123", "confirm_password": "password123"},
    )

    # User B should NOT see User A's confidential transaction!
    res_b = client.get("/api/transactions")
    data_b = res_b.get_json()
    assert not any("Confidential Flight A" in tx["description"] for tx in data_b["transactions"])


# Profile Page & Edit Options Tests
def test_unauthenticated_profile_redirects(client):
    res = client.get("/profile", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


def test_profile_page_renders_for_authenticated_user(client):
    client.post("/login", data={"username": "analyst@finpay.com", "password": "password123"})
    res = client.get("/profile")
    assert res.status_code == 200
    assert b"User Profile & Account Settings" in res.data
    assert b"Sarah Jenkins" in res.data
    assert b"analyst@finpay.com" in res.data
    assert b"Edit Profile Information" in res.data
    assert b"Change Account Password" in res.data


def test_profile_update_details(client):
    # Register a new user to test profile editing
    email = "edit_test@finpay.com"
    client.post(
        "/signup",
        data={"full_name": "Original Name", "username": email, "password": "password123", "confirm_password": "password123"},
    )

    # Submit profile update
    res = client.post(
        "/profile",
        data={"action": "update_profile", "full_name": "Updated Name", "username": "new_email@finpay.com"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Profile information updated successfully" in res.data
    assert b"Updated Name" in res.data
    assert b"new_email@finpay.com" in res.data


def test_profile_change_password_success(client):
    email = "pw_test@finpay.com"
    client.post(
        "/signup",
        data={"full_name": "Password User", "username": email, "password": "oldpassword123", "confirm_password": "oldpassword123"},
    )

    # Change password
    res = client.post(
        "/profile",
        data={
            "action": "change_password",
            "current_password": "oldpassword123",
            "new_password": "brandnewpassword456",
            "confirm_password": "brandnewpassword456",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Password changed successfully" in res.data

    # Log out and log back in with new password
    client.get("/logout")
    login_new = client.post("/login", data={"username": email, "password": "brandnewpassword456"}, follow_redirects=True)
    assert login_new.status_code == 200
    assert b"Sign Out" in login_new.data


def test_profile_change_password_invalid_old_password(client):
    email = "pw_fail@finpay.com"
    client.post(
        "/signup",
        data={"full_name": "Fail User", "username": email, "password": "password123", "confirm_password": "password123"},
    )

    res = client.post(
        "/profile",
        data={
            "action": "change_password",
            "current_password": "wrongpassword",
            "new_password": "newpassword123",
            "confirm_password": "newpassword123",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Current password is incorrect" in res.data


def test_api_me_json_endpoint(client):
    client.post("/login", data={"username": "analyst@finpay.com", "password": "password123"})
    res = client.get("/api/me", headers={"Accept": "application/json"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["authenticated"] is True
    assert "username" in data
    assert "full_name" in data
    assert "role" in data
    assert "stats" in data


def test_api_me_json_update(client):
    email = "json_update@finpay.com"
    client.post(
        "/signup",
        data={"full_name": "API User", "username": email, "password": "password123", "confirm_password": "password123"},
    )

    res = client.post(
        "/api/me",
        json={"full_name": "API User Renamed"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["user"]["full_name"] == "API User Renamed"
