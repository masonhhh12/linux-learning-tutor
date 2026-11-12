"""Real SQLite and password hashing tests, with isolated temporary databases."""
import hashlib
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import auth
import main
from fastapi.testclient import TestClient

PASSWORD = "correct horse tutor battery"
ACCOUNT = {"username": "student", "password": PASSWORD}


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path_patch = patch.object(auth, "DB_PATH", Path(self.temp.name) / "accounts.sqlite3")
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        auth.init_db()
        self.client = TestClient(main.app, base_url="http://localhost")
        self.client.headers["Origin"] = "http://localhost"
        self.addCleanup(self.client.close)

    def register(self):
        r = self.client.post("/auth/register", json=ACCOUNT)
        self.assertEqual(r.status_code, 201, r.text)
        self.client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
        return r

    def test_registration_hashes_password_and_session(self):
        response = self.register()
        self.assertNotIn(PASSWORD, response.text)
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=strict", cookie)
        token = self.client.cookies.get(auth.COOKIE)
        with auth.database() as db:
            user = db.execute("SELECT * FROM users").fetchone()
            session = db.execute("SELECT * FROM sessions").fetchone()
        self.assertTrue(user["password_hash"].startswith("$argon2id$"))
        self.assertTrue(auth.hasher.verify(user["password_hash"], PASSWORD))
        self.assertNotEqual(user["password_hash"], PASSWORD)
        self.assertEqual(session["token_hash"], hashlib.sha256(token.encode()).hexdigest())
        self.assertNotEqual(session["token_hash"], token)

    def test_login_and_normalized_username(self):
        self.register()
        self.client.cookies.clear()
        r = self.client.post("/auth/login", json={"username":"STUDENT","password":PASSWORD})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/auth/me").json()["username"], "student")

    def test_login_failure_is_generic(self):
        self.register()
        self.client.cookies.clear()
        wrong = self.client.post("/auth/login", json={"username":"student","password":"wrong"})
        unknown = self.client.post("/auth/login", json={"username":"missing","password":"wrong"})
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(wrong.json(), unknown.json())

    def test_duplicate_username_and_weak_password(self):
        self.register()
        self.assertEqual(self.client.post("/auth/register", json=ACCOUNT).status_code,409)
        self.assertEqual(self.client.post("/auth/register",json={
            "username":"another","password":"short"}).status_code,422)

    def test_sql_injection_username_rejected(self):
        self.assertEqual(self.client.post("/auth/login",json={
            "username":"' OR 1=1 --","password":PASSWORD}).status_code,422)
        with auth.database() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM users").fetchone()[0],0)

    def test_anonymous_cannot_use_tutor(self):
        self.assertEqual(self.client.get("/",follow_redirects=False).status_code,303)
        self.assertEqual(self.client.get("/auth/me").status_code,401)
        for path in ("/ask","/ask/stream"):
            self.assertEqual(self.client.post(path,json={"question":"hi"}).status_code,401)

    def test_login_origin_required(self):
        for origin in ("http://evil.example","null",""):
            r=self.client.post("/auth/login",json=ACCOUNT,headers={"Origin":origin})
            self.assertEqual(r.status_code,403)
        self.assertEqual(self.client.post("/auth/register",json=ACCOUNT,
            headers={"Origin":"http://evil.example"}).status_code,403)

    def test_csrf_required_for_authenticated_actions(self):
        self.register()
        for token in ("","incorrect"):
            self.assertEqual(self.client.post("/auth/logout",
                headers={"X-CSRF-Token":token}).status_code,403)
            self.assertEqual(self.client.post("/ask",json={"question":"hi"},
                headers={"X-CSRF-Token":token}).status_code,403)

    def test_cross_origin_rejected_even_with_csrf(self):
        self.register()
        self.assertEqual(self.client.post("/auth/logout",
            headers={"Origin":"http://evil.example"}).status_code,403)

    def test_logout_invalidates_replayed_cookie(self):
        self.register()
        token=self.client.cookies.get(auth.COOKIE)
        self.assertEqual(self.client.post("/auth/logout").status_code,204)
        self.client.cookies.set(auth.COOKIE,token)
        self.assertEqual(self.client.get("/auth/me").status_code,401)

    def test_session_rotation(self):
        self.register()
        old=self.client.cookies.get(auth.COOKIE)
        self.assertEqual(self.client.post("/auth/login",json=ACCOUNT).status_code,200)
        with auth.database() as db:
            self.assertIsNone(db.execute("SELECT * FROM sessions WHERE token_hash=?",
                (auth.digest(old),)).fetchone())

    def test_session_expiry(self):
        self.register()
        with auth.database() as db:
            db.execute("UPDATE sessions SET expires_at=?",(int(time.time())-1,))
        self.assertEqual(self.client.get("/auth/me").status_code,401)

    def test_rate_limit_persists_in_sql(self):
        for i in range(10):
            r=self.client.post("/auth/login",json={"username":"missing","password":"wrong"})
            self.assertEqual(r.status_code,401)
        r=self.client.post("/auth/login",json={"username":"missing","password":"wrong"})
        self.assertEqual(r.status_code,429)
        self.assertIn("Retry-After",r.headers)

    def test_security_headers_and_asset_allowlist(self):
        r=self.client.get("/login")
        self.assertEqual(r.status_code,200)
        self.assertIn("script-src 'self'",r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["Cache-Control"],"no-store")
        self.assertEqual(r.headers["X-Frame-Options"],"DENY")
        self.assertEqual(self.client.get("/assets/login.js").status_code,200)
        self.assertEqual(self.client.get("/assets/auth.py").status_code,404)

    def test_request_body_limit(self):
        r=self.client.post("/auth/login",content="x"*256001,
            headers={"Content-Type":"application/json"})
        self.assertEqual(r.status_code,413)

    def test_untrusted_host_rejected(self):
        self.assertEqual(self.client.get("/login", headers={"Host":"attacker.example"}).status_code,400)

    def test_validation_does_not_echo_password(self):
        secret = "x" * 129
        r = self.client.post("/auth/register",json={"username":"student","password":secret})
        self.assertEqual(r.status_code,422)
        self.assertNotIn(secret,r.text)

    def test_secure_cookie_setting(self):
        with patch.object(auth,"SECURE_COOKIES",True):
            r=self.register()
            self.assertIn("Secure",r.headers["set-cookie"])
            self.assertIn("Strict-Transport-Security",r.headers)


if __name__ == "__main__":
    unittest.main()
