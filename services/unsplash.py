"""
Unsplash API Client — Fetches royalty-free stock images for in-article use.
"""
import logging
from typing import Optional

import httpx

import config

logger = logging.getLogger(__name__)

UNSPLASH_API = "https://api.unsplash.com"


async def search_images(query: str, count: int = 3) -> list[dict]:
    """Search Unsplash for royalty-free images.
    
    Returns a list of dicts: [{"url": ..., "alt": ..., "credit": ...}, ...]
    """
    if not config.UNSPLASH_ACCESS_KEY:
        logger.warning("Unsplash API key not configured. Skipping stock images.")
        return []

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{UNSPLASH_API}/search/photos",
                params={
                    "query": query,
                    "per_page": count,
                    "orientation": "landscape",
                },
                headers={"Authorization": f"Client-ID {config.UNSPLASH_ACCESS_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for photo in data.get("results", []):
            results.append({
                "url": photo["urls"]["regular"],       # 1080px wide
                "small_url": photo["urls"]["small"],    # 400px wide
                "alt": photo.get("alt_description", query),
                "credit": photo["user"]["name"],
                "credit_url": photo["user"]["links"]["html"],
            })

        return results

    except Exception as e:
        logger.error(f"Unsplash search failed for '{query}': {e}")
        return []
