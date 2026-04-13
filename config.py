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
MAX_CONCURRENT_DOWNLOADS = 4 # Increased for speed
API_REQUEST_DELAY = 1.0 # Faster API requests
STATUS_UPDATE_INTERVAL = 3 # More responsive UI updates
FFMPEG_PRESET = "ultrafast"  # default ultrafast
FFMPEG_CRF = 23

# Hardsub Rules
HARDSUB_MAX_RES = 720
HARDSUB_PRESET = "ultrafast" # ultrafast for speed
HARDSUB_CRF = 23 # 20-23
SUB_FONT = "Standard Symbols PS"
SUB_FONT_SIZE = 10
SUB_FONT_BOLD = 1
SUB_OUTLINE = 1
SUB_OFFSET = 90

# Automation Config
AUTO_SCAN_INTERVAL = 15 * 60  # Back to 15 minutes for faster scanning
EPISODE_COOLDOWN = 10 # Delay between processing different episodes (seconds)
PROCESSED_FILE = "processed.json"

# Watermark Config (Optional)
WATERMARK_PATH = "logo.png" # Place logo.png in the root or change path
WATERMARK_SIZE = "100:-1"   # Scale watermark width to 100px
WATERMARK_OPACITY = 0.7

# Create directories
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
