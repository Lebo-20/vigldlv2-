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
AUTO_CHANNEL = -1003857149032
TOPIC_ID = 3931

# GSheet Config
GSHEET_ID = "1lRZrBO9YOnzxdjSfcCmrQzKr-aQKDnMd2vD-x90qRj4"
GSHEET_CREDENTIALS = "bot-downloader-493221-8f7ba339f423.json"
BOT_IDENTITY = "VIGLOO_BOT"

# Vigloo API Config
BASE_URL = os.getenv("BASE_URL", "https://api.iltv.my.id") # Default if not specified
API_TOKEN = "5cf419a4c7fb1c8585314b9f797bf77e7b10a705f32c91aac65b901559780e12"
LANG = "id"

# Download & Merge Config
DOWNLOAD_DIR = "downloads"
OUTPUT_DIR = "output"
MAX_CONCURRENT_DOWNLOADS = 4 # Increased for speed
API_REQUEST_DELAY = 1.0 # Faster API requests
API_MAX_RETRIES = 5 # Maximum retries for API errors
API_BACKOFF_FACTOR = 2 # Multiplier for exponential backoff
API_MAX_CONCURRENT_REQUESTS = 3 # Limit concurrent API calls to avoid spam
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
ENABLE_ARIA2 = True # Use aria2c for parallel segment downloading
PROCESSED_FILE = "processed.json"
UPLOAD_SUCCESS_COOLDOWN = 600 # 10 minutes rest after successful upload

# Watermark Config (Optional)
WATERMARK_PATH = "logo.png" # Place logo.png in the root or change path
WATERMARK_SIZE = "100:-1"   # Scale watermark width to 100px
WATERMARK_OPACITY = 0.7

# Create directories
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
