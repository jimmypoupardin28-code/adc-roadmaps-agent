"""
webhook_bridge.py
─────────────────
Reçoit les webhooks Fathom (call.completed) et déclenche le GitHub Actions workflow
via repository_dispatch.

Déploiement : Railway, Render, ou n'importe quel hébergeur Python gratuit.
Variables d'environnement requises :
  GITHUB_TOKEN       — Personal Access Token avec scope repo
  GITHUB_REPO        — ex: jimmy-dupont/adc-roadmap-agent
  WEBHOOK_SECRET     — secret partagé avec Fathom (optionnel mais recommandé)
  ADC_KEYWORDS       — mots-clés séparés par virgule (défaut: academie,adc,maelys)
"""

import hashlib
import hmac
import json
import os

import requests
from flask import Flask, abort, jsonify, request

app = Flask(__name__)

GITHUB_TOKEN = os.environ["GITHUB_TOKEN"]
GITHUB_REPO = os.environ["GITHUB_REPO"]          # "username/repo-name"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
ADC_KEYWORDS = [k.strip().lower() for k in os.environ.get(
    "ADC_KEYWORDS", "académie des coachs,academie des coachs,adc,maëlys,maelys,lafrogne"
).split(",")]


def verify_signature(payload: bytes, sig_header: str) -> bool:
    if not WEBHOOK_SECRET:
        return True
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, sig_header or "")


def is_adc_call(payload: dict) -> bool:
    haystack = json.dumps(payload).lower()
    return any(kw in haystack for kw in ADC_KEYWORDS)


def trigger_github_action(call_id: str):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/dispatches"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = {
        "event_type": "fathom_call_completed",
        "client_payload": {"call_id": call_id},
    }
    r = requests.post(url, headers=headers, json=body, timeout=10)
    r.raise_for_status()
    return r.status_code


@app.route("/webhook/fathom", methods=["POST"])
def fathom_webhook():
    payload_bytes = request.get_data()
    sig = request.headers.get("X-Fathom-Signature", "")

    if not verify_signature(payload_bytes, sig):
        abort(401, "Invalid signature")

    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError:
        abort(400, "Invalid JSON")

    event_type = payload.get("event") or payload.get("type", "")

    # Only process call completion events
    if "call" not in event_type.lower() and "recording" not in event_type.lower():
        return jsonify({"status": "ignored", "reason": "not a call event"}), 200

    # Filter to AdC calls only
    if not is_adc_call(payload):
        return jsonify({"status": "ignored", "reason": "not an AdC call"}), 200

    # Extract call ID (Fathom may use different field names)
    call_id = (
        payload.get("call_id")
        or payload.get("id")
        or (payload.get("call") or {}).get("id")
        or (payload.get("data") or {}).get("id")
    )

    if not call_id:
        abort(422, "Could not extract call_id from payload")

    status_code = trigger_github_action(str(call_id))
    return jsonify({
        "status": "triggered",
        "call_id": call_id,
        "github_status": status_code,
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
