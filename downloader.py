import asyncio
import httpx
import os
import logging
from pathlib import Path
from config import MAX_CONCURRENT_DOWNLOADS

logger = logging.getLogger(__name__)

class Downloader:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)
        self.retry_count = 3

    async def download_file(self, stream_info, dest_path):
        """Download HLS stream using FFmpeg with cookies and all streams mapped (for subs)"""
        async with self.semaphore:
            m3u8_url = stream_info.get("url")
            cookies_dict = stream_info.get("cookies", {})
            
            if not m3u8_url:
                logger.error("No stream URL provided")
                return False

            # Format cookies for FFmpeg headers
            cookie_str = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
            headers = f"Cookie: {cookie_str}\r\n"

            for attempt in range(self.retry_count):
                try:
                    # ffmpeg command to download m3u8
                    # added -map 0 to catch all streams (including potential internal subtitles)
                    command = [
                        'ffmpeg', '-y', 
                        '-headers', headers,
                        '-i', m3u8_url,
                        '-map', '0', # Map all streams (Video, Audio, Subtitles if any)
                        '-c', 'copy', 
                        '-bsf:a', 'aac_adtstoasc',
                        dest_path
                    ]
                    
                    logger.info(f"Downloading stream (Attempt {attempt+1}): {m3u8_url[:60]}...")
                    process = await asyncio.create_subprocess_exec(
                        *command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    
                    try:
                        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300) # 5 min timeout
                        
                        if process.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                            logger.info(f"Downloaded: {dest_path}")
                            return True
                        else:
                            error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
                            logger.warning(f"FFmpeg attempt {attempt+1} failed: {error_msg[:200]}")
                    except asyncio.TimeoutError:
                        logger.error("FFmpeg process timed out")
                        try:
                            process.kill()
                        except:
                            pass
                        
                except Exception as e:
                    logger.warning(f"Download Exception {attempt+1}: {e}")
                
                await asyncio.sleep(5) # Delay before retry
        return False

downloader = Downloader()
