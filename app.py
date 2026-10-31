import os
import secrets
import hashlib
import requests
from flask import Flask, redirect, request, session, jsonify, render_template_string

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

FYERS_APP_ID = os.environ.get("FYERS_APP_ID", "").strip()
FYERS_APP_SECRET = os.environ.get("FYERS_APP_SECRET", "").strip()
# Set this to the exact callback URL registered in the FYERS dashboard.
FYERS_REDIRECT_URI = os.environ.get("FYERS_REDIRECT_URI", "").strip()

AUTH_URL = "https://api-t1.fyers.in/api/v3/generate-authcode"
TOKEN_URL = "https://api-t1.fyers.in/api/v3/validate-authcode"

# Access token is held only in server memory; it is not sent to the browser or logged.
access_token = None

PAGE = """
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trader Vikki Scanner</title>
<style>
body{font-family:Arial,sans-serif;background:#fffbea;margin:0;padding:20px;color:#172554}
.card{max-width:650px;margin:25px auto;background:white;padding:24px;border-radius:16px;box-shadow:0 3px 18px #0001}
h1{margin:0 0 8px;color:#1746a2} .tag{color:#555;margin-bottom:22px}
button{background:#1746a2;color:white;border:0;padding:13px 20px;border-radius:9px;font-size:16px}
.status{padding:12px;border-radius:8px;background:#f1f5f9;margin:18px 0}
small{color:#555}
</style></head><body><div class="card">
<h1>Trader Vikki Scanner</h1><div class="tag">FYERS secure connection setup</div>
<div class="status">{{ status }}</div>
{% if ready %}<a href="/login"><button>Connect FYERS</button></a>
{% else %}<p>Backend setup is incomplete. The app owner must add the FYERS credentials and callback URL as private environment variables in the hosting dashboard.</p>{% endif %}
<p><small>This setup requests market-data access only. It does not place trades.</small></p>
</div></body></html>
"""

@app.get("/")
def home():
    ready = bool(FYERS_APP_ID and FYERS_APP_SECRET and FYERS_REDIRECT_URI)
    if access_token:
        status = "FYERS connection established for this server session."
    elif ready:
        status = "Backend configured. Connect your FYERS account to continue."
    else:
        status = "Waiting for secure backend configuration."
    return render_template_string(PAGE, status=status, ready=ready)

@app.get("/health")
def health():
    return jsonify({"status": "ok", "app": "Trader Vikki Scanner"})

@app.get("/login")
def login():
    if not (FYERS_APP_ID and FYERS_APP_SECRET and FYERS_REDIRECT_URI):
        return "Backend is not configured. Set FYERS_APP_ID, FYERS_APP_SECRET and FYERS_REDIRECT_URI privately in the host environment.", 503
    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state
    params = {
        "client_id": FYERS_APP_ID,
        "redirect_uri": FYERS_REDIRECT_URI,
        "response_type": "code",
        "state": state
    }
    from urllib.parse import urlencode
    return redirect(AUTH_URL + "?" + urlencode(params))

@app.get("/login/callback")
def callback():
    global access_token
    returned_state = request.args.get("state", "")
    expected_state = session.pop("oauth_state", "")
    auth_code = request.args.get("auth_code", "")
    if not expected_state or not secrets.compare_digest(returned_state, expected_state):
        return "Login state verification failed. Please return to the scanner and try again.", 400
    if not auth_code:
        return "FYERS did not return an authorization code. Please try connecting again.", 400
    if not (FYERS_APP_ID and FYERS_APP_SECRET):
        return "Backend credentials are not configured.", 503

    app_id_hash = hashlib.sha256(
        f"{FYERS_APP_ID}:{FYERS_APP_SECRET}".encode("utf-8")
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
        # Do not display credentials or raw API response.
        return "FYERS login was not completed. Check the app permissions and try again.", 400

    access_token = data["access_token"]
    return """<h2>FYERS connected successfully.</h2>
    <p>Your connection is held securely on the server for this session.</p>
    <p>Return to the Trader Vikki Scanner home page.</p><a href="/">Open Scanner</a>"""

@app.get("/connection-status")
def connection_status():
    return jsonify({"connected": bool(access_token)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
