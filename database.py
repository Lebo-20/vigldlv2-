import os
import psycopg2
import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL")
        self.conn = None
        if self.db_url:
            self._initialize_db()

    def _get_connection(self):
        try:
            if self.conn is None or self.conn.closed:
                self.conn = psycopg2.connect(self.db_url)
                self.conn.autocommit = True
            return self.conn
        except Exception as e:
            logger.error(f"Database connection error: {e}")
            return None

    def _initialize_db(self):
        conn = self._get_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS processed_titles (
                            id SERIAL PRIMARY KEY,
                            title TEXT UNIQUE NOT NULL,
                            drama_id TEXT,
                            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                logger.info("Database initialized successfully.")
            except Exception as e:
                logger.error(f"Failed to initialize database: {e}")

    def is_title_processed(self, title):
        if not self.db_url:
            return False
        
        conn = self._get_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM processed_titles WHERE LOWER(title) = LOWER(%s)", (title,))
                    return cur.fetchone() is not None
            except Exception as e:
                logger.error(f"Error checking title in database: {e}")
        return False

    def mark_title_processed(self, title, drama_id=None):
        if not self.db_url:
            return
        
        conn = self._get_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO processed_titles (title, drama_id) VALUES (%s, %s) ON CONFLICT (title) DO NOTHING",
                        (title, drama_id)
                    )
                logger.info(f"Marked title as processed: {title}")
            except Exception as e:
                logger.error(f"Error marking title in database: {e}")

db = Database()
