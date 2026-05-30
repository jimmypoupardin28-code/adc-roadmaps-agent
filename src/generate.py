#!/usr/bin/env python3
"""
AdC Roadmap Generator — v2 (Fathom API corrigée)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests

FATHOM_API_BASE = "https://api.fathom.ai/external/v1"
ANTHROPIC_API_BASE = "https://api.anthropic.com/v1"
ADC_KEYWORDS = ["audit business avec poupardin", "audit business", "confirmé : audit"]
ADC_EXCLUDE = ["mise en place", "lead magnet", "impromptu", "kretz", "forge academy", "revolia", "1-1", "appel 1"]

FATHOM_KEY = os.environ["FATHOM_API_KEY"]
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]

HEADERS_FATHOM = {"X-Api-Key": FATHOM_KEY}
HEADERS_ANTHROPIC = {
    "x-api-key": ANTHROPIC_KEY,
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}


def list_meetings(limit=20):
    r = requests.get(
        f"{FATHOM_API_BASE}/meetings",
        headers=HEADERS_FATHOM,
        params={"limit": limit, "include_transcript": "true"},
        timeout=15
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
    raise ValueError("Aucun meeting AdC trouvé dans les 50 derniers.")


def get_meeting_by_id(meeting_id):
    r = requests.get(
        f"{FATHOM_API_BASE}/meetings",
        headers=HEADERS_FATHOM,
        params={"include_transcript": "true"},
        timeout=15
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    for m in items:
        if str(m.get("id", "")) == str(meeting_id):
            return m
    raise ValueError(f"Meeting {meeting_id} non trouvé.")


def claude(prompt, system=None, max_tokens=6000):
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        body["system"] = system
    r = requests.post(
        f"{ANTHROPIC_API_BASE}/messages",
        headers=HEADERS_ANTHROPIC,
        json=body,
        timeout=120
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"]


EXTRACTION_SYSTEM = """
Tu es un assistant d'analyse de calls de vente. Tu lis un meeting Fathom et tu retournes
UNIQUEMENT un JSON valide, sans markdown, sans backticks, sans commentaires.
"""

EXTRACTION_PROMPT = """
Analyse ce meeting de vente pour L'Académie des Coachs.

MEETING DATA:
{meeting_data}

Retourne EXACTEMENT ce JSON :
{{
  "prenom": "Prénom du prospect",
  "nom": "Nom du prospect",
  "driver_emotionnel": "Le mot/phrase exact que LE PROSPECT a employé pour décrire son objectif principal.",
  "point_a": {{
    "ca_mensuel": "chiffre exact en euros ou non mentionné",
    "situation_actuelle": "2-3 phrases factuelles",
    "deja_accompli": "ce qu'il a déjà fait",
    "audience": "taille audience si mentionnée",
    "offre_actuelle": "ce qu'il vend aujourd'hui",
    "nb_clients": "nombre de clients actifs si mentionné"
  }},
  "point_b": {{
    "objectif_principal": "son objectif principal",
    "delai": "délai visé ou non précisé",
    "vision_lifestyle": "ce qu'il veut vivre"
  }},
  "chantiers_raw": [
    "Problème 1", "Problème 2", "Problème 3", "Problème 4",
    "Problème 5", "Problème 6", "Problème 7", "Problème 8",
    "Problème 9", "Problème 10", "Problème 11", "Problème 12"
  ],
  "ca_level": "high ou low",
  "payment_plan": "ex 3x500 ou null",
  "objections_exprimees": ["objection 1", "objection 2"],
  "mots_cles_prospect": ["mot 1", "mot 2"],
  "niveau_chaleur": "chaud ou tiède ou froid",
  "potentiel_laisse_table": ["point 1", "point 2", "point 3"],
  "objections_cachees": ["objection 1", "objection 2", "objection 3"],
  "timing_r2": "recommendation timing R2"
}}
"""

CHANTIER_SYSTEM = """
Tu es expert en copywriting de vente premium. Tu reformules des problèmes en questions ouvertes
qui créent de la tension sans donner la solution.
Règle absolue : si le prospect peut résoudre seul après avoir lu la ligne, c'est mal écrit.
Retourne UNIQUEMENT un JSON valide, sans markdown.
"""

CHANTIER_PROMPT = """
Driver émotionnel : "{driver}"
Problèmes bruts :
{chantiers_raw}

