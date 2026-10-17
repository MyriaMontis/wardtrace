import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data" / "out"
FRONTEND_DIR = ROOT / "frontend"

NEO4J_URI = os.getenv("NEO4J_URI") or "bolt://localhost:7687"
NEO4J_USER = os.getenv("NEO4J_USER") or "neo4j"
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD") or "wardtrace123"

AIAND_BASE_URL = os.getenv("AIAND_BASE_URL") or "https://api.aiand.com/v1"
AIAND_API_KEY = os.getenv("AIAND_API_KEY") or ""
AIAND_MODEL = os.getenv("AIAND_MODEL") or "openai/gpt-oss-120b"

# 感染症モデル（PLAN.md 2章）
INFECTIOUS_LOOKBACK_DAYS = 2
INCUBATION_MIN_DAYS = 2
INCUBATION_MAX_DAYS = 7
LATENT_DAYS = 1
