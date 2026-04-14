
import gspread
from google.oauth2.service_account import Credentials
import logging
import os
from config import GSHEET_ID, GSHEET_CREDENTIALS, BOT_IDENTITY

logger = logging.getLogger(__name__)

class GSheetManager:
    def __init__(self):
        self.client = None
        self.sheet = None
        self._authenticate()

    def _authenticate(self):
        if not os.path.exists(GSHEET_CREDENTIALS):
            logger.error(f"Credentials file {GSHEET_CREDENTIALS} not found!")
            return

        try:
            scopes = [
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive'
            ]
            creds = Credentials.from_service_account_file(GSHEET_CREDENTIALS, scopes=scopes)
            self.client = gspread.authorize(creds)
            spreadsheet = self.client.open_by_key(GSHEET_ID)
            self.sheet = spreadsheet.get_worksheet(0) # Get first sheet
            
            # Ensure headers exist
            headers = self.sheet.row_values(1)
            expected_headers = ['Judul Drama', 'Status', 'Catatan', 'Bot']
            if not headers:
                self.sheet.append_row(expected_headers)
                logger.info("Added missing headers to Spreadsheet.")
            
            logger.info("Successfully authenticated with Google Sheets.")
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Sheets: {e}")

    def _ensure_connection(self):
        if not self.sheet:
            self._authenticate()
        return self.sheet is not None

    def find_drama(self, title):
        """Find if drama exists in spreadsheet (case-insensitive, trimmed)"""
        if not self._ensure_connection():
            return None

        try:
            all_records = self.sheet.get_all_records()
            clean_title = title.strip().lower()
            
            for record in all_records:
                # Assuming first column is 'Judul Drama' or use the key if provided
                # We use .get() to avoid KeyError if header is different
                row_title = str(record.get('Judul Drama', '')).strip().lower()
                if row_title == clean_title:
                    return record
            return None
        except Exception as e:
            logger.error(f"Error searching spreadsheet: {e}")
            return None

    def log_drama(self, title, status, note):
        """Add or update drama log in spreadsheet"""
        if not self._ensure_connection():
            return False

        try:
            # Format: Judul Drama | Status | Catatan | Bot
            row = [title, status, note, BOT_IDENTITY]
            self.sheet.append_row(row)
            logger.info(f"Logged to spreadsheet: {title} | {status}")
            return True
        except Exception as e:
            logger.error(f"Error logging to spreadsheet: {e}")
            return False

# Singleton instance
gsheet_manager = GSheetManager()
