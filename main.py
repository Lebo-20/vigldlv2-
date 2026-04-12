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
        """Standard pipeline with LIVE DASHBOARD"""
        if chat_id is None:
            chat_id = AUTO_CHANNEL if AUTO_CHANNEL != 0 else ADMIN_ID
            
        logger.info(f"Starting pipeline for Drama ID: {drama_id} to Chat: {chat_id}")
        
        # 0. Initial Status Message
        status_msg = await uploader.client.send_message(chat_id, "🎬 **Preparing Drama...**", reply_to=topic_id)
        
        def get_bar(percent):
            # 20 block resolution for smoother progress
            blocks = 20
            done = int((percent / 100) * blocks)
            return f"|{'■' * done}{'□' * (blocks - done)}| {percent:.1f}%"

        async def update_status(text):
            try: await uploader.client.edit_message(chat_id, status_msg, text)
            except: pass

        try:
            # 1. Scraping Detail
            await update_status(f"🎬 **Fetching Details (ID: {drama_id})...**")
            res = await vigloo_api.get_drama_detail(drama_id)
            if not res or not res.get("success"):
                await update_status(f"❌ **Failed to fetch details for {drama_id}**")
                return False
            
            detail = res.get("data", {}).get("payload", {})
            drama_title = detail.get("title", f"Drama_{drama_id}")
            seasons = detail.get("seasons", [])
            
            if not seasons:
                await update_status(f"❌ **No seasons found for {drama_title}**")
                return False

            temp_dir = os.path.join(DOWNLOAD_DIR, str(drama_id))
            os.makedirs(temp_dir, exist_ok=True)

            for season in seasons:
                season_id = season.get("id")
                season_num = season.get("seasonNumber", 1)
                
                # 2. Episode Fetch
                await update_status(f"🎬 **{drama_title}**\n🔥 Status: Fetching Episodes...")
                res_eps = await vigloo_api.get_episodes(drama_id, season_id)
                if not res_eps or not res_eps.get("success"): continue
                
                episodes = res_eps.get("data", {}).get("payloads", [])
                total_eps = len(episodes)
                downloaded_files = []
                
                # 3. Stream & Download
                all_downloaded = True
                pipeline_start_time = time.time()
                for i, ep in enumerate(episodes, 1):
                    ep_num = ep.get("episodeNumber")
                    video_id = ep.get("id")
                    
                    stream_res = await vigloo_api.get_stream(season_id, ep_num, video_id)
                    if not stream_res or not stream_res.get("success"):
                        all_downloaded = False; break
                    
                    file_path = os.path.join(temp_dir, f"S{season_num}E{ep_num}.mp4")
                    
                    # Global Progress Callback
                    async def progress_cb(ep_percent, current_sec, total_sec):
                        global_percent = ((i - 1) + (ep_percent / 100)) / total_eps * 100
                        
                        eta_str = "Calculating..."
                        elapsed = time.time() - pipeline_start_time
                        if global_percent > 0.1: # Show ETA earlier
                            total_est = elapsed * (100 / global_percent)
                            rem_sec = max(0, total_est - elapsed)
                            
                            hours = int(rem_sec // 3600)
                            mins = int((rem_sec % 3600) // 60)
                            secs = int(rem_sec % 60)
                            eta_str = f"{hours}h {mins}m {secs}s" if hours > 0 else f"{mins}m {secs}s"
                        
                        dashboard = (
                            f"🎬 **{drama_title}**\n"
                            f"🔥 Status: **Burning Hardsub...**\n"
                            f"🎞 Episode {i}/{total_eps}\n"
                            f"`{get_bar(global_percent)}`\n"
                            f"⏳ Estimasi Selesai: `{eta_str}`"
                        )
                        await update_status(dashboard)

                    success = await downloader.download_file(stream_res, file_path, progress_cb)
                    if not success:
                        await update_status(f"❌ **Pipeline Aborted: Download failed for Ep {ep_num} in {drama_title}**")
                        all_downloaded = False; break
                    
                    downloaded_files.append(file_path)

                if not all_downloaded or not downloaded_files:
                    return False

                # 4. Merge
                await update_status(f"🎬 **{drama_title}**\n🔥 Status: **Merging Episodes...**\n🎞 Total: {total_eps} Episode")
                output_filename = f"{drama_title} - Season {season_num}.mp4"
                output_path = os.path.join(OUTPUT_DIR, output_filename)
                
                merge_success = merger.merge_videos(downloaded_files, output_path)
                
                if merge_success:
                    # 5. Upload
                    async def upload_cb(sent_bytes, total_bytes):
                        pct = (sent_bytes / total_bytes) * 100
                        dashboard = (
                            f"🎬 **{drama_title}**\n"
                            f"🔥 Status: **Uploading to Telegram...**\n"
                            f"{get_bar(pct)}"
                        )
                        await update_status(dashboard)

                    caption = f"🎬 **{drama_title}**\n\nSeason: {season_num}\nStatus: Completed\n\n#Vigloo #Drama"
                    await uploader.upload_video(chat_id, output_path, caption, topic_id, progress_callback=upload_cb)
                    await update_status(f"✅ **{drama_title} Uploaded Successfully!**")
                    
                    if os.path.exists(output_path): os.remove(output_path)

            self.mark_processed(drama_id)
            return True
        finally:
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
                                except asyncio.TimeoutError:
                                    logger.error(f"Timeout: Drama {drama_id} took more than 4 hours.")
                                except Exception as e:
                                    logger.error(f"Pipeline failed for {drama_id}: {e}")
                
            await asyncio.sleep(600)

    async def start(self):
        await uploader.start()
        
        # Bot commands interface
        @uploader.client.on(events.NewMessage(pattern='/start'))
        async def handler(event):
            await event.respond('Vigloo Automation Bot is Ready!')

        @uploader.client.on(events.NewMessage(pattern='/status'))
        async def status_handler(event):
            status = "Auto Mode: ON" if self.auto_mode else "Auto Mode: OFF"
            if self.lock.locked():
                status += "\n🔥 Currently processing a drama..."
            await event.respond(status)

        @uploader.client.on(events.NewMessage(pattern='/update'))
        async def update_handler(event):
            if event.sender_id != ADMIN_ID:
                return await event.respond("❌ Only Admin can update the bot.")
            
            await event.respond("🔄 **Updating bot...** pulling latest code from GitHub.")
            try:
                import subprocess
                import sys
                # 1. Git Pull
                process = subprocess.run(["git", "pull", "origin", "main"], capture_output=True, text=True)
                if process.returncode != 0:
                    return await event.respond(f"❌ **Git Pull Failed:**\n`{process.stderr}`")
                
                await event.respond("✅ **Code updated!** Restarting bot... 🚀")
                
                # 2. Self Restart
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
