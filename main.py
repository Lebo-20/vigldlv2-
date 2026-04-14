import os
import time
import json
import logging
import asyncio
import shutil
from datetime import datetime
from telethon import events

from api import vigloo_api
from downloader import downloader
from merge import merger
from uploader import uploader
from gsheets import gsheet_manager
from config import *

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_bar(percent):
    length = 20
    filled = int(length * percent / 100)
    return "█" * filled + "░" * (length - filled) + f" {percent:.1f}%"

class ViglooBot:
    def __init__(self):
        self.processed_file = PROCESSED_FILE
        self.processed_data = self._load_processed()
        self.auto_mode = True
        self.session_failed = set()
        self.priority_queue = asyncio.Queue() # Queue for manual ID/Search tasks
        self.lock = asyncio.Lock()  # Ensure only one drama processed at a time
        self.last_status_time = 0
        self.failed_counts = {}

    def _load_processed(self):
        if os.path.exists(self.processed_file):
            try:
                with open(self.processed_file, 'r') as f:
                    return set(json.load(f))
            except: return set()
        return set()

    def mark_processed(self, drama_id):
        self.processed_data.add(drama_id)
        with open(self.processed_file, 'w') as f:
            json.dump(list(self.processed_data), f)

    def is_processed(self, drama_id):
        return drama_id in self.processed_data

    async def run_pipeline(self, drama_id, chat_id=AUTO_CHANNEL, topic_id=TOPIC_ID):
        """Processes one drama end-to-end"""
        status_msg = None
        temp_dir = os.path.join(DOWNLOAD_DIR, str(drama_id))
        
        async def update_status(text, force=False):
            nonlocal status_msg
            now = time.time()
            if not force and now - self.last_status_time < STATUS_UPDATE_INTERVAL:
                return
            self.last_status_time = now
            try:
                if status_msg:
                    await status_msg.edit(text)
                else:
                    status_msg = await uploader.client.send_message(chat_id, text, reply_to=topic_id)
            except Exception as e:
                logger.error(f"Status update failed: {e}")

        try:
            # 1. Scraping Detail
            await asyncio.sleep(API_REQUEST_DELAY)
            res = await vigloo_api.get_drama_detail(drama_id)
            if not res: return False
            
            detail = res.get("drama") or res.get("payload") or res.get("data", {}).get("payload", {})
            if not detail: return False
            
            drama_title = detail.get("title", f"Drama_{drama_id}")
            
            # GSheet Check: Skip if already in Spreadsheet
            exist = gsheet_manager.find_drama(drama_title)
            if exist:
                logger.info(f"Drama {drama_title} already in Spreadsheet. Skipping.")
                return True
            
            drama_desc = detail.get("description", "No description available.")
            genres_list = detail.get("genres", [])
            genre_names = ", ".join([g.get("title") for g in genres_list]) if isinstance(genres_list, list) else "Drama"
            poster_url = detail.get("thumbnailExpanded") or detail.get("thumbnail") or detail.get("thumbnails", [{}])[0].get("url")
            
            seasons = detail.get("seasons", [])
            if not seasons: return False

            # We usually process Season 1 unless logic needs more
            for season in seasons:
                season_id = season.get("id")
                season_num = season.get("seasonNumber", 1)
                await asyncio.sleep(API_REQUEST_DELAY)
                res_eps = await vigloo_api.get_episodes(drama_id, season_id)
                if not res_eps: continue
                
                episodes = res_eps.get("payloads") or res_eps.get("data", {}).get("payloads", [])
                total_eps = len(episodes)
                downloaded_files = []
                
                if total_eps == 0: continue
                
                os.makedirs(temp_dir, exist_ok=True)
                episode_progress = {} # idx -> percent
                
                # Initial status
                self.last_status_time = 0 # Reset for new drama
                await update_status(f"🎬 **[vigloo] Full Episode**: {drama_title}\n🔥 Status: **Memulai proses {total_eps} episode...**", force=True)

                # 3. Stream & Download (Parallelized for Speed)
                pipeline_start_time = time.time()
                
                async def process_one_episode(idx, ep):
                    ep_num = ep.get("episodeNumber")
                    stream_res = await vigloo_api.get_stream(season_id, ep_num)
                    if not stream_res:
                        return None
                    
                    # New API: stream info is in 'payload' or 'source' (if dict)
                    stream_info = stream_res.get("payload")
                    if not isinstance(stream_info, dict):
                        stream_info = stream_res.get("source")
                    
                    if not isinstance(stream_info, dict) or not stream_info.get("url"):
                        logger.error(f"❌ Episode {ep_num} failed: Locked Content or Paywall.")
                        return None
                    
                    file_path = os.path.join(temp_dir, f"S{season_num}E{ep_num}.mp4")
                    
                    async def progress_cb(label, ep_percent, current_sec=0, total_sec=0):
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

                        dashboard = (
                            f"🎬 **[vigloo] Full Episode**: {drama_title}\n"
                            f"🔥 Status: **Processing ({total_eps} Eps)...**\n"
                            f"🎞 Progress: `{get_bar(total_percent)}`\n"
                            f"⏳ Estimasi: `{eta_str}`"
                        )
                        await update_status(dashboard)

                    success = await downloader.download_file(stream_info, file_path, progress_cb)
                    if not success:
                        logger.error(f"❌ Episode {ep_num} failed during download/burn.")
                        return None
                    
                    episode_progress[idx] = 100
                    return file_path

                tasks = []
                for i, ep in enumerate(episodes, 1):
                    tasks.append(process_one_episode(i, ep))
                    await asyncio.sleep(5) # Stagger episode start (5s) as requested
                
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
                    # 5. Send Poster & Info Before Video
                    info_caption = (
                        f"🎬 **{drama_title}**\n\n"
                        f"🎭 **Genre**: {genre_names}\n"
                        f"📝 **Sinopsis**: {drama_desc[:800]}{'...' if len(drama_desc) > 800 else ''}\n\n"
                        f"#Vigloo #Drama #EpisodeFull"
                    )
                    try:
                        if poster_url:
                            await uploader.client.send_file(chat_id, poster_url, caption=info_caption, reply_to=topic_id)
                        else:
                            await uploader.client.send_message(chat_id, info_caption, reply_to=topic_id)
                    except: pass

                    # 6. Upload Video
                    async def upload_cb(sent_bytes, total_bytes):
                        pct = (sent_bytes / total_bytes) * 100
                        await update_status(f"🎬 **{drama_title}**\n🔥 Status: **Uploading...**\n`{get_bar(pct)}`")

                    video_caption = f"[vigloo] Full Episode {drama_title}"
                    await uploader.upload_video(chat_id, output_path, video_caption, topic_id, progress_callback=upload_cb)
                    
                    # Log to GSheet
                    gsheet_manager.log_drama(drama_title, "SUCCESS", f"S{season_num} Full Movie Uploaded")
                    
                    # Delete dashboard message after success
                    if status_msg: await uploader.client.delete_messages(chat_id, status_msg)
                    if os.path.exists(output_path): os.remove(output_path)

            self.mark_processed(drama_id)
            return True
        except Exception as e:
            logger.error(f"Pipeline error for {drama_id}: {e}")
            return False
        finally:
            if status_msg: 
                try: await uploader.client.delete_messages(chat_id, status_msg)
                except: pass
            if os.path.exists(temp_dir): shutil.rmtree(temp_dir)

    async def auto_scan_task(self):
        """Background task for auto mode with priority queue and auto-scanning"""
        logger.info("Starting Vigloo Automation Bot...")
        await uploader.start()
        
        # Command Listeners
        @uploader.client.on(events.NewMessage(pattern='/add (\\d+)'))
        async def add_handler(event):
            if event.sender_id != int(ADMIN_ID): return
            drama_id = event.pattern_match.group(1)
            await self.priority_queue.put(('id', drama_id, event.chat_id, event.message.reply_to_msg_id))
            await event.reply(f"✅ Drama ID {drama_id} ditambahkan ke antrian priority!")

        @uploader.client.on(events.NewMessage(pattern='/search (.+)'))
        async def search_handler(event):
            if event.sender_id != int(ADMIN_ID): return
            query = event.pattern_match.group(1)
            await self.priority_queue.put(('search', query, event.chat_id, event.message.reply_to_msg_id))
            await event.reply(f"🔍 Mencari dan menambahkan drama '{query}' ke antrian priority...")

        while True:
            try:
                # 1. Process Priority Queue
                while not self.priority_queue.empty():
                    task_type, payload, chat_id, topic_id = await self.priority_queue.get()
                    logger.info(f"Processing priority task: {task_type} -> {payload}")
                    
                    async with self.lock:
                        if task_type == 'id':
                            await self.run_pipeline(payload, chat_id, topic_id)
                        elif task_type == 'search':
                            search_res = await vigloo_api.search(payload)
                            payloads = search_res.get("payloads") or search_res.get("data", {}).get("payloads", [])
                            if payloads:
                                first_item = payloads[0]
                                drama = first_item.get("program") if first_item.get("program") else first_item
                                await self.run_pipeline(drama.get("id"), chat_id, topic_id)
                            else:
                                await uploader.client.send_message(chat_id, f"❌ Drama '{payload}' tidak ditemukan.")
                    
                    self.priority_queue.task_done()
                    await asyncio.sleep(5)

                # 2. Auto Scan
                logger.info("Scanning Ranking & Browse...")
                session_failed = set()
                
                # Fetch Ranking
                rank_data = await vigloo_api.fetch_rank()
                # Combined payloads from Rank and Browse
                all_drama_ids = []
                
                if rank_data:
                    ps = rank_data.get("payloads") or rank_data.get("data", {}).get("payloads", [])
                    for p in ps:
                        d_id = p.get("program", {}).get("id")
                        if d_id and not self.is_processed(d_id): all_drama_ids.append(d_id)
                
                # Fetch Browse
                browse_data = await vigloo_api.fetch_browse()
                if browse_data:
                    ps = browse_data.get("payloads") or browse_data.get("data", {}).get("payloads", [])
                    for p in ps:
                        d_id = p.get("program", {}).get("id")
                        if d_id and not self.is_processed(d_id): all_drama_ids.append(d_id)

                # Process auto-scanned dramas
                for drama_id in all_drama_ids:
                    # Check Priority Queue again inside the loop for responsiveness
                    if not self.priority_queue.empty(): break
                    
                    if self.failed_counts.get(drama_id, 0) >= 3: continue
                    
                    async with self.lock:
                        try:
                            logger.info(f"Auto-processing drama {drama_id}...")
                            success = await asyncio.wait_for(self.run_pipeline(drama_id), timeout=4*3600)
                            if not success:
                                self.failed_counts[drama_id] = self.failed_counts.get(drama_id, 0) + 1
                            await asyncio.sleep(60) # Cooldown between automated dramas
                        except Exception as e:
                            logger.error(f"Auto-pipeline failed for {drama_id}: {e}")
                            self.failed_counts[drama_id] = self.failed_counts.get(drama_id, 0) + 1

                logger.info(f"Auto-scan finished. Sleeping for {AUTO_SCAN_INTERVAL}s...")
                await asyncio.sleep(AUTO_SCAN_INTERVAL)
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await asyncio.sleep(60)

if __name__ == "__main__":
    bot = ViglooBot()
    asyncio.run(bot.auto_scan_task())
