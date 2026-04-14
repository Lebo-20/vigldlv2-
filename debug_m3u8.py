import asyncio
import httpx

async def check():
    url = "https://captain.sapimu.au/vigloo/api/v1/play?lang=id&seasonId=15001024&ep=1"
    headers = {
        "Authorization": "Bearer 5cf419a4c7fb1c8585314b9f797bf77e7b10a705f32c91aac65b901559780e12"
    }
    async with httpx.AsyncClient(headers=headers) as client:
        r = await client.get(url)
        data = r.json()
        m3u8 = data.get("url")
        cookies = data.get("cookies")
        print(f"URL: {m3u8}")
        
        # Baca konten m3u8
        r2 = await client.get(m3u8, cookies=cookies)
        print("--- CONTENT ---")
        print(r2.text[:500]) # Print first 500 chars

if __name__ == "__main__":
    asyncio.run(check())
