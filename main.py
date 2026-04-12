import asyncio
import json
import os
import logging
import shutil
from telethon import events
from config import *
from api import vigloo_api
from downloader import downloader
from merge import merger
from uploader import uploader

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class ViglooBot:
    def __init__(self):
        self.processed_data = self._load_processed()
        self.auto_mode = True

    def _load_processed(self):
        if os.path.exists(PROCESSED_FILE):
            with open(PROCESSED_FILE, "r") as f:
                return json.load(f)
        return {"dramas": []}

    def _save_processed(self):
        with open(PROCESSED_FILE, "w") as f:
            json.dump(self.processed_data, f, indent=4)

    def is_processed(self, drama_id, version=""):
        # We can track by ID and potentially some version or episode count
        key = f"{drama_id}_{version}"
        return key in self.processed_data["dramas"]

    def mark_processed(self, drama_id, version=""):
        key = f"{drama_id}_{version}"
        if key not in self.processed_data["dramas"]:
            self.processed_data["dramas"].append(key)
            self._save_processed()

    async def run_pipeline(self, drama_id, chat_id=None, topic_id=None):
        """Standard pipeline for downloading and uploading a drama"""
        if chat_id is None:
            chat_id = AUTO_CHANNEL if AUTO_CHANNEL != 0 else ADMIN_ID
            
        logger.info(f"Starting pipeline for Drama ID: {drama_id} to Chat: {chat_id}")
        
        # 1. Scraping Detail
        res = await vigloo_api.get_drama_detail(drama_id)
        if not res or not res.get("success"):
            return False
        
        detail = res.get("data", {}).get("payload", {})
        drama_title = detail.get("title", f"Drama_{drama_id}")
        seasons = detail.get("seasons", [])
        
        if not seasons:
            logger.error(f"No seasons found for drama {drama_id}")
            return False

        temp_dir = os.path.join(DOWNLOAD_DIR, str(drama_id))
        os.makedirs(temp_dir, exist_ok=True)

        try:
            for season in seasons:
                season_id = season.get("id")
                season_num = season.get("seasonNumber", 1)
                
                # 2. Episode Fetch
                res_eps = await vigloo_api.get_episodes(drama_id, season_id)
                if not res_eps or not res_eps.get("success"):
                    continue
                
                episodes = res_eps.get("data", {}).get("payloads", [])
                downloaded_files = []
                
                # 3. Stream & Download
                for ep in episodes:
                    ep_num = ep.get("episodeNumber")
                    video_id = ep.get("id") # The field is 'id' in payloads for episode
                    
                    stream_res = await vigloo_api.get_stream(season_id, ep_num, video_id)
                    if not stream_res or not stream_res.get("success"):
                        logger.warning(f"Could not get stream for ep {ep_num}")
                        continue
                    
                    file_path = os.path.join(temp_dir, f"S{season_num}E{ep_num}.mp4")
                    
                    # Passing entire stream info for m3u8 + cookie support
                    success = await downloader.download_file(stream_res, file_path)
                    if success:
                        downloaded_files.append(file_path)

                if not downloaded_files:
                    continue

                # 4. Merge
                output_filename = f"{drama_title} - Season {season_num}.mp4"
                output_path = os.path.join(OUTPUT_DIR, output_filename)
                
                merge_success = merger.merge_videos(downloaded_files, output_path)
                
                if merge_success:
                    # 5. Upload
                    caption = f"🎬 **{drama_title}**\n\nSeason: {season_num}\nStatus: Completed\n\n#Vigloo #Drama"
                    await uploader.upload_video(chat_id, output_path, caption, topic_id)
                    
                    # Cleanup output
                    if os.path.exists(output_path):
                        os.remove(output_path)

            # Mark as processed after all seasons or logic
            self.mark_processed(drama_id)
            return True
        finally:
            # Cleanup temp directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    async def auto_scan_task(self):
        """Background task for auto mode"""
        while True:
            if self.auto_mode:
                logger.info("Starting Auto Scan...")
                
                # Scan Ranking (Priority)
                rank_data = await vigloo_api.fetch_rank()
                if rank_data and rank_data.get("success"):
                    payloads = rank_data.get("data", {}).get("payloads", [])
                    logger.info(f"Found {len(payloads)} items in Ranking.")
                    for item in payloads:
                        program = item.get("program", {})
                        drama_id = program.get("id")
                        if drama_id and not self.is_processed(drama_id):
                            await self.run_pipeline(drama_id)
                
                # Scan Browse (Latest)
                browse_data = await vigloo_api.fetch_browse()
                if browse_data and browse_data.get("success"):
                    payloads = browse_data.get("data", {}).get("payloads", [])
                    logger.info(f"Found {len(payloads)} items in Browse.")
                    for item in payloads:
                        program = item.get("program", {})
                        drama_id = program.get("id")
                        if drama_id and not self.is_processed(drama_id):
                            await self.run_pipeline(drama_id)

                logger.info("Auto Scan finished. Sleeping...")
            
            await asyncio.sleep(AUTO_SCAN_INTERVAL)

    async def start(self):
        # Start Telethon
        await uploader.start()
        
        # Add event handlers
        @uploader.client.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            await event.reply("Welcome to Vigloo Automation Bot! Use /search {title} to find dramas.")

        @uploader.client.on(events.NewMessage(pattern='/search (.*)'))
        async def search_handler(event):
            query = event.pattern_match.group(1)
            results = await vigloo_api.search(query)
            if not results or not results.get("success"):
                await event.reply("No results found.")
                return
            
            payloads = results.get("data", {}).get("payloads", [])
            if not payloads:
                await event.reply("No results found.")
                return

            msg = "**Search Results:**\n\n"
            for item in payloads[:15]:
                program = item.get("program", {})
                msg += f"ID: `{program.get('id')}` - **{program.get('title')}**\n"
            
            msg += "\nUse `/download {id}` to start processing."
            await event.reply(msg)

        @uploader.client.on(events.NewMessage(pattern='/download (.*)'))
        async def download_handler(event):
            drama_id = event.pattern_match.group(1)
            await event.reply(f"Started processing Drama ID: {drama_id}...")
            # We can use event.chat_id to upload to the same chat
            success = await self.run_pipeline(drama_id, event.chat_id)
            if success:
                await event.reply(f"Processing for ID {drama_id} completed!")
            else:
                await event.reply(f"Failed to process Drama ID: {drama_id}")

        @uploader.client.on(events.NewMessage(pattern='/panel'))
        async def panel_handler(event):
            status = "ON" if self.auto_mode else "OFF"
            await event.reply(f"Auto Mode: **{status}**\n\nUse `/toggle` to switch.")

        @uploader.client.on(events.NewMessage(pattern='/toggle'))
        async def toggle_handler(event):
            self.auto_mode = not self.auto_mode
            status = "ON" if self.auto_mode else "OFF"
            await event.reply(f"Auto Mode is now **{status}**.")

        logger.info("Bot started!")
        
        # Run auto scan and bot client
        await asyncio.gather(
            self.auto_scan_task(),
            uploader.client.run_until_disconnected()
        )

if __name__ == "__main__":
    bot = ViglooBot()
    asyncio.run(bot.start())
