import httpx
import logging
import asyncio
from config import (
    BASE_URL, API_CODE, LANG, API_REQUEST_DELAY, 
    API_MAX_RETRIES, API_BACKOFF_FACTOR, API_MAX_CONCURRENT_REQUESTS
)

logger = logging.getLogger(__name__)

class ViglooAPI:
    def __init__(self):
        self.base_url = BASE_URL
        self.params = {
            "lang": LANG,
            "code": API_CODE
        }
        # Limit concurrent API calls to prevent server spam
        self.semaphore = asyncio.Semaphore(API_MAX_CONCURRENT_REQUESTS)

    async def _get(self, endpoint, additional_params=None):
        params = self.params.copy()
        if additional_params:
            params.update(additional_params)
        
        async with self.semaphore:
            async with httpx.AsyncClient(timeout=30.0) as client:
                current_delay = API_REQUEST_DELAY
                for attempt in range(API_MAX_RETRIES):
                    try:
                        # Base delay before every request
                        await asyncio.sleep(current_delay)
                        
                        response = await client.get(f"{self.base_url}{endpoint}", params=params)
                        
                        # Handle specific HTTP error cases
                        if response.status_code == 500:
                            raise httpx.HTTPStatusError("Internal Server Error", request=response.request, response=response)
                            
                        response.raise_for_status()
                        return response.json()
                        
                    except (httpx.HTTPStatusError, httpx.RequestError) as e:
                        # Only retry on 5xx or connection issues
                        is_server_error = isinstance(e, httpx.HTTPStatusError) and e.response.status_code >= 500
                        is_conn_error = isinstance(e, httpx.RequestError)
                        
                        if attempt < API_MAX_RETRIES - 1 and (is_server_error or is_conn_error):
                            # Exponential Backoff for 500 or Connection Error
                            wait_time = current_delay * (API_BACKOFF_FACTOR ** attempt) + 5
                            logger.warning(f"API {endpoint} failed (Attempt {attempt+1}/{API_MAX_RETRIES}). Retrying in {wait_time:.1f}s...")
                            await asyncio.sleep(wait_time)
                            continue
                        
                        # Don't log 404 as error (silent skip)
                        if not (isinstance(e, httpx.HTTPStatusError) and e.response.status_code == 404):
                            logger.error(f"API Final Error ({endpoint}): {e}")
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
