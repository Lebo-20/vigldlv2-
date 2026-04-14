import asyncio
import logging
from api import vigloo_api
from uploader import uploader
from config import AUTO_CHANNEL, TOPIC_ID

async def test_random_details():
    print("--- TESTING RANDOM DRAMA DETAILS ---")
    await uploader.start()
    
    print("Fetching ranking...")
    rank_res = await vigloo_api.fetch_rank()
    payloads = rank_res.get("payloads") or rank_res.get("data", {}).get("payloads", [])
    
    if not payloads:
        print("No dramas found in ranking.")
        return

    # Pick the first one
    item = payloads[0]
    drama_id = item.get("program", {}).get("id")
    
    print(f"Fetching details for Drama ID: {drama_id}...")
    detail_res = await vigloo_api.get_drama_detail(drama_id)
    detail = detail_res.get("drama") or detail_res.get("payload") or detail_res.get("data", {}).get("payload", {})
    
    if not detail:
        print("Failed to fetch drama details.")
        return

    drama_title = detail.get("title", "Unknown Title")
    drama_desc = detail.get("description", "No description.")
    genres_list = detail.get("genres", [])
    genre_names = ", ".join([g.get("title") for g in genres_list]) if isinstance(genres_list, list) else "Drama"
    
    # New Poster Logic: thumbnailExpanded first, NO titleImage
    poster_url = detail.get("thumbnailExpanded") or detail.get("thumbnail") or detail.get("thumbnails", [{}])[0].get("url")
    
    info_caption = (
        f"🎬 **{drama_title}** (TEST)\n\n"
        f"🎭 **Genre**: {genre_names}\n"
        f"📝 **Sinopsis**: {drama_desc[:800]}{'...' if len(drama_desc) > 800 else ''}\n\n"
        f"#Vigloo #Drama #TestDetails"
    )

    print(f"Sending to {AUTO_CHANNEL} (Topic: {TOPIC_ID})...")
    print(f"Using Poster: {poster_url}")
    
    try:
        if poster_url:
            await uploader.client.send_file(AUTO_CHANNEL, poster_url, caption=info_caption, reply_to=TOPIC_ID)
        else:
            await uploader.client.send_message(AUTO_CHANNEL, info_caption, reply_to=TOPIC_ID)
        print("✅ Success!")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_random_details())
