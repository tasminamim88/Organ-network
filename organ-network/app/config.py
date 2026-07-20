"""Central configuration, read from environment with safe defaults."""

from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "720"))
DATABASE_PATH = os.getenv("DATABASE_PATH", "organ_network.db")
SEED_DEMO = os.getenv("SEED_DEMO", "1") == "1"
