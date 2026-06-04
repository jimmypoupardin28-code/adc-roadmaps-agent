#!/usr/bin/env python3
"""
AdC Roadmap Generator — v4
Claude génère le HTML complet via le prompt exact de Jimmy.
"""

import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

import requests

FATHOM_API_BASE = "https://api.fathom.ai/external/v1"
ANTHROPIC_API_BASE = "https://api.anthropic.com/v1"

ADC_KEYWORDS = ["audit business avec poupardin", "audit business", "confirmé : audit", "unknown"]
ADC_EXCLUDE = ["mise en place", "lead magnet", "impromptu", "kretz", "forge academy", "revolia", "1-1", "appel 1"]

FATHOM_KEY = os.environ["FATHOM_API_KEY"]
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]

HEADERS_FATHOM = {"X-Api-Key": FATHOM_KEY}
HEADERS_ANTHROPIC = {
    "x-api-key": ANTHROPIC_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}


def list_meetings(limit=50):
    r = requests.get(
        f"{FATHOM_API_BASE}/meetings",
        headers=HEADERS_FATHOM,
        params={"limit": limit, "include_transcript": "true"},
        timeout=30
    )
    r.raise_for_status()
    return r.json().get("items", [])


def is_adc_meeting(meeting):
    haystack = json.dumps(meeting).lower()
    matches = any(kw in haystack for kw in ADC_KEYWORDS)
    excluded = any(kw in haystack for kw in ADC_EXCLUDE)
    return matches and not excluded


def find_latest_adc_meeting():
    meetings = list_meetings(50)
    for m in meetings:
        if is_adc_meeting(m):
            return m
    raise ValueError("Aucun meeting AdC trouve dans les 50 derniers.")


def get_meeting_by_id(meeting_id):
    meetings = list_meetings(50)
    for m in meetings:
        if str(m.get("id", "")) == str(meeting_id):
            return m
    raise ValueError(f"Meeting {meeting_id} non trouve.")


