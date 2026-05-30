#!/usr/bin/env python3
"""
Script d'envoi d'email post-generation
"""
import smtplib
import os
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

password = os.environ["GMAIL_APP_PASSWORD"]

url = Path("output/DERNIERE-URL.txt").read_text(encoding="utf-8").strip()
wa_msg = Path("output/DERNIER-MESSAGE-WA.txt").read_text(encoding="utf-8").strip()

analysis_files = list(Path("output").glob("analysis-*.json"))
analysis = {}
if analysis_files:
    latest = max(analysis_files, key=lambda f: f.stat().st_mtime)
    analysis = json.loads(latest.read_text(encoding="utf-8"))

chaleur = analysis.get("niveau_chaleur", "N/A").upper()
timing = analysis.get("timing_r2", "N/A")
potentiel = "\n".join(f"  - {p}" for p in analysis.get("potentiel_laisse_table", []))
objections = "\n".join(f"  - {o}" for o in analysis.get("objections_cachees", []))

prospect_slug = url.split("/")[-1]

body = f"""NOUVELLE FEUILLE DE ROUTE GENEREE
==========================================

LIEN A ENVOYER AU PROSPECT :
{url}

==========================================
MESSAGE WHATSAPP (copie-colle directement) :

{wa_msg}

==========================================
ANALYSE DU CALL :

Niveau de chaleur : {chaleur}
Timing R2 recommande : {timing}

Potentiel laisse sur la table :
{potentiel}

Objections cachees a pre-traiter en R2 :
{objections}

==========================================
"""

msg = MIMEMultipart()
msg["From"] = "jimmy.poupardin28@gmail.com"
msg["To"] = "jimmy.poupardin28@gmail.com"
msg["Subject"] = f"Roadmap generee - {prospect_slug}"
msg.attach(MIMEText(body, "plain", "utf-8"))

with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    server.login("jimmy.poupardin28@gmail.com", password)
    server.send_message(msg)

print("Email envoye !")