Regroupe en 4 phases de 3 items. Chaque item = question ouverte ou problème non résolu. JAMAIS de solution.

Format JSON :
{{
  "phases": [
    {{
      "titre": "Titre court 3-5 mots",
      "items": ["question 1", "question 2", "question 3"],
      "outcome": "Ce qui change émotionnellement quand c'est réglé. 2 phrases max."
    }}
  ]
}}
"""


def extract_context(meeting):
    meeting_text = json.dumps(meeting, ensure_ascii=False)[:8000]
    raw = claude(
        EXTRACTION_PROMPT.format(meeting_data=meeting_text),
        system=EXTRACTION_SYSTEM,
        max_tokens=2000,
    )
    raw = re.sub(r"```json|```", "", raw).strip()
    return json.loads(raw)


def build_chantiers(ctx):
    raw_list = "\n".join(f"- {c}" for c in ctx["chantiers_raw"])
    raw = claude(
        CHANTIER_PROMPT.format(driver=ctx["driver_emotionnel"], chantiers_raw=raw_list),
        system=CHANTIER_SYSTEM,
        max_tokens=1500,
    )
    raw = re.sub(r"```json|```", "", raw).strip()
    return json.loads(raw)["phases"]


def build_html(ctx, phases):
    prenom = ctx["prenom"]
    nom = ctx["nom"]
    driver = ctx["driver_emotionnel"]
    pa = ctx["point_a"]
    pb = ctx["point_b"]
    ca_level = ctx["ca_level"]
    payment_plan = ctx.get("payment_plan")

    wa_msg = f"Bonjour, c'est {prenom}. J'ai lu ma feuille de route et je veux échanger."
    wa_url = f"https://wa.me/33756288802?text={quote(wa_msg)}"

    if ca_level == "high":
        featured_price, featured_label = "5 000€", "Accompagnement complet"
        featured_features = ["Plateforme + Slack + Lives", "3 mois de suivi 1-to-1", "Garantie 3-10k€/mois en 90 jours"]
        alt_price, alt_label = "1 500€", "Accès plateforme"
        alt_features = ["Plateforme + Slack + Lives", "Sans suivi 1-to-1", "Sans garantie"]
    else:
        featured_price, featured_label = "1 500€", "Accès plateforme"
        featured_features = ["Plateforme + Slack + Lives", "Upgrade possible", "Sans suivi 1-to-1"]
        alt_price, alt_label = "5 000€", "Accompagnement complet"
        alt_features = ["Plateforme + Slack + Lives", "3 mois de suivi 1-to-1", "Garantie 3-10k€/mois en 90 jours"]

    payment_html = f'<div class="payment-plan"><span class="payment-badge">Plan convenu</span><p>Paiement en {payment_plan}</p></div>' if payment_plan else '<p class="payment-note">Plans 3-4 fois disponibles sur les deux formules.</p>'

    diag_rows = ""
    for key, val in [
        ("CA mensuel actuel", pa.get("ca_mensuel", "Non mentionné")),
        ("Offre actuelle", pa.get("offre_actuelle", "Non mentionné")),
        ("Clients actifs", pa.get("nb_clients", "Non mentionné")),
        ("Audience", pa.get("audience", "Non mentionné")),
        ("Objectif", pb.get("objectif_principal", "Non mentionné")),
        ("Délai visé", pb.get("delai", "Non précisé")),
    ]:
        diag_rows += f'<tr><td class="diag-key">{key}</td><td class="diag-val">{val}</td></tr>'

    phases_html = ""
    for i, phase in enumerate(phases, 1):
        items_html = "".join(f"<li>{item}</li>" for item in phase["items"])
        phases_html += f"""
        <div class="phase">
          <div class="phase-header">
            <span class="period-label">Chantier</span>
            <div class="phase-num">{i:02d}</div>
            <h3 class="phase-title">{phase['titre']}</h3>
          </div>
          <ul class="phase-items">{items_html}</ul>
          <div class="outcome-block">
            <p class="outcome-header">Quand c'est réglé</p>
            <p class="outcome-text">{phase['outcome']}</p>
          </div>
        </div>"""

    feat_html = "".join(f"<li>{f}</li>" for f in featured_features)
    alt_feat_html = "".join(f"<li>{f}</li>" for f in alt_features)

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Feuille de route — {prenom} {nom}</title>
<style>
  :root {{
    --red: #C0272D; --red-soft: rgba(192,39,45,0.15); --red-glow: rgba(192,39,45,0.35);
    --black: #1A1A1A; --bg: #0A0A0B; --glass: rgba(255,255,255,0.04);
    --glass-border: rgba(255,255,255,0.08); --text: #E8E8E8; --muted: rgba(232,232,232,0.45);
    --font: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--font); font-weight: 300; line-height: 1.6; -webkit-font-smoothing: antialiased; }}
  .orb {{ position: fixed; border-radius: 50%; filter: blur(80px); pointer-events: none; z-index: 0; opacity: 0.18; }}
  .orb-1 {{ width: 320px; height: 320px; background: var(--red); top: -80px; right: -80px; }}
  .orb-2 {{ width: 200px; height: 200px; background: var(--red); bottom: 20%; left: -60px; opacity: 0.1; }}
  .container {{ max-width: 460px; margin: 0 auto; padding: 0 20px 60px; position: relative; z-index: 1; }}
  .header {{ padding: 52px 0 32px; border-bottom: 1px solid var(--glass-border); margin-bottom: 32px; }}
  .header-tag {{ font-size: 10px; font-weight: 500; letter-spacing: 0.2em; text-transform: uppercase; color: var(--red); margin-bottom: 16px; }}
  .header h1 {{ font-size: 26px; font-weight: 200; line-height: 1.3; margin-bottom: 16px; }}
  .header h1 em {{ font-style: normal; color: var(--red); font-weight: 400; }}
  .header-sub {{ font-size: 13px; color: var(--muted); }}
  .glass-card {{ background: var(--glass); border: 1px solid var(--glass-border); border-radius: 16px; padding: 24px; margin-bottom: 32px; }}
  .glass-card p {{ font-size: 14px; margin-bottom: 12px; }}
  .glass-card p:last-child {{ margin-bottom: 0; }}
  .glass-card p strong {{ font-weight: 500; color: #fff; }}
  .section-tag {{ font-size: 10px; font-weight: 500; letter-spacing: 0.2em; text-transform: uppercase; color: var(--red); margin-bottom: 8px; }}
  .section-title {{ font-size: 20px; font-weight: 300; margin-bottom: 24px; }}
  .section-title em {{ font-style: normal; color: var(--red); }}
  .vision-list {{ list-style: none; margin-bottom: 32px; }}
  .vision-list li {{ padding: 14px 0; border-bottom: 1px solid var(--glass-border); font-size: 14px; display: flex; align-items: flex-start; gap: 12px; }}
  .vision-list li::before {{ content: '→'; color: var(--red); font-size: 12px; margin-top: 2px; flex-shrink: 0; }}
  .diag-table {{ width: 100%; border-collapse: collapse; margin-bottom: 32px; }}
  .diag-table tr {{ border-bottom: 1px solid var(--glass-border); }}
  .diag-key {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em; padding: 12px 0; width: 45%; vertical-align: top; }}
  .diag-val {{ font-size: 14px; color: var(--text); padding: 12px 0 12px 12px; }}
  .phase {{ border: 1px solid var(--glass-border); border-radius: 16px; padding: 24px; margin-bottom: 16px; background: var(--glass); }}
  .period-label {{ font-size: 9px; font-weight: 500; letter-spacing: 0.25em; text-transform: uppercase; color: var(--red); display: block; margin-bottom: 8px; }}
  .phase-num {{ display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; background: var(--red); color: #fff; border-radius: 50%; font-size: 12px; font-weight: 500; margin-bottom: 10px; }}
  .phase-title {{ font-size: 16px; font-weight: 400; color: #fff; margin-bottom: 16px; }}
  .phase-items {{ list-style: none; margin-bottom: 20px; }}
  .phase-items li {{ font-size: 13px; padding: 10px 0 10px 16px; border-bottom: 1px solid rgba(255,255,255,0.05); position: relative; line-height: 1.5; }}
  .phase-items li::before {{ content: ''; position: absolute; left: 0; top: 17px; width: 5px; height: 5px; border-radius: 50%; background: var(--red); opacity: 0.6; }}
  .outcome-block {{ background: var(--red-soft); border: 1px solid var(--red-glow); border-radius: 10px; padding: 14px 16px; }}
  .outcome-header {{ font-size: 10px; font-weight: 500; letter-spacing: 0.15em; text-transform: uppercase; color: var(--red); margin-bottom: 6px; }}
  .outcome-text {{ font-size: 13px; color: rgba(232,232,232,0.8); line-height: 1.5; }}
  .eco-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 32px; }}
  .eco-item {{ background: var(--glass); border: 1px solid var(--glass-border); border-radius: 12px; padding: 16px; text-align: center; }}
  .eco-icon {{ font-size: 20px; margin-bottom: 8px; display: block; }}
  .eco-name {{ font-size: 12px; font-weight: 500; color: #fff; display: block; margin-bottom: 4px; }}
  .eco-desc {{ font-size: 11px; color: var(--muted); line-height: 1.4; }}
  .proofs-wrap {{ display: flex; flex-direction: column; align-items: center; gap: 12px; margin-bottom: 32px; }}
  .proofs {{ list-style: none; width: 100%; }}
  .proofs li {{ padding: 14px 0; border-bottom: 1px solid var(--glass-border); display: flex; justify-content: space-between; align-items: center; font-size: 14px; }}
  .proof-name {{ font-weight: 400; color: #fff; }}
  .proof-val {{ color: var(--red); font-weight: 500; font-size: 16px; }}
  .proofs-cta {{ display: inline-flex; align-items: center; gap: 8px; padding: 12px 24px; background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.12); border-radius: 100px; color: var(--text); font-family: var(--font); font-size: 13px; text-decoration: none; transition: background 0.2s, border-color 0.2s; }}
  .proofs-cta .arrow {{ transition: transform 0.2s; }}
  .proofs-cta:hover {{ background: rgba(192,39,45,0.12); border-color: rgba(192,39,45,0.4); color: #fff; }}
  .proofs-cta:hover .arrow {{ transform: translate(2px,-2px); }}
  .offer-featured {{ background: var(--glass); border: 1px solid var(--red); border-radius: 16px; padding: 24px; margin-bottom: 12px; position: relative; overflow: hidden; }}
  .offer-featured::before {{ content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: var(--red); }}
  .offer-alt {{ background: var(--glass); border: 1px solid var(--glass-border); border-radius: 16px; padding: 20px 24px; margin-bottom: 16px; opacity: 0.75; }}
  .offer-badge {{ font-size: 9px; font-weight: 500; letter-spacing: 0.2em; text-transform: uppercase; color: var(--red); margin-bottom: 8px; }}
  .offer-price {{ font-size: 28px; font-weight: 300; color: #fff; margin-bottom: 4px; }}
  .offer-label {{ font-size: 12px; color: var(--muted); margin-bottom: 16px; }}
  .offer-features {{ list-style: none; }}
  .offer-features li {{ font-size: 13px; padding: 6px 0 6px 16px; position: relative; }}
  .offer-features li::before {{ content: '✓'; position: absolute; left: 0; color: var(--red); font-size: 11px; }}
  .payment-plan {{ background: var(--red-soft); border: 1px solid var(--red-glow); border-radius: 10px; padding: 14px 16px; margin-bottom: 16px; display: flex; gap: 12px; align-items: center; }}
  .payment-badge {{ font-size: 9px; font-weight: 500; letter-spacing: 0.15em; text-transform: uppercase; color: var(--red); white-space: nowrap; }}
  .payment-plan p {{ font-size: 13px; margin: 0; }}
  .payment-note {{ font-size: 12px; color: var(--muted); text-align: center; margin-bottom: 16px; }}
  .closing {{ text-align: center; padding: 40px 0 20px; }}
  .closing-title {{ font-size: 22px; font-weight: 300; margin-bottom: 20px; line-height: 1.4; }}
  .closing-title em {{ font-style: normal; color: var(--red); }}
  .closing-body {{ font-size: 14px; color: var(--muted); margin-bottom: 32px; line-height: 1.7; }}
  .cta-btn {{ display: inline-flex; align-items: center; gap: 10px; background: var(--red); color: #fff; font-family: var(--font); font-size: 15px; text-decoration: none; padding: 16px 32px; border-radius: 100px; transition: background 0.2s; }}
  .cta-btn:hover {{ background: #a01f24; }}
  .footer {{ border-top: 1px solid var(--glass-border); padding-top: 24px; text-align: center; font-size: 11px; color: var(--muted); }}
  section {{ margin-bottom: 48px; }}
</style>
</head>
<body>
<div class="orb orb-1"></div>
<div class="orb orb-2"></div>
<div class="container">
  <header class="header">
    <p class="header-tag">L'Académie des Coachs · Feuille de route</p>
    <h1>Tout ce qu'il reste à régler pour atteindre <em>{driver}</em>.</h1>
    <p class="header-sub">Pas un argumentaire. Voilà ce que j'ai retenu, voilà le chemin qu'il reste.</p>
  </header>
  <div class="glass-card">
    <p><strong>Où tu en es.</strong> {pa.get('situation_actuelle', '')}</p>
    <p><strong>Ce que tu as déjà prouvé.</strong> {pa.get('deja_accompli', '')}</p>
    <p>Ce doc, c'est le pont entre les deux. On en reparle au call.</p>
  </div>
  <section>
    <p class="section-tag">01</p>
    <h2 class="section-title">Ton point B — <em>{driver}</em></h2>
    <ul class="vision-list">
      <li>{pb.get('objectif_principal', '')}</li>
      <li>{pb.get('vision_lifestyle', '')}</li>
      <li>Un revenu qui tient sans que tu portes tout à bout de bras.</li>
      <li>La liberté de choisir avec qui tu travailles — et pourquoi.</li>
    </ul>
  </section>
  <section>
    <p class="section-tag">02</p>
    <h2 class="section-title">Ton point A — les faits.</h2>
    <table class="diag-table">{diag_rows}</table>
  </section>
  <section>
    <p class="section-tag">03</p>
    <h2 class="section-title">Les chantiers entre toi et <em>{driver}</em>.</h2>
    {phases_html}
  </section>
  <section>
    <p class="section-tag">04</p>
    <h2 class="section-title">L'écosystème AdC.</h2>
    <div class="eco-grid">
      <div class="eco-item"><span class="eco-icon">🎓</span><span class="eco-name">Plateforme</span><span class="eco-desc">Modules, templates, ressources</span></div>
      <div class="eco-item"><span class="eco-icon">💬</span><span class="eco-name">Slack</span><span class="eco-desc">Communauté active</span></div>
      <div class="eco-item"><span class="eco-icon">📡</span><span class="eco-name">Lives</span><span class="eco-desc">Sessions hebdo avec Maëlys</span></div>
      <div class="eco-item"><span class="eco-icon">🤝</span><span class="eco-name">Partenaires</span><span class="eco-desc">Réseau et opportunités</span></div>
      <div class="eco-item"><span class="eco-icon">⚡</span><span class="eco-name">Maëlys</span><span class="eco-desc">Accès direct, expertise terrain</span></div>
      <div class="eco-item"><span class="eco-icon">🔥</span><span class="eco-name">Cohorte</span><span class="eco-desc">Promos actives, émulation</span></div>
    </div>
  </section>
  <section>
    <p class="section-tag">05</p>
    <h2 class="section-title">Ce que ça donne — en chiffres.</h2>
    <div class="proofs-wrap">
      <ul class="proofs">
        <li><span class="proof-name">Manon</span><span class="proof-val" data-target="150000">0€</span></li>
        <li><span class="proof-name">Emmerick — janvier</span><span class="proof-val" data-target="15000">0€</span></li>
        <li><span class="proof-name">Emmerick + équipe — février</span><span class="proof-val" data-target="19000">0€</span></li>
        <li><span class="proof-name">Aurélie — 1 semaine</span><span class="proof-val" data-target="7000">0€</span></li>
        <li><span class="proof-name">Nouvelle coach — 1 mois (0)</span><span class="proof-val" data-target="3300">0€</span></li>
      </ul>
      <a class="proofs-cta" href="https://drive.google.com/drive/folders/1fk6fHzGKUbFWrXez6Cm4EPabMdCrkd0V" target="_blank" rel="noopener">Voir tous les témoignages <span class="arrow">↗</span></a>
    </div>
  </section>
  <section>
    <p class="section-tag">06</p>
    <h2 class="section-title">Ton accès.</h2>
    <div class="offer-featured">
      <p class="offer-badge">Recommandé pour toi</p>
      <p class="offer-price">{featured_price}</p>
      <p class="offer-label">{featured_label}</p>
      <ul class="offer-features">{feat_html}</ul>
    </div>
    <div class="offer-alt">
      <p class="offer-badge">Alternative</p>
      <p class="offer-price">{alt_price}</p>
      <p class="offer-label">{alt_label}</p>
      <ul class="offer-features">{alt_feat_html}</ul>
    </div>
    {payment_html}
  </section>
  <section class="closing">
    <h2 class="closing-title">Alors <em>{prenom}</em>, qu'est-ce que t'attends&nbsp;?</h2>
    <p class="closing-body">Tu sais où t'en es. Tu sais où tu veux aller. Tu sais ce qu'il reste à régler.<br><br>Dans 6 mois, soit tu y es, soit t'es encore là à regarder le chemin.<br>La seule chose qui change : la décision que tu prends maintenant.</p>
    <a href="{wa_url}" target="_blank" rel="noopener" class="cta-btn"><span>Je suis prêt, on lance</span><span>→</span></a>
  </section>
  <footer class="footer"><p>L'Académie des Coachs · Document préparé pour {prenom} {nom}</p></footer>
</div>
<script>
const proofVals = document.querySelectorAll('.proof-val[data-target]');
const io = new IntersectionObserver((entries) => {{
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      const target = parseInt(e.target.dataset.target);
      const start = performance.now();
      const step = (now) => {{
        const p = Math.min((now-start)/1400,1);
        const ease = 1-Math.pow(1-p,3);
        e.target.textContent = Math.round(ease*target).toLocaleString('fr-FR')+'€';
        if(p<1) requestAnimationFrame(step);
      }};
      requestAnimationFrame(step);
      io.unobserve(e.target);
    }}
  }});
}}, {{threshold:0.5}});
proofVals.forEach(el => io.observe(el));
</script>
</body>
</html>"""


