"""Test 1 of 4 — the auth round-trip.

This exists because of a specific outage: `sqlite3.Row` has no `.get()`, and a
`row.get("role")` in the login handler 500'd **every login on production** while
registration kept working, so the service looked healthy from outside. The
lesson is that registering is not logging in, and a test that only registers
proves nothing.

The one assertion that would have caught it is the full round-trip: register,
then come back and log in *with the password*, then use the token.
"""

from conftest import auth


def test_register_then_login_then_authenticated_call(client, new_user):
    email, password, _token, user_id = new_user()

    # Come back as a returning user -- this is the step that was broken in prod.
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["id"] == user_id
    # The field whose absence caused the outage. Present and non-null.
    assert body["user"]["role"], "login response lost the role field"

    r = client.get("/api/auth/me", headers=auth(body["token"]))
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == email


def test_login_is_case_insensitive_on_email(client, new_user):
    email, password, _t, _uid = new_user()
    r = client.post("/api/auth/login",
                    json={"email": email.upper(), "password": password})
    assert r.status_code == 200, r.text


def test_wrong_password_is_401_not_500(client, new_user):
    email, _password, _t, _uid = new_user()
    r = client.post("/api/auth/login",
                    json={"email": email, "password": "not-the-password"})
    assert r.status_code == 401


def test_unknown_email_is_401_and_indistinguishable_from_wrong_password(client):
    r = client.post("/api/auth/login",
                    json={"email": "nobody@example.com", "password": "whatever"})
    assert r.status_code == 401
    # Enumeration safety: the response must not reveal that the account is absent.
    assert "not found" not in r.text.lower()
    assert "no such" not in r.text.lower()


def test_missing_and_malformed_tokens_are_401(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me",
                      headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_staff_domain_selfsignup_is_refused(client):
    """A staff-domain account is uncapped on AI, so self-signup on that domain
    was a live cost hole once. 403 here is a money control, not a nicety."""
    r = client.post("/api/auth/register", json={
        "email": "anyone@greencurve.solutions", "name": "X", "org": "Y",
        "password": "correct-horse-battery",
    })
    assert r.status_code == 403


def test_duplicate_email_is_409(client, new_user):
    email, password, _t, _uid = new_user()
    r = client.post("/api/auth/register", json={
        "email": email, "name": "Again", "org": "Z", "password": password,
    })
    assert r.status_code == 409


def test_short_password_rejected(client):
    r = client.post("/api/auth/register", json={
        "email": "shortpw@example.com", "name": "X", "org": "Y", "password": "abc",
    })
    assert r.status_code == 400


def test_password_over_72_bytes_rejected_not_silently_truncated(client):
    """bcrypt silently ignores bytes past 72. Without an explicit reject, two
    different long passwords would authenticate the same account."""
    r = client.post("/api/auth/register", json={
        "email": "longpw@example.com", "name": "X", "org": "Y",
        "password": "a" * 73,
    })
    assert r.status_code == 400
