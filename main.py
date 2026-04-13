import os
import logging
import shutil
import time
import asyncio
import json
from telethon import events
from config import *
from api import vigloo_api
from downloader import downloader
from merge import merger
from uploader import uploader

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROCESSED_FILE = 'processed.json'

class ViglooBot:
    def __init__(self):
        self.processed_data = self._load_processed()
        self.auto_mode = True
        self.lock = asyncio.Lock()  # Ensure only one drama processed at a time
        self.last_status_time = 0
        self._check_lock()

    def _check_lock(self):
        """Prevent multiple instances of the bot from running"""
        lock_file = "bot.lock"
        if os.path.exists(lock_file):
            try:
                # On Windows, we can use try-except to check if file is held by another process
                with open(lock_file, "w") as f:
                    f.write(str(os.getpid()))
            except IOError:
                print("❌ ERROR: Another instance of the bot is already running!")
                os._exit(1)
        else:
            with open(lock_file, "w") as f:
                f.write(str(os.getpid()))
            
        import atexit
        def cleanup():
            if os.path.exists(lock_file):
                try: os.remove(lock_file)
                except: pass
        atexit.register(cleanup)

    def _load_processed(self):
        if os.path.exists(PROCESSED_FILE):
            try:
                with open(PROCESSED_FILE, 'r') as f:
                    return json.load(f)
            except:
                return {"dramas": []}
        return {"dramas": []}

    def _save_processed(self):
        with open(PROCESSED_FILE, 'w') as f:
            json.dump(self.processed_data, f, indent=4)

    def is_processed(self, drama_id):
        return str(drama_id) in self.processed_data.get("dramas", [])

    def mark_processed(self, drama_id):
        if not self.is_processed(drama_id):
            self.processed_data["dramas"].append(str(drama_id))
            self._save_processed()

    async def run_pipeline(self, drama_id, chat_id=None, topic_id=None):
        """Pipeline with CLEAN DASHBOARD (Only during active processing)"""
        if chat_id is None:
            chat_id = AUTO_CHANNEL if AUTO_CHANNEL != 0 else ADMIN_ID
            
        logger.info(f"Starting pipeline for Drama ID: {drama_id}")
        status_msg = None

        def get_bar(percent):
            blocks = 20
            done = int((percent / 100) * blocks)
            return f"|{'■' * done}{'□' * (blocks - done)}| {percent:.1f}%"

        async def update_status(text):
            nonlocal status_msg
            current_time = time.time()
            # Only update if enough time has passed to avoid Telegram ratelimits
            if current_time - self.last_status_time < STATUS_UPDATE_INTERVAL:
                return
            
            try:
                if status_msg is None:
                    status_msg = await uploader.client.send_message(chat_id, text, reply_to=topic_id)
                else:
                    await uploader.client.edit_message(chat_id, status_msg, text)
                self.last_status_time = current_time
            except Exception as e:
                logger.debug(f"Status update failed: {e}")

        try:
            # 1. Scraping Detail
            await asyncio.sleep(API_REQUEST_DELAY)
            res = await vigloo_api.get_drama_detail(drama_id)
            if not res or not res.get("success"): return False
            
            detail = res.get("data", {}).get("payload", {})
            drama_title = detail.get("title", f"Drama_{drama_id}")
            seasons = detail.get("seasons", [])
            if not seasons: return False

            temp_dir = os.path.join(DOWNLOAD_DIR, str(drama_id))
            os.makedirs(temp_dir, exist_ok=True)

            for season in seasons:
                season_id = season.get("id")
                season_num = season.get("seasonNumber", 1)
                await asyncio.sleep(API_REQUEST_DELAY)
                res_eps = await vigloo_api.get_episodes(drama_id, season_id)
                if not res_eps or not res_eps.get("success"): continue
                
                episodes = res_eps.get("data", {}).get("payloads", [])
                total_eps = len(episodes)
                downloaded_files = []
                
                # 3. Stream & Download (Parallelized for Speed)
                pipeline_start_time = time.time()
                episode_progress = {} # Track individual ep progress
                
                async def process_one_episode(idx, ep):
                    ep_num = ep.get("episodeNumber")
                    video_id = ep.get("id")
                    stream_res = await vigloo_api.get_stream(season_id, ep_num, video_id)
                    if not stream_res or not stream_res.get("success"):
                        return None
                    
                    file_path = os.path.join(temp_dir, f"S{season_num}E{ep_num}.mp4")
                    
                    async def progress_cb(ep_percent, current_sec, total_sec):
                        episode_progress[idx] = ep_percent
                        # Update global status occasionally
                        total_percent = sum(episode_progress.values()) / total_eps
                        
                        elapsed = time.time() - pipeline_start_time
                        if total_percent > 0.1:
                            rem_sec = (elapsed * (100 / total_percent)) - elapsed
                            hours, rem = divmod(int(rem_sec), 3600)
                            mins, secs = divmod(rem, 60)
                            eta_str = f"{hours}h {mins}m {secs}s" if hours > 0 else f"{mins}m {secs}s"
                        else:
                            eta_str = "Calculating..."

                        active_ep = max(episode_progress.keys()) if episode_progress else idx
                        dashboard = (
                            f"🎬 **{drama_title}**\n"
                            f"🔥 Status: **Parallel Processing ({total_eps} Eps)...**\n"
                            f"🎞 Progress: `{get_bar(total_percent)}`\n"
                            f"⏳ Estimasi: `{eta_str}`"
                        )
                        await update_status(dashboard)

                    success = await downloader.download_file(stream_res, file_path, progress_cb)
                    if success:
                        episode_progress[idx] = 100
                        return file_path
                    return None

                tasks = [process_one_episode(i, ep) for i, ep in enumerate(episodes, 1)]
                downloaded_files_results = await asyncio.gather(*tasks)
                downloaded_files = [f for f in downloaded_files_results if f]
                
                if len(downloaded_files) < total_eps:
                    logger.error(f"Some episodes failed for {drama_title}")
                    if status_msg: await uploader.client.delete_messages(chat_id, status_msg)
                    return False

                # Sort downloaded files to ensure correct order
                downloaded_files.sort()

                # 4. Merge
                output_filename = f"{drama_title} - Season {season_num}.mp4"
                output_path = os.path.join(OUTPUT_DIR, output_filename)
                if merger.merge_videos(downloaded_files, output_path):
                    # 5. Upload
                    async def upload_cb(sent_bytes, total_bytes):
                        pct = (sent_bytes / total_bytes) * 100
                        await update_status(f"🎬 **{drama_title}**\n🔥 Status: **Uploading...**\n`{get_bar(pct)}`")

                    caption = f"🎬 **{drama_title}**\n\nSeason: {season_num}\n#Vigloo #Drama"
                    await uploader.upload_video(chat_id, output_path, caption, topic_id, progress_callback=upload_cb)
                    
                    # Delete dashboard message after success
                    if status_msg: await uploader.client.delete_messages(chat_id, status_msg)
                    if os.path.exists(output_path): os.remove(output_path)

            self.mark_processed(drama_id)
            return True
        finally:
            if status_msg: 
                try: await uploader.client.delete_messages(chat_id, status_msg)
                except: pass
            if os.path.exists(temp_dir): shutil.rmtree(temp_dir)

    async def auto_scan_task(self):
        """Background task for auto mode with concurrency lock and 4h timeout"""
        while True:
            if self.auto_mode:
                logger.info("Starting Auto Scan...")
                
                # Scan Ranking
                rank_data = await vigloo_api.fetch_rank()
                if rank_data and rank_data.get("success"):
                    payloads = rank_data.get("data", {}).get("payloads", [])
                    for item in payloads:
                        drama_id = item.get("program", {}).get("id")
                        if drama_id and not self.is_processed(drama_id):
                            async with self.lock:
                                try:
                                    logger.info(f"Processing drama {drama_id} with 4h timeout...")
                                    await asyncio.wait_for(self.run_pipeline(drama_id), timeout=4*3600)
                                    await asyncio.sleep(10) # Cooldown after successful processing
                                except asyncio.TimeoutError:
                                    logger.error(f"Timeout: Drama {drama_id} took more than 4 hours.")
                                except Exception as e:
                                    logger.error(f"Pipeline failed for {drama_id}: {e}")
                
                # Scan Browse
                browse_data = await vigloo_api.fetch_browse()
                if browse_data and browse_data.get("success"):
                    payloads = browse_data.get("data", {}).get("payloads", [])
                    for item in payloads:
                        drama_id = item.get("program", {}).get("id")
                        if drama_id and not self.is_processed(drama_id):
                            async with self.lock:
                                try:
                                    logger.info(f"Processing drama {drama_id} with 4h timeout...")
                                    await asyncio.wait_for(self.run_pipeline(drama_id), timeout=4*3600)
                                    await asyncio.sleep(10) # Cooldown after successful processing
                                except asyncio.TimeoutError:
                                    logger.error(f"Timeout: Drama {drama_id} took more than 4 hours.")
                                except Exception as e:
                                    logger.error(f"Pipeline failed for {drama_id}: {e}")
                
            await asyncio.sleep(AUTO_SCAN_INTERVAL)

    async def start(self):
        await uploader.start()
        
        # Bot commands interface
        @uploader.client.on(events.NewMessage(pattern='/start'))
        async def handler(event):
            await event.respond('Vigloo Automation Bot is Ready!')

        @uploader.client.on(events.NewMessage(pattern='/status'))
        async def status_handler(event):
            # Convert to int for comparison
            if event.sender_id != int(ADMIN_ID):
                return
            
            status = "Auto Mode: ON" if self.auto_mode else "Auto Mode: OFF"
            if self.lock.locked():
                status += "\n🔥 Currently processing a drama..."
            await event.respond(status)

        @uploader.client.on(events.NewMessage(pattern='/update'))
        async def update_handler(event):
            if event.sender_id != int(ADMIN_ID):
                return await event.respond("❌ Only Admin can update the bot.")
            
            await event.respond("🔄 **Updating bot...** pulling latest code from GitHub.")
            try:
                import subprocess
                import sys
                # 1. Git Pull
                process = subprocess.run(["git", "pull", "origin", "main"], capture_output=True, text=True)
                if process.returncode != 0:
                    return await event.respond(f"❌ **Git Pull Failed:**\n`{process.stderr}`")
                
                await event.respond("✅ **Code updated!** Cleaning session and restarting bot... 🚀")
                
                # 2. Cleanup & Restart
                await uploader.client.disconnect()
                
                # Remove session files for a clean start
                import glob
                for f in glob.glob("*.session"):
                    try: os.remove(f)
                    except: pass
                
                os.execv(sys.executable, ['python'] + sys.argv)
            except Exception as e:
                await event.respond(f"❌ **Update Error:** {e}")

        logger.info("Bot logic started...")
        await asyncio.gather(
            uploader.client.run_until_disconnected(),
            self.auto_scan_task()
        )

if __name__ == '__main__':
    bot = ViglooBot()
    asyncio.run(bot.start())
