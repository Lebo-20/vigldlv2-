import httpx
import logging
import asyncio
from config import BASE_URL, API_CODE, LANG, API_REQUEST_DELAY

logger = logging.getLogger(__name__)

class ViglooAPI:
    def __init__(self):
        self.base_url = BASE_URL
        self.params = {
            "lang": LANG,
            "code": API_CODE
        }

    async def _get(self, endpoint, additional_params=None):
        params = self.params.copy()
        if additional_params:
            params.update(additional_params)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(3):
                try:
                    await asyncio.sleep(API_REQUEST_DELAY) # Avoid API spam
                    response = await client.get(f"{self.base_url}{endpoint}", params=params)
                    response.raise_for_status()
                    return response.json()
                except (httpx.HTTPStatusError, httpx.RequestError) as e:
                    # Retry on 5xx errors or connectivity issues
                    if attempt < 2 and (isinstance(e, httpx.RequestError) or (isinstance(e, httpx.HTTPStatusError) and e.response.status_code >= 500)):
                        logger.warning(f"API Attempt {attempt+1} failed ({endpoint}), retrying in 5s: {e}")
                        await asyncio.sleep(5)
                        continue
                    
                    if not (isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404):
                        logger.error(f"API Error ({endpoint}): {e}")
                    return None
            return None

    async def fetch_browse(self, page=1):
        """Latest Drama"""
        return await self._get("/api/vigloo/browse", {"page": page})

    async def fetch_rank(self):
        """Top Ranking Drama"""
        return await self._get("/api/vigloo/rank")

    async def search(self, query):
        """Search Drama"""
        return await self._get("/api/vigloo/search", {"q": query})

    async def get_drama_detail(self, drama_id):
        """Detail Drama"""
        return await self._get(f"/api/vigloo/drama/{drama_id}")

    async def get_episodes(self, drama_id, season_id):
        """Episode List (per season)"""
        return await self._get(f"/api/vigloo/drama/{drama_id}/season/{season_id}/episodes")

    async def get_stream(self, season_id, ep, video_id):
        """Stream Video Link"""
        return await self._get("/api/vigloo/getstream", {
            "seasonId": season_id,
            "ep": ep,
            "videoId": video_id
        })

# Singleton instance
vigloo_api = ViglooAPI()
