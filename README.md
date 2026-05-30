# AdC Roadmap Agent

Génère automatiquement une feuille de route HTML personnalisée après chaque appel de closing pour L'Académie des Coachs.

**Flow :**
```
Appel Fathom terminé
      ↓
Fathom → Webhook → webhook_bridge.py (hébergé)
      ↓
GitHub repository_dispatch
      ↓
GitHub Actions → generate.py
      ↓
Claude API (extraction + chantiers + HTML)
      ↓
Fichier HTML commité dans /output
```

---

## Setup (20 min)

### 1. Fork / clone ce repo sur ton GitHub

```bash
git clone https://github.com/TON-USERNAME/adc-roadmap-agent
cd adc-roadmap-agent
```

### 2. Ajouter les secrets GitHub

Dans ton repo → **Settings → Secrets → Actions → New repository secret** :

| Nom | Valeur |
|-----|--------|
| `FATHOM_API_KEY` | Clé API Fathom (Settings → API) |
| `ANTHROPIC_API_KEY` | Clé API Anthropic (console.anthropic.com) |

### 3. Tester en manuel

Aller dans **Actions → Generate AdC Roadmap → Run workflow**.

- Laisser `call_id` vide = prend le dernier appel AdC
- Ou coller un Fathom call ID spécifique

Le fichier HTML apparaîtra dans `/output/` après ~2 min.

### 4. Automatiser avec le webhook Fathom

**Héberger le webhook bridge** (gratuit sur Railway ou Render) :

#### Railway (recommandé, 1 clic)
1. [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Sélectionne ce repo
3. Start command : `python src/webhook_bridge.py`
4. Variables d'environnement à ajouter dans Railway :
   ```
   GITHUB_TOKEN=ghp_xxxx          # PAT avec scope repo
   GITHUB_REPO=ton-username/adc-roadmap-agent
   WEBHOOK_SECRET=un-secret-fort   # optionnel mais conseillé
   PORT=5000
   ```
5. Railway te donne une URL publique : `https://xxx.railway.app`

#### Render (alternative)
1. [render.com](https://render.com) → New Web Service → Connect GitHub
2. Build command : `pip install -r requirements.txt`
3. Start command : `python src/webhook_bridge.py`
4. Ajouter les mêmes variables d'environnement

---

**Créer le GitHub Personal Access Token :**
1. GitHub → Settings → Developer Settings → Personal access tokens → Tokens (classic)
2. Generate new token → scope : cocher `repo`
3. Copier le token `ghp_xxx`

---

**Configurer le webhook dans Fathom :**
1. Fathom → Settings → Integrations → Webhooks
2. URL : `https://ton-app.railway.app/webhook/fathom`
3. Events : `call.completed` (ou équivalent selon la version)
4. Secret : le même que `WEBHOOK_SECRET`

---

## Usage manuel (local)

```bash
pip install requests

export FATHOM_API_KEY="..."
export ANTHROPIC_API_KEY="..."

# Dernier appel AdC
python src/generate.py --latest

# Call spécifique
python src/generate.py --call-id "abc123"
```

Le fichier HTML est généré dans `./output/`.

---

## Filtrage AdC

Le bridge et le script filtrent les calls par mots-clés dans le titre/participants :
- académie des coachs
- adc
- maëlys / maelys
- lafrogne

Tu peux modifier la variable `ADC_KEYWORDS` dans `webhook_bridge.py` ou via la variable d'env du même nom.

---

## Structure du repo

```
├── .github/workflows/
│   └── generate-roadmap.yml   # GitHub Actions
├── src/
│   ├── generate.py            # Script principal
│   └── webhook_bridge.py      # Serveur Flask webhook → GitHub
├── output/                    # Fichiers HTML générés (commités auto)
├── requirements.txt
└── README.md
```
