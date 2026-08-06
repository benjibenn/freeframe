"""End-to-end OAuth flow against a real Postgres + Redis. Run inside the api image."""
import base64, hashlib, os, secrets, sys, uuid
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

sys.path.insert(0, "/workspace")
from apps.api.main import app                      # noqa: E402
from apps.api.database import SessionLocal          # noqa: E402
from apps.api.models.user import User, UserStatus   # noqa: E402
from apps.api.models.oauth import OAuthToken        # noqa: E402
from apps.api.routers import mcp_oauth_routes as R  # noqa: E402
from apps.api.services.mcp_oauth_provider import create_client  # noqa: E402

FAIL = []
def check(label, cond, extra=""):
    print(("  PASS  " if cond else "  FAIL  ") + label + (f"   {extra}" if extra else ""))
    if not cond: FAIL.append(label)

db = SessionLocal()
admin = User(email=f"oauth-e2e-{uuid.uuid4().hex[:8]}@test.local", name="E2E Admin",
             status=UserStatus.active, email_verified=True, is_superadmin=True)
db.add(admin); db.commit(); db.refresh(admin)
row, client_id = create_client(db, name="E2E Connector",
    redirect_uris=["https://claude.ai/api/mcp/auth_callback"],
    scope="briefs:read briefs:write", created_by=admin.id)
print(f"client_id={client_id}  admin={admin.email}\n")

verifier = secrets.token_urlsafe(48)
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")

# Import the real dependency OUTSIDE any patch: overriding with a patched mock
# as the key silently does nothing, which is what made this 403 the first time.
from apps.api.middleware.auth import get_current_user  # noqa: E402

with patch("apps.api.services.s3_service.ensure_bucket_exists"), \
     patch("apps.api.services.s3_service.get_s3_client", return_value=MagicMock()):
    app.dependency_overrides[get_current_user] = lambda: admin
    with TestClient(app) as c:
        print("== discovery ==")
        prm = c.get("/.well-known/oauth-protected-resource").json()
        asm = c.get("/.well-known/oauth-authorization-server").json()
        check("protected resource names our issuer",
              prm["authorization_servers"] == [asm["issuer"]], f"{prm['authorization_servers']}")
        check("AS advertises S256 (Claude requires it)",
              asm.get("code_challenge_methods_supported") == ["S256"],
              str(asm.get("code_challenge_methods_supported")))
        check("DCR not advertised (disabled)", "registration_endpoint" not in asm)

        print("\n== authorize ==")
        r = c.get("/authorize", params={
            "client_id": client_id, "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "response_type": "code", "code_challenge": challenge,
            "code_challenge_method": "S256", "state": "xyz",
            "scope": "briefs:read briefs:write",
            "resource": "https://freeframe.multiadsx.com/api/mcp/",
        }, follow_redirects=False)
        loc = r.headers.get("location", "")
        check("redirects to consent, not to a code", r.status_code in (302, 307) and "/oauth/consent" in loc, loc[:90])
        request_id = loc.split("request_id=")[-1]

        print("\n== unregistered redirect_uri is refused ==")
        bad = c.get("/authorize", params={
            "client_id": client_id, "redirect_uri": "https://claude.ai/api/mcp/auth_callback/../evil",
            "response_type": "code", "code_challenge": challenge,
            "code_challenge_method": "S256"}, follow_redirects=False)
        check("exact-match redirect rejects a near-miss", bad.status_code >= 400 or "error" in bad.headers.get("location",""),
              f"status={bad.status_code}")

        print("\n== consent ==")
        info = c.get(f"/oauth/consent/{request_id}")
        check("consent page gets client + redirect host", info.status_code == 200 and info.json()["client_name"] == "E2E Connector")
        dec = c.post("/oauth/consent", json={"request_id": request_id, "approve": True})
        check("approval returns the client's redirect", dec.status_code == 200 and dec.json()["redirect_to"].startswith("https://claude.ai/"))
        code = dec.json()["redirect_to"].split("code=")[1].split("&")[0]
        check("state is echoed back", "state=xyz" in dec.json()["redirect_to"])

        print("\n== replayed approval mints nothing ==")
        again = c.post("/oauth/consent", json={"request_id": request_id, "approve": True})
        check("second approve is refused", again.status_code == 404, f"status={again.status_code}")

        print("\n== token exchange ==")
        bad_pkce = c.post("/token", data={"grant_type": "authorization_code", "code": code,
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": client_id, "code_verifier": "wrong-verifier"})
        check("wrong PKCE verifier is rejected", bad_pkce.status_code >= 400, f"status={bad_pkce.status_code}")

        tok = c.post("/token", data={"grant_type": "authorization_code", "code": code,
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": client_id, "code_verifier": verifier})
        check("form-urlencoded token exchange works", tok.status_code == 200, f"status={tok.status_code} {tok.text[:120]}")
        if tok.status_code != 200: raise SystemExit(1)
        body = tok.json(); access, refresh = body["access_token"], body["refresh_token"]

        print("\n== code is single use ==")
        reuse = c.post("/token", data={"grant_type": "authorization_code", "code": code,
            "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
            "client_id": client_id, "code_verifier": verifier})
        check("redeeming the same code twice fails", reuse.status_code >= 400, f"status={reuse.status_code}")

        print("\n== the token actually drives MCP ==")
        H = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json",
             "Authorization": f"Bearer {access}"}
        init = c.post("/mcp/", headers=H, json={"jsonrpc":"2.0","id":1,"method":"initialize",
            "params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"e2e","version":"1"}}})
        check("initialize with Bearer", init.status_code == 200, f"status={init.status_code} {init.text[:120]}")
        tl = c.post("/mcp/", headers=H, json={"jsonrpc":"2.0","id":2,"method":"tools/list"})
        check("tools/list with Bearer", tl.status_code == 200 and len(tl.json()["result"]["tools"]) == 7)

        print("\n== refresh rotates ==")
        rf = c.post("/token", data={"grant_type": "refresh_token", "refresh_token": refresh, "client_id": client_id})
        check("refresh returns a new pair", rf.status_code == 200, f"status={rf.status_code} {rf.text[:120]}")
        new_refresh = rf.json().get("refresh_token")
        check("refresh token is rotated, not reissued", new_refresh and new_refresh != refresh)

        print("\n== replaying the rotated refresh kills the chain ==")
        replay = c.post("/token", data={"grant_type": "refresh_token", "refresh_token": refresh, "client_id": client_id})
        check("replayed refresh is refused", replay.status_code >= 400, f"status={replay.status_code}")
        after = c.post("/token", data={"grant_type": "refresh_token", "refresh_token": new_refresh, "client_id": client_id})
        check("chain revoked: the good refresh dies too", after.status_code >= 400, f"status={after.status_code}")

        print("\n== revocation is immediate ==")
        live = SessionLocal().query(OAuthToken).filter(
            OAuthToken.token_hash == __import__("apps.api.models.oauth", fromlist=["x"]).hash_secret(access)).first()
        check("access token row was revoked with the chain", live is not None and live.revoked_at is not None)
        after_tok = c.post("/mcp/", headers=H, json={"jsonrpc":"2.0","id":3,"method":"tools/list"})
        check("revoked access token no longer authenticates", after_tok.status_code == 401, f"status={after_tok.status_code}")

print("\n" + ("ALL PASSED" if not FAIL else f"FAILURES: {FAIL}"))
sys.exit(1 if FAIL else 0)
