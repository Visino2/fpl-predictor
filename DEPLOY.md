# Deploying (single-user)

**Backend** (FastAPI + weekly scheduler) → **Render** free web service
**Frontend** (Vite/React SPA) → **Netlify** free static site

This app is single-user: your FPL entry id is hardcoded
(`MY_ENTRY_ID = 6849416` in `backend/api/routes/*.py` and
`frontend/src/hooks/useSquad.ts`). If you forked this, change those first.
The URL only exposes public FPL data for that one team.

---

## 0. Push to a Git host

```bash
cd fpl-predictor
git init
git add .
git commit -m "Deploy-ready: env CORS, render.yaml, netlify.toml"
git branch -M main
git remote add origin https://github.com/<you>/fpl-predictor.git
git push -u origin main
```

`.gitignore` already whitelists the runtime files the backend needs
(`bootstrap.json`, `fixtures.json`, `player_histories.json`,
`predictions_gw*.csv`, `historical/2025-26/teams.csv`, and the trained
model in `backend/models/`). The 30 MB training CSVs stay out — you
retrain locally and commit the updated `position_models.joblib`.

Confirm the model actually got committed:

```bash
git ls-files | grep -E 'position_models.joblib|data/bootstrap.json'
```

---

## 1. Backend on Render

1. Render dashboard → **New → Blueprint** → connect the repo. It picks up
   `render.yaml` (service `fpl-predictor-api`, Python 3.11, free plan).
2. It will ask for the one `sync: false` env var — leave `ALLOWED_ORIGINS`
   blank for now, or set `*` temporarily.
3. Deploy. First build takes a few minutes (installs pandas / lightgbm).
   When it's up, check `https://<service>.onrender.com/health` → `{"status":"ok"}`.
4. Copy that base URL.

**Free-plan behaviour to expect**
- Sleeps after ~15 min idle; the next request cold-starts in ~50 s.
- `backend/data/tracking.db` (accuracy history) resets on every redeploy —
  the filesystem is ephemeral. GW1's logged data is trivial to lose this
  early. To keep it: upgrade to a paid plan, add a **Disk** mounted at
  `/var/data`, and set env `FPL_DATA_DIR=/var/data` *(needs a small code
  change — DATA_DIR is currently a fixed path in a few modules; ask when
  you want this)*.
- The in-process weekly scheduler only runs while the service is awake. If
  it's asleep at the scheduled refresh time, that run is skipped — use the
  refresh button in the UI, or `POST /predictions/refresh`, when you need
  fresh numbers. (Paid "always-on" plan removes this.)

---

## 2. Frontend on Netlify

1. Netlify → **Add new site → Import an existing project** → pick the repo.
   It reads `netlify.toml` (base `frontend`, build `npm run build`, publish
   `frontend/dist`, Node 20).
2. **Site configuration → Environment variables** → add:
   `VITE_API_BASE = https://<your-render-service>.onrender.com`
   (no trailing slash)
3. **Trigger deploy** (env vars only apply to builds after they're set).
4. Open the Netlify URL, e.g. `https://<site>.netlify.app` — this is what
   you open on your phone. Add it to your home screen for an app-like icon.

---

## 3. Close the CORS loop

Back on Render → the service → **Environment** →
`ALLOWED_ORIGINS = https://<your-site>.netlify.app`
→ save (auto-redeploys).

Now the Netlify frontend is the only origin allowed to call the API.
(You can list several, comma-separated, e.g. to also allow a Netlify
preview URL. `*` allows any — acceptable here since all data is public,
but tighter is better.)

---

## 4. Verify end to end

- Phone → Netlify URL loads the pitch, Chip Advice, Strategy, Accuracy.
- First hit may hang ~50 s while Render wakes — that's the free tier, not a bug.
- The "GW2 picks not published yet — showing GW1" note stays until FPL
  locks the gameweek; nothing to fix.

---

## Weekly upkeep (local)

The model improves as the season progresses. Every few gameweeks:

```bash
cd backend
../venv/bin/python -m src.fetch_historical      # refresh raw season data
../venv/bin/python -m src.build_features         # rebuild training table
../venv/bin/python -m src.train_model            # retrain -> position_models.joblib
../venv/bin/python -m src.predict                # regenerate predictions_gw{N}.csv
cd .. && git add backend/models backend/data/predictions_gw*.csv backend/data/*.json \
      && git commit -m "Retrain + refresh GW data" && git push
```

Render + Netlify redeploy automatically on push.