def print_analysis(ctx):
    print("\n" + "="*60)
    print("ANALYSE POST-CALL")
    print("="*60)
    print(f"\n Chaleur : {ctx.get('niveau_chaleur','N/A').upper()}")
    print("\n Potentiel laisse sur la table :")
    for p in ctx.get("potentiel_laisse_table", []):
        print(f"   . {p}")
    print("\n Objections cachees a pre-traiter :")
    for o in ctx.get("objections_cachees", []):
        print(f"   . {o}")
    print(f"\n Timing R2 : {ctx.get('timing_r2','N/A')}")
    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--call-id")
    group.add_argument("--latest", action="store_true")
    args = parser.parse_args()

    print("Recuperation du meeting Fathom...")
    if args.call_id:
        meeting = get_meeting_by_id(args.call_id)
    else:
        meeting = find_latest_adc_meeting()

    print(f"Meeting : {meeting.get('title', 'Sans titre')}")
    print("Extraction contexte via Claude...")
    ctx = extract_context(meeting)
    print(f"Prospect : {ctx['prenom']} {ctx['nom']} | Driver : {ctx['driver_emotionnel']}")

    print("Construction des chantiers...")
    phases = build_chantiers(ctx)

    print("Generation HTML...")
    html = build_html(ctx, phases)

    output_dir = Path(os.environ.get("OUTPUT_DIR", "output"))
    output_dir.mkdir(exist_ok=True)
    prenom_slug = ctx["prenom"].lower().replace(" ", "-")
    nom_slug = ctx["nom"].lower().replace(" ", "-")
    filename = f"feuille-de-route-{prenom_slug}-{nom_slug}.html"
    out_path = output_dir / filename
    out_path.write_text(html, encoding="utf-8")
    print(f"Fichier : {out_path}")

    url_publique = f"https://roadmaps.jimmycorp.fit/output/{filename}"

    url_path = output_dir / "DERNIERE-URL.txt"
    url_path.write_text(url_publique, encoding="utf-8")

    historique_path = output_dir / "HISTORIQUE-URLS.txt"
    ligne = f"{datetime.now().strftime('%Y-%m-%d %H:%M')} | {ctx['prenom']} {ctx['nom']} | {url_publique}\n"
    with open(historique_path, "a", encoding="utf-8") as f:
        f.write(ligne)

    print(f"URL publique : {url_publique}")
    print_analysis(ctx)

    analysis_path = output_dir / f"analysis-{prenom_slug}-{nom_slug}.json"
    analysis_path.write_text(json.dumps({
        "niveau_chaleur": ctx.get("niveau_chaleur"),
        "potentiel_laisse_table": ctx.get("potentiel_laisse_table"),
        "objections_cachees": ctx.get("objections_cachees"),
        "timing_r2": ctx.get("timing_r2"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
