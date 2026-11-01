import os
import secrets
import hashlib
import requests
from urllib.parse import urlencode
from flask import Flask, redirect, request, session, jsonify, render_template_string

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PREFERRED_URL_SCHEME="https",
)

AUTH_URL = "https://api-t1.fyers.in/api/v3/generate-authcode"
TOKEN_URL = "https://api-t1.fyers.in/api/v3/validate-authcode"
access_token = None

def fyers_settings():
    # Read on each request so current host settings are checked, not stale import-time values.
    return {
        "app_id": os.environ.get("FYERS_APP_ID", "").strip(),
        "app_secret": os.environ.get("FYERS_APP_SECRET", "").strip(),
        "redirect_uri": os.environ.get("FYERS_REDIRECT_URI", "").strip(),
    }

def missing_settings(settings):
    missing = []
    if not settings["app_id"]:
        missing.append("FYERS_APP_ID")
    if not settings["app_secret"]:
        missing.append("FYERS_APP_SECRET")
    if not settings["redirect_uri"]:
        missing.append("FYERS_REDIRECT_URI")
    return missing

PAGE = """
<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trader Vikki Scanner</title>
<style>
body{font-family:Arial,sans-serif;background:#fffbea;margin:0;padding:18px;color:#172554}
.card{max-width:650px;margin:22px auto;background:white;padding:22px;border-radius:16px;box-shadow:0 3px 18px #0001}
h1{margin:0 0 8px;color:#1746a2}.tag{color:#555;margin-bottom:18px}
.status{padding:13px;border-radius:9px;background:#f1f5f9;margin:16px 0;line-height:1.5}
button{background:#1746a2;color:white;border:0;padding:13px 20px;border-radius:9px;font-size:16px}
small{color:#555}.ok{color:#087443}.bad{color:#a32626}
</style></head><body><div class="card">
<h1>Trader Vikki Scanner</h1><div class="tag">FYERS secure connection setup</div>
<div class="status">{{ status }}</div>
{% if ready %}<a href="/login"><button>Connect FYERS</button></a>
{% else %}<p class="bad">The server is missing one or more private settings. The diagnostic page shows only whether each setting exists; it never reveals secret values.</p>{% endif %}
<p><small>Market-data access only. This app does not place trades.</small></p>
</div></body></html>
"""

@app.get("/")
def home():
    settings = fyers_settings()
    missing = missing_settings(settings)
    if access_token:
        status = "FYERS connection established for this server session."
    elif not missing:
        status = "Backend configured. You can connect FYERS."
    else:
        status = "Backend setup incomplete. Missing: " + ", ".join(missing)
    return render_template_string(PAGE, status=status, ready=not missing)

@app.get("/health")
def health():
    return jsonify({"status": "ok", "app": "Trader Vikki Scanner"})

@app.get("/config-status")
def config_status():
    settings = fyers_settings()
    missing = missing_settings(settings)
    return jsonify({
        "app": "Trader Vikki Scanner",
        "configured": not missing,
        "FYERS_APP_ID_present": bool(settings["app_id"]),
        "FYERS_APP_SECRET_present": bool(settings["app_secret"]),
        "FYERS_REDIRECT_URI_present": bool(settings["redirect_uri"]),
        "missing": missing
    })

@app.get("/login")
def login():
    settings = fyers_settings()
    missing = missing_settings(settings)
    if missing:
        return jsonify({
            "error": "Backend is not configured",
            "missing": missing,
            "hint": "Add the missing variables directly to the trader-vikki-scanner Web Service environment, save, and restart."
        }), 503

    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    params = {
        "client_id": settings["app_id"],
        "redirect_uri": settings["redirect_uri"],
        "response_type": "code",
        "state": state
    }
    return redirect(AUTH_URL + "?" + urlencode(params))

@app.get("/login/callback")
def callback():
    global access_token
    settings = fyers_settings()
    returned_state = request.args.get("state", "")
    expected_state = session.pop("oauth_state", "")
    auth_code = request.args.get("auth_code", "")

    if not expected_state or not secrets.compare_digest(returned_state, expected_state):
        return "Login state verification failed. Please return to the scanner and try again.", 400
    if not auth_code:
        return "FYERS did not return an authorization code. Please try connecting again.", 400

    missing = missing_settings(settings)
    if missing:
        return jsonify({"error": "Backend credentials missing", "missing": missing}), 503

    app_id_hash = hashlib.sha256(
        f'{settings["app_id"]}:{settings["app_secret"]}'.encode("utf-8")
    ).hexdigest()
    payload = {
        "grant_type": "authorization_code",
        "appIdHash": app_id_hash,
        "code": auth_code
    }
    try:
        response = requests.post(TOKEN_URL, json=payload, timeout=20)
        data = response.json()
    except Exception:
        return "Could not contact FYERS to complete login. Please try again later.", 502

    if data.get("s") != "ok" or not data.get("access_token"):
        return "FYERS login was not completed. Check the app permissions and redirect URL, then try again.", 400

    access_token = data["access_token"]
    return """<h2>FYERS connected successfully.</h2>
    <p>Your access token is held on the server for this session only.</p>
    <p>Return to the Trader Vikki Scanner home page.</p><a href="/">Open Scanner</a>"""

@app.get("/connection-status")
def connection_status():
    return jsonify({"connected": bool(access_token)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