def claude(prompt, system=None, max_tokens=8000):
    body = {
        "model": "claude-sonnet-4-5",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system
    r = requests.post(
        f"{ANTHROPIC_API_BASE}/messages",
        headers=HEADERS_ANTHROPIC,
        json=body,
        timeout=180
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"]


SYSTEM_PROMPT = """Tu es un expert en copywriting de vente premium pour L'Académie des Coachs.
Tu génères des feuilles de route HTML personnalisées post-appel de closing.
Tu retournes UNIQUEMENT du code HTML valide, sans markdown, sans backticks, sans commentaires avant ou après.
Le HTML doit commencer par <!DOCTYPE html> et finir par </html>."""

MAIN_PROMPT = """Génère une feuille de route HTML personnalisée pour le prospect dont voici les données d'appel Fathom.

DONNÉES DU CALL :
{meeting_data}

PHILOSOPHIE DU DOC — LE PLUS IMPORTANT :
Ce doc n'est PAS un livrable de valeur. Il ne donne PAS de solutions.
Il fait 3 choses, dans cet ordre :
   1. Refléter au prospect SA situation actuelle (point A) avec précision
   2. Lister les CHANTIERS qui le séparent de son point B — sous forme de questions ouvertes qu'il ne sait pas résoudre seul
   3. Lui donner envie de SIGNER pour obtenir les réponses

Règle d'or : chaque "chantier" doit être formulé comme une question/problème, PAS comme une solution.
Le prospect doit finir sa lecture en pensant "je vois le chemin mais j'ai pas les clés — j'ai besoin d'eux".

Test du chantier bien écrit : si le prospect pouvait le résoudre seul après avoir lu cette ligne, c'est mal écrit.

EXEMPLES :
❌ "Construire ton offre signature à 250-350€/mois" (= solution livrée)
✅ "À quel tarif tu deviens crédible sans être hors de portée — et comment tu fais le saut sans perdre ceux que t'as déjà" (= chantier ouvert)

❌ "Reels structurés avec couche d'expertise" (= recette donnée)
✅ "Comment ton humour rapporte des clients sans dénaturer ce qui te ressemble" (= question vraie)

INSTRUCTIONS :
1. Identifie le DRIVER ÉMOTIONNEL #1 du prospect — le mot/phrase EXACT qu'IL a employé pour décrire ce qu'il veut. Ce mot devient le fil rouge du doc. Utilise SES mots verbatim.
2. Génère un HTML mobile-first (max-width 460px), single-file, charte AdC.

DESIGN :
— Couleurs : rouge #C0272D, noir #1A1A1A, blanc, fond #0A0A0B
— Typo : Helvetica Neue uniquement, weight 200-500
— Style : glass morphism subtil, orbes rouges floutés, count-up sur les chiffres au scroll
— Pas de dégradés baveux. Pas de polices décoratives.

STRUCTURE OBLIGATOIRE :

HEADER — Titre : "Tout ce qu'il reste à régler pour atteindre [DRIVER ÉMOTIONNEL EN ROUGE]."
Sous-titre : "Pas un argumentaire. Voilà ce que j'ai retenu, voilà le chemin qu'il reste."

INTRO (encadré glass) — 3 paragraphes :
· Son point A actuel (chiffres exacts, faits du call)
· Ce qu'il a déjà accompli (preuve qu'il est capable)
· "Ce doc c'est le pont. On en reparle au call."

01 — TON POINT B
4 vision items avec son driver émotionnel en #1. Utiliser SES mots.

02 — TON POINT A
Tableau clé/valeur avec SES chiffres exacts du call. Pas de "non mentionné" — si pas dit, trouve une reformulation de ce qui a été dit.

03 — CE QU'IL TE RESTE À RÉGLER
Titre : "Les chantiers entre toi et [son driver émotionnel]."
4 phases numérotées badge rouge.
AUCUNE TEMPORALITÉ. Le label au-dessus du titre = juste "Chantier".
Chaque phase : 3 items formulés comme questions ouvertes / problèmes non résolus, jamais comme solutions.
Bloc outcome à la fin de chaque phase : "Quand c'est réglé" + ce qui change émotionnellement pour LUI.

04 — L'ÉCOSYSTÈME AdC (fixe)
Grid 2 col : Plateforme, Slack, Lives, Partenaires, Maëlys, Cohorte.

05 — RÉSULTATS COMMUNAUTÉ (fixe)
Count-up au scroll :
· Manon — 150 000€
· Emmerick — 15 000€ en janvier
· Emmerick + équipe — 19 000€ en février
· Aurélie — 7 000€ en une semaine
· Nouvelle coach — 3 300€ en 1 mois partie de 0
Bouton pill "Voir tous les témoignages" → https://drive.google.com/drive/folders/1fk6fHzGKUbFWrXez6Cm4EPabMdCrkd0V

06 — TON ACCÈS
Deux formules :
· 5 000€ — plateforme + Slack + lives + 3 mois 1-to-1 + garantie 3-10k€/mois en 90 jours
· 1 500€ — plateforme + Slack + lives (sans 1-to-1, sans garantie)
Si CA solide (3k€+/mois) → 5 000€ en featured. Sinon → 1 500€ en featured.
Plans 3-4 fois disponibles.

CLOSING
Titre : "Alors [PRÉNOM], qu'est-ce que t'attends ?"
Corps : "Tu sais où t'en es. Tu sais où tu veux aller. Tu sais ce qu'il reste à régler. Dans 6 mois, soit tu y es, soit t'es encore là. La seule chose qui change : la décision que tu prends maintenant." (adapter au driver émotionnel)
Bouton WhatsApp : https://wa.me/33756288802?text=Bonjour%2C%20c%27est%20[PRÉNOM%20URL-ENCODÉ].%20J%27ai%20lu%20ma%20feuille%20de%20route%20et%20je%20veux%20%C3%A9changer.
Texte bouton : "Je suis prêt, on lance"

FOOTER : "L'Académie des Coachs · Document préparé pour [Prénom Nom]"

RÈGLES DE TON :
— Tutoiement direct. Zéro flagornerie.
— Refléter SES mots. Pas inventer.
— Pas plus de 1 phrase >25 mots. Sec, premium, lisible mobile.
— JAMAIS livrer la solution. Toujours laisser la question ouverte.

IMPORTANT : Retourne UNIQUEMENT le code HTML complet. Commence par <!DOCTYPE html> et termine par </html>. Aucun texte avant ou après."""

ANALYSIS_PROMPT = """Sur la base de ce call Fathom, retourne UNIQUEMENT un JSON valide (sans markdown) :

MEETING DATA:
{meeting_data}

Format :
{{
  "prenom": "prénom du prospect",
  "nom": "nom du prospect",
  "niveau_chaleur": "chaud ou tiede ou froid",
  "potentiel_laisse_table": ["point 1", "point 2", "point 3"],
  "objections_cachees": ["objection 1", "objection 2", "objection 3"],
  "timing_r2": "recommendation timing R2",
  "message_whatsapp": "Message WhatsApp personnalisé. Tutoiement. 4-6 lignes. Mentionne un détail spécifique du call. CTA clair pour lire le doc. Pas de flagornerie. Termine par une phrase sur le R2."
}}"""


def extract_names_from_html(html):
    """Extrait prénom et nom depuis le HTML généré."""
    match = re.search(r"Document préparé pour ([A-ZÀ-Ÿa-zà-ÿ]+)\s+([A-ZÀ-Ÿa-zà-ÿ]+)", html)
    if match:
        return match.group(1).lower(), match.group(2).lower()
    # Fallback depuis le title
    match = re.search(r"<title>.*?- ([A-ZÀ-Ÿa-zà-ÿ]+)\s+([A-ZÀ-Ÿa-zà-ÿ]+)</title>", html)
    if match:
        return match.group(1).lower(), match.group(2).lower()
    return "prospect", "inconnu"


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--call-id")
    group.add_argument("--latest", action="store_true")
    args = parser.parse_args()

    print("Récupération du meeting Fathom...")
    if args.call_id:
        meeting = get_meeting_by_id(args.call_id)
    else:
        meeting = find_latest_adc_meeting()

    print(f"Meeting : {meeting.get('title', 'Sans titre')}")

    meeting_text = json.dumps(meeting, ensure_ascii=False)

    print("Génération HTML par Claude Sonnet (prompt complet)...")
    html = claude(
        MAIN_PROMPT.format(meeting_data=meeting_text),
        system=SYSTEM_PROMPT,
        max_tokens=8000
    )

    # Nettoyer les éventuels backticks
    html = re.sub(r"^```html\s*", "", html.strip())
    html = re.sub(r"\s*```$", "", html.strip())

    print("Extraction analyse post-call...")
    analysis_raw = claude(
        ANALYSIS_PROMPT.format(meeting_data=meeting_text),
        max_tokens=1500
    )
    analysis_raw = re.sub(r"```json|```", "", analysis_raw).strip()
    try:
        analysis = json.loads(analysis_raw)
    except Exception:
        analysis = {"prenom": "prospect", "nom": "inconnu", "niveau_chaleur": "N/A",
                    "potentiel_laisse_table": [], "objections_cachees": [],
                    "timing_r2": "N/A", "message_whatsapp": ""}

    prenom = analysis.get("prenom", "prospect").lower().replace(" ", "-")
    nom = analysis.get("nom", "inconnu").lower().replace(" ", "-")

    output_dir = Path(os.environ.get("OUTPUT_DIR", "output"))
    output_dir.mkdir(exist_ok=True)

    prospect_dir = output_dir / f"{prenom}-{nom}"
    prospect_dir.mkdir(exist_ok=True)
    out_path = prospect_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Fichier : {out_path}")

    url_publique = f"https://roadmaps.jimmycorp.fit/output/{prenom}-{nom}/"

    (output_dir / "DERNIERE-URL.txt").write_text(url_publique, encoding="utf-8")

    historique_path = output_dir / "HISTORIQUE-URLS.txt"
    ligne = f"{datetime.now().strftime('%Y-%m-%d %H:%M')} | {analysis.get('prenom','')} {analysis.get('nom','')} | {url_publique}\n"
    with open(historique_path, "a", encoding="utf-8") as f:
        f.write(ligne)

    message_wa = analysis.get("message_whatsapp", "")
    (output_dir / "DERNIER-MESSAGE-WA.txt").write_text(message_wa, encoding="utf-8")

    analysis_path = output_dir / f"analysis-{prenom}-{nom}.json"
    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2))

    print(f"\nURL publique : {url_publique}")
    print("\n" + "="*60)
    print("ANALYSE POST-CALL")
    print("="*60)
    print(f"Chaleur : {analysis.get('niveau_chaleur','N/A').upper()}")
    print(f"Timing R2 : {analysis.get('timing_r2','N/A')}")
    print("Potentiel laissé sur la table :")
    for p in analysis.get("potentiel_laisse_table", []):
        print(f"  - {p}")
    print("Objections cachées :")
    for o in analysis.get("objections_cachees", []):
        print(f"  - {o}")
    print("="*60)


if __name__ == "__main__":
    main()
