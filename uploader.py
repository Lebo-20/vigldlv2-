import os
import logging
import asyncio
import subprocess
from telethon import TelegramClient, events
from config import API_ID, API_HASH, BOT_TOKEN

logger = logging.getLogger(__name__)

class Uploader:
    def __init__(self):
        self.client = TelegramClient('vigloo_bot_session', API_ID, API_HASH)

    async def start(self):
        await self.client.start(bot_token=BOT_TOKEN)

    def _generate_thumbnail(self, video_path):
        """Generate a thumbnail from the video using ffmpeg"""
        thumb_path = video_path + ".jpg"
        try:
            command = [
                'ffmpeg', '-y', '-i', video_path, '-ss', '00:00:05', 
                '-vframes', '1', thumb_path
            ]
            subprocess.run(command, capture_output=True)
            if os.path.exists(thumb_path):
                return thumb_path
        except Exception as e:
            logger.error(f"Thumbnail generation failed: {e}")
        return None

    async def upload_video(self, chat_id, video_path, caption, topic_id=None):
        """Upload video to Telegram channel/group/topic"""
        if not os.path.exists(video_path):
            logger.error(f"Video file not found: {video_path}")
            return None

        thumb = self._generate_thumbnail(video_path)
        
        try:
            # For topics, we use reply_to (message_thread_id)
            message = await self.client.send_file(
                chat_id,
                video_path,
                caption=caption,
                thumb=thumb,
                supports_streaming=True,
                reply_to=topic_id,
                progress_callback=self._callback
            )
            logger.info(f"Uploaded: {video_path}")
            return message
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return None
        finally:
            if thumb and os.path.exists(thumb):
                os.remove(thumb)

    def _callback(self, current, total):
        # Progress callback if needed for UI
        # logger.debug(f'Uploaded: {current}/{total} ({current/total*100:.2f}%)')
        pass

uploader = Uploader()
