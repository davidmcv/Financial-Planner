"""API tests for the pension-planner backend.

Run from the repository root:
    python3 -m unittest discover -s server/tests -t .
Uses a throwaway SQLite database per test run; no network, no fixtures.
"""
import os
import tempfile
import unittest

_TMPDIR = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMPDIR.name}/test.db"

from fastapi.testclient import TestClient  # noqa: E402

from server.app import app  # noqa: E402
from server.reference_data import (  # noqa: E402
    HIST_REAL_RETURNS, REFERENCE_VERSION, TAX_TABLES,
)


class ApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()  # run startup (create tables, seed reference)

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    # -- helpers ------------------------------------------------------------
    _serial = 0

    def register(self, email=None, password="hunter2-hunter2"):
        if email is None:
            ApiTestCase._serial += 1
            email = f"user{ApiTestCase._serial}@example.com"
        r = self.client.post("/api/auth/register",
                             json={"email": email, "password": password})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        return body["email"], body["token"]

    def auth(self, token):
        return {"Authorization": f"Bearer {token}"}

    # -- health & reference --------------------------------------------------
    def test_health(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_reference_data_served_from_db(self):
        r = self.client.get("/api/reference")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["version"], REFERENCE_VERSION)
        self.assertEqual(body["returns"], HIST_REAL_RETURNS)
        self.assertEqual(len(body["returns"]), 100)
        self.assertEqual(body["taxTables"]["UK"]["pa"], TAX_TABLES["UK"]["pa"])
        self.assertEqual(len(body["taxTables"]["UK"]["scotBands"]), 6)
        for country in ("UK", "US", "FR", "AU"):
            self.assertIn(country, body["taxTables"])

    def test_client_served_at_root(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Pension Planner", r.text)
        self.assertIn("MAJOR CHANGE IN PROGRESS", r.text)

    # -- auth -----------------------------------------------------------------
    def test_register_login_me_logout(self):
        email, token = self.register(password="correct-horse-battery")
        r = self.client.get("/api/auth/me", headers=self.auth(token))
        self.assertEqual(r.json(), {"email": email})

        r = self.client.post("/api/auth/login",
                             json={"email": email, "password": "correct-horse-battery"})
        self.assertEqual(r.status_code, 200)
        token2 = r.json()["token"]
        self.assertNotEqual(token, token2)

        r = self.client.post("/api/auth/logout", headers=self.auth(token))
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/auth/me", headers=self.auth(token))
        self.assertEqual(r.status_code, 401)  # revoked
        r = self.client.get("/api/auth/me", headers=self.auth(token2))
        self.assertEqual(r.status_code, 200)  # other session unaffected

    def test_register_duplicate_email_conflicts(self):
        email, _ = self.register()
        r = self.client.post("/api/auth/register",
                             json={"email": email, "password": "another-password"})
        self.assertEqual(r.status_code, 409)

    def test_login_wrong_password_rejected(self):
        email, _ = self.register(password="right-password-1")
        r = self.client.post("/api/auth/login",
                             json={"email": email, "password": "wrong-password-1"})
        self.assertEqual(r.status_code, 401)

    def test_short_password_rejected(self):
        r = self.client.post("/api/auth/register",
                             json={"email": "short@example.com", "password": "short"})
        self.assertEqual(r.status_code, 422)

    def test_endpoints_require_auth(self):
        for method, path in [("get", "/api/profiles"),
                             ("put", "/api/profiles/x"),
                             ("delete", "/api/profiles/x"),
                             ("get", "/api/auth/me")]:
            r = getattr(self.client, method)(
                path, **({"json": {}} if method == "put" else {}))
            self.assertEqual(r.status_code, 401, f"{method} {path}")

    # -- profiles ---------------------------------------------------------------
    def test_profile_crud_roundtrip(self):
        _, token = self.register()
        doc = {"dob": "1973-03-01", "yourPot": "1,000,000",
               "assets": {"savings": [{"type": "Cash ISA", "balance": 5000}]}}
        r = self.client.put("/api/profiles/Household", json=doc,
                            headers=self.auth(token))
        self.assertEqual(r.status_code, 200)

        r = self.client.get("/api/profiles", headers=self.auth(token))
        self.assertEqual(r.json()["profiles"]["Household"], doc)

        doc["yourPot"] = "1,250,000"
        self.client.put("/api/profiles/Household", json=doc, headers=self.auth(token))
        r = self.client.get("/api/profiles", headers=self.auth(token))
        self.assertEqual(r.json()["profiles"]["Household"]["yourPot"], "1,250,000")

        r = self.client.delete("/api/profiles/Household", headers=self.auth(token))
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/profiles", headers=self.auth(token))
        self.assertEqual(r.json()["profiles"], {})

    def test_profiles_are_private_per_user(self):
        _, token_a = self.register()
        _, token_b = self.register()
        self.client.put("/api/profiles/Secret", json={"yourPot": "9"},
                        headers=self.auth(token_a))
        r = self.client.get("/api/profiles", headers=self.auth(token_b))
        self.assertEqual(r.json()["profiles"], {})
        r = self.client.delete("/api/profiles/Secret", headers=self.auth(token_b))
        self.assertEqual(r.status_code, 404)

    def test_delete_missing_profile_404(self):
        _, token = self.register()
        r = self.client.delete("/api/profiles/Nope", headers=self.auth(token))
        self.assertEqual(r.status_code, 404)

    # -- sharing -----------------------------------------------------------------
    def test_share_read_only(self):
        adviser, token_a = self.register()
        client_email, token_c = self.register()
        self.client.put("/api/profiles/Plan", json={"yourPot": "100"},
                        headers=self.auth(token_a))
        r = self.client.post("/api/profiles/Plan/share",
                             json={"email": client_email, "permission": "read"},
                             headers=self.auth(token_a))
        self.assertEqual(r.status_code, 200)

        r = self.client.get("/api/profiles", headers=self.auth(token_c))
        shared = r.json()["shared"]
        self.assertEqual(len(shared), 1)
        self.assertEqual(shared[0]["owner"], adviser)
        self.assertEqual(shared[0]["name"], "Plan")
        self.assertEqual(shared[0]["permission"], "read")
        self.assertEqual(shared[0]["data"], {"yourPot": "100"})

        # Read-only: writing through the shared endpoint is forbidden.
        r = self.client.put(f"/api/shared/{adviser}/Plan", json={"yourPot": "0"},
                            headers=self.auth(token_c))
        self.assertEqual(r.status_code, 403)

    def test_share_write_and_unshare(self):
        adviser, token_a = self.register()
        client_email, token_c = self.register()
        self.client.put("/api/profiles/Joint", json={"yourPot": "1"},
                        headers=self.auth(token_a))
        self.client.post("/api/profiles/Joint/share",
                         json={"email": client_email, "permission": "write"},
                         headers=self.auth(token_a))

        r = self.client.put(f"/api/shared/{adviser}/Joint", json={"yourPot": "2"},
                            headers=self.auth(token_c))
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/profiles", headers=self.auth(token_a))
        self.assertEqual(r.json()["profiles"]["Joint"], {"yourPot": "2"})

        r = self.client.delete(f"/api/profiles/Joint/share/{client_email}",
                               headers=self.auth(token_a))
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/api/profiles", headers=self.auth(token_c))
        self.assertEqual(r.json()["shared"], [])
        r = self.client.put(f"/api/shared/{adviser}/Joint", json={"yourPot": "3"},
                            headers=self.auth(token_c))
        self.assertEqual(r.status_code, 403)

    def test_share_with_unknown_email_404(self):
        _, token = self.register()
        self.client.put("/api/profiles/P", json={}, headers=self.auth(token))
        r = self.client.post("/api/profiles/P/share",
                             json={"email": "nobody@example.com"},
                             headers=self.auth(token))
        self.assertEqual(r.status_code, 404)

    def test_share_random_user_cannot_write(self):
        adviser, token_a = self.register()
        _, token_x = self.register()
        self.client.put("/api/profiles/Private", json={"yourPot": "1"},
                        headers=self.auth(token_a))
        r = self.client.put(f"/api/shared/{adviser}/Private", json={"yourPot": "0"},
                            headers=self.auth(token_x))
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
