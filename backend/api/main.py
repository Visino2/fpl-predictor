"""
FastAPI entrypoint. Thin wrapper only — no prediction or optimization logic
lives here; every route calls into backend/src and serializes the result.

Also starts the weekly background scheduler (see src/weekly_job.py) on
startup, so a running server is all that's needed — no separate cron
process to manage.

Run from the backend/ directory so `src` and `api` resolve as packages:
    cd backend && uvicorn api.main:app --reload --port 8000

Deployed (Render): the platform sets $PORT, and ALLOWED_ORIGINS must list
the frontend's URL:
    uvicorn api.main:app --host 0.0.0.0 --port $PORT
"""
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import predictions, squad, strategy, team
from src import weekly_job

scheduler = BackgroundScheduler()

# Comma-separated list of allowed frontend origins, or "*" for any. Defaults
# to the local Vite dev server. In production set this to the deployed
# frontend URL, e.g. ALLOWED_ORIGINS=https://fpl-predictor.vercel.app
_origins_env = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").strip()
ALLOWED_ORIGINS = ["*"] if _origins_env == "*" else [
    o.strip() for o in _origins_env.split(",") if o.strip()
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # weekly_job owns its own scheduling now: it registers the daily backfill
    # check and computes the next weekly refresh from FPL's real gameweek
    # calendar (deadline_time per event), rescheduling itself after every run
    # since deadlines move week to week. See src/weekly_job.py.
    weekly_job.init_scheduler(scheduler)
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="FPL Predictor API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(predictions.router)
app.include_router(squad.router)
app.include_router(strategy.router)
app.include_router(team.router)


@app.get("/health")
def health():
    return {"status": "ok"}
