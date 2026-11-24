"""Agent 2: queries Cloud SQL for the user named in a verified, signed assertion.

The user comes from a signed assertion: the web app signs a short JWT (as its service account) naming the
user, Agent 1 passes it through, and Agent 2 verifies it before using the user.
"""
import os
import time

from demo_agents.common import code_ref

INSTANCE = os.environ["SQL_CONNECTION_NAME"]  # project:region:instance
DB_NAME = os.environ["DB_NAME"]
ASSERTION_ISSUER = os.environ["ASSERTION_ISSUER"]  # the web app's service account email
ASSERTION_AUDIENCE = os.environ.get("ASSERTION_AUDIENCE", "agent2")
CERTS_URL = f"https://www.googleapis.com/service_accounts/v1/metadata/x509/{ASSERTION_ISSUER}"


class Agent2:
    def set_up(self):
        from google.cloud.sql.connector import Connector

        self._user = os.environ["DB_USER"]
        self._password = None
        self._connector = Connector(refresh_strategy="lazy")
        self._certs, self._certs_at, self._seen_jti = None, 0.0, {}

    def register_operations(self):
        return {"": ["enroll_cookie", "query_db"]}

    def _db_password(self):
        if self._password is None:
            from google.cloud import secretmanager

            sm = secretmanager.SecretManagerServiceClient(transport="rest")
            name = os.environ["DB_SECRET"]  # projects/.../secrets/.../versions/latest
            self._password = sm.access_secret_version(name=name).payload.data.decode().strip()
        return self._password

    def _conn(self):
        return self._connector.connect(
            INSTANCE, "pymysql", user=self._user, password=self._db_password(), db=DB_NAME
        )

    def _issuer_certs(self):
        """The issuer's public signing keys, published by Google (cached for an hour)."""
        import requests

        if self._certs is None or time.time() - self._certs_at > 3600:
            self._certs = requests.get(CERTS_URL, timeout=5).json()
            self._certs_at = time.time()
        return self._certs

    def _verify_user(self, assertion: str, email: str):
        """Return (user, identity_check). The user comes from the verified assertion only."""
        from google.auth import jwt

        require = os.environ.get("REQUIRE_ASSERTION", "true") == "true"
        if not assertion:
            check = {"verified": False, "mode": "require" if require else "accept-both",
                     "checks": [{"name": "user assertion present", "ok": False}],
                     "reason": "no assertion sent" + ("" if require else "; using the email argument (legacy)")}
            return (None if require else email), check
        checks = []
        try:
            header = jwt.decode_header(assertion)
            kid = header.get("kid", "")
            certs = self._issuer_certs()
            checks.append({"name": f"signing key {kid[:12]}… is one of {ASSERTION_ISSUER}'s published keys",
                           "ok": kid in certs})
            claims = jwt.decode(assertion, certs=certs, verify=True, clock_skew_in_seconds=10)
            checks.append({"name": "signature valid (RS256)", "ok": True})
        except Exception as exc:  # bad signature, expired, malformed
            checks.append({"name": "signature valid and not expired", "ok": False,
                           "detail": f"{type(exc).__name__}: {str(exc)[:160]}"})
            return None, {"verified": False, "checks": checks, "reason": "assertion rejected"}
        now = time.time()
        self._seen_jti = {j: t for j, t in self._seen_jti.items() if t > now}
        jti = claims.get("jti", "")
        checks += [
            {"name": f"iss == {ASSERTION_ISSUER}", "ok": claims.get("iss") == ASSERTION_ISSUER},
            {"name": f"aud == {ASSERTION_AUDIENCE}", "ok": claims.get("aud") == ASSERTION_AUDIENCE},
            {"name": f"not expired ({int(claims.get('exp', 0) - now)} s left)", "ok": claims.get("exp", 0) > now},
            {"name": "jti not used before (single use)", "ok": bool(jti) and jti not in self._seen_jti},
        ]
        ok = all(c["ok"] for c in checks)
        if ok:
            self._seen_jti[jti] = claims["exp"] + 10
        check = {"verified": ok, "checks": checks, "claims": claims,
                 "user_from_token": claims.get("sub"),
                 "email_argument_ignored": email if email and email != claims.get("sub") else None,
                 "reason": "assertion verified" if ok else "assertion rejected"}
        return (claims.get("sub") if ok else None), check

    def _rejected(self, check: dict) -> dict:
        return {"agent": "Agent 2", "rejected": True, "identity_check": check, "rows": [],
                "sql": "(not run: the user assertion was rejected)",
                "received": {"user": "(rejected)"}, "code": code_ref()}

    def enroll_cookie(self, cookie: str, email: str, assertion: str = "") -> dict:
        """Register the received cookie with its user so rows can be tied to it."""
        email, check = self._verify_user(assertion, email)
        if email is None:
            return self._rejected(check)
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO user_data (cookie, user, note) VALUES (%s, %s, %s) "
                    "ON DUPLICATE KEY UPDATE user = VALUES(user)",
                    (cookie, email, f"profile note for {email}"),
                )
            conn.commit()
        finally:
            conn.close()
        return {"agent": "Agent 2", "stored": True, "identity_check": check,
                "received": {"user": email, "cookie": cookie}, "code": code_ref()}

    def query_db(self, email: str, assertion: str = "") -> dict:
        """Return rows that belong to the verified user, plus the SQL that was run."""
        email, check = self._verify_user(assertion, email)
        if email is None:
            return self._rejected(check)
        sql = "SELECT user, note, created_at FROM user_data WHERE user = %s"
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (email,))  # executed parameterized
                rows = [
                    {"user": r[0], "note": r[1], "created_at": str(r[2])}
                    for r in cur.fetchall()
                ]
        finally:
            conn.close()
        shown = sql.replace("%s", "'" + email.replace("'", "''") + "'")
        return {"agent": "Agent 2", "sql": shown, "rows": rows, "identity_check": check,
                "received": {"user": email}, "code": code_ref()}
