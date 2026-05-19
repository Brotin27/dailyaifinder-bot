"""
Daily AI Finder Bot — Configuration
All sensitive credentials are loaded from environment variables.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROMPTS_DIR = BASE_DIR / "prompts"

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

# ── Telegram ───────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_ID = int(os.getenv("TELEGRAM_ADMIN_ID", "0"))

# ── WordPress ──────────────────────────────────────────────────────────
WP_URL = os.getenv("WP_URL", "https://honeydew-chough-681574.hostingersite.com")
WP_API_BASE = f"{WP_URL}/wp-json/wp/v2"
WP_USERNAME = os.getenv("WP_USERNAME", "")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD", "")

# ── Google Gemini ──────────────────────────────────────────────────────
# Primary AI model for content generation
GEMINI_DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "imagen-3.0-generate-002")

# ── Unsplash ───────────────────────────────────────────────────────────
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "")

# ── Data file paths ───────────────────────────────────────────────────
API_KEYS_FILE = DATA_DIR / "api_keys.json"
DRAFTS_FILE = DATA_DIR / "drafts.json"
AFFILIATE_LINKS_FILE = DATA_DIR / "affiliate_links.json"
PENDING_AFFILIATES_FILE = DATA_DIR / "pending_affiliates.json"

# ── Article defaults ──────────────────────────────────────────────────
DEFAULT_ARTICLE_LANGUAGE = "English"
DEFAULT_WORD_COUNT_MIN = 2000
DEFAULT_WORD_COUNT_MAX = 3000

# ── WordPress categories (slugs matching your React frontend) ─────────
WP_CATEGORIES = {
    "ai-tools": "AI Tools",
    "comparisons": "Comparisons",
    "tutorials": "Tutorials",
    "productivity": "Productivity",
    "industry-news": "Industry News",
}
