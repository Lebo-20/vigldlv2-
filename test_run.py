import asyncio
import os
import logging
import shutil
from api import vigloo_api
from downloader import downloader
from uploader import uploader
from config import *

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_single_episode():
    await uploader.start()
    
    print("Step 1: Fetching Ranking...")
    rank_res = await vigloo_api.fetch_rank()
    payloads = rank_res.get("payloads") or rank_res.get("data", {}).get("payloads", [])
    if not payloads:
        print(f"No dramas found. Keys: {rank_res.keys()}")
        return

    drama = payloads[0].get("program", {})
    drama_id = drama.get("id")
    drama_title = drama.get("title")
    print(f"Found Drama: {drama_title} (ID: {drama_id})")

    print(f"Step 2: Fetching Drama Detail...")
    detail_res = await vigloo_api.get_drama_detail(drama_id)
    payload = detail_res.get("drama") or detail_res.get("payload") or detail_res.get("data", {}).get("payload", {})
    if not payload:
        print(f"No payload. Keys: {detail_res.keys()}")
        return

    drama_desc = payload.get("description", "No description available.")
    genres_list = payload.get("genres", [])
    genre_names = ", ".join([g.get("title") for g in genres_list]) if isinstance(genres_list, list) else "Drama"
    poster_url = payload.get("titleImage") or payload.get("thumbnail") or payload.get("thumbnails", [{}])[0].get("url")

    seasons = payload.get("seasons", [])
    if not seasons:
        print("No seasons found.")
        return

    season = seasons[0]
    season_id = season.get("id")
    season_num = season.get("seasonNumber", 1)
    print(f"Found Season {season_num} (ID: {season_id})")

    print(f"Step 3: Fetching Episodes...")
    eps_res = await vigloo_api.get_episodes(drama_id, season_id)
    episodes = eps_res.get("payloads") or eps_res.get("data", {}).get("payloads", [])
    if not episodes:
        print(f"No episodes. Keys: {eps_res.keys()}")
        return

    ep = episodes[0]
    ep_num = ep.get("episodeNumber", 1)
    print(f"Found Episode {ep_num} (ID: {ep.get('id')})")

    print(f"Step 4: Getting Stream Link...")
    stream_res = await vigloo_api.get_stream(season_id, ep_num)
    stream_info = stream_res.get("payload")
    if not isinstance(stream_info, dict):
        stream_info = stream_res.get("source")
    if not isinstance(stream_info, dict):
        stream_info = stream_res

    if not stream_info or "url" not in stream_info:
        print(f"Failed to get stream. Keys: {stream_res.keys()}")
        return

    print("Step 5: Downloading & Burning Episode...")
    temp_dir = os.path.join(DOWNLOAD_DIR, "test_run")
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, f"Test_S{season_num}E{ep_num}.mp4")

    async def progress_cb(label, percent, current=0, total=0):
        if int(percent) % 25 == 0:
            print(f"[{label}] Progress: {percent:.1f}%")

    success = await downloader.download_file(stream_info, file_path, progress_cb)
    if not success:
        print("Download/Burn failed.")
        return

    # Step 6: Send Poster & Details
    print("Step 6: Sending Poster & Details...")
    info_caption = (
        f"🎬 **{drama_title}**\n\n"
        f"🎭 **Genre**: {genre_names}\n"
        f"📝 **Sinopsis**: {drama_desc[:800]}{'...' if len(drama_desc) > 800 else ''}\n\n"
        f"#Vigloo #Drama #EpisodeFull"
    )
    if poster_url:
        await uploader.client.send_file(ADMIN_ID, poster_url, caption=info_caption)
    else:
        await uploader.client.send_message(ADMIN_ID, info_caption)

    # Step 7: Upload Video
    print(f"Step 7: Uploading to {ADMIN_ID}...")
    video_caption = f"[vigloo] Full Episode {drama_title}"
    await uploader.upload_video(ADMIN_ID, file_path, video_caption)
    
    print("✅ TEST COMPLETED SUCCESSFULLY!")
    if os.path.exists(temp_dir): shutil.rmtree(temp_dir)

if __name__ == "__main__":
    asyncio.run(test_single_episode())
