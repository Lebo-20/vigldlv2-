import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

def get_int_env(key, default=0):
    val = os.getenv(key)
    if val is None or val.strip() == "":
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default

API_ID = get_int_env("API_ID")
API_HASH = os.getenv("API_HASH", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = get_int_env("ADMIN_ID")
AUTO_CHANNEL = get_int_env("AUTO_CHANNEL")

# Vigloo API Config
BASE_URL = os.getenv("BASE_URL", "https://api.iltv.my.id") # Default if not specified
API_CODE = "A8D6AB170F7B89F2182561D3B32F390D"
LANG = "id"

# Download & Merge Config
DOWNLOAD_DIR = "downloads"
OUTPUT_DIR = "output"
MAX_CONCURRENT_DOWNLOADS = 5
FFMPEG_PRESET = "ultrafast"  # ultrafast, slow
FFMPEG_CRF = 23

# Automation Config
AUTO_SCAN_INTERVAL = 15 * 60  # 15 minutes in seconds
PROCESSED_FILE = "processed.json"

# Create directories
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
