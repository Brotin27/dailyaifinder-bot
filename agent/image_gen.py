"""
AI Image Generator
- Generates custom featured images using Gemini 2.5 Flash native image generation
- Falls back to Unsplash stock images for in-article illustrations
"""
import io
import logging
import base64
from typing import Optional

from google.genai import types

import config
from services.key_manager import key_manager
from services import unsplash

logger = logging.getLogger(__name__)


async def generate_featured_image(
    article_title: str,
    tool_name: str = "",
) -> Optional[bytes]:
    """Generate a custom featured image using Gemini 2.5 Flash native image gen.

    Returns PNG image bytes or None on failure.
    """
    client = key_manager.get_genai_client()
    if not client:
        logger.error("No API key available for image generation.")
        return None

    image_prompt = (
        f"Generate a premium, modern blog featured image for an article titled: "
        f'"{article_title}". '
        f"{'Tool/Brand: ' + tool_name + '. ' if tool_name else ''}"
        f"Style: Clean, professional tech blog aesthetic with dark background, "
        f"vibrant cyan/blue/purple accent gradients, abstract 3D tech elements "
        f"(nodes, circuits, geometric shapes), cinematic lighting. "
        f"Do NOT include any text, logos, or watermarks. 16:9 composition."
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=image_prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        # Extract image from response parts
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.inline_data and part.inline_data.mime_type.startswith("image/"):
                    logger.info(f"Generated featured image for: {article_title}")
                    return part.inline_data.data

        logger.warning("Gemini returned no image in response.")
        return None

    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return None


async def get_inline_images(
    topic: str,
    count: int = 3,
) -> list[dict]:
    """Get royalty-free stock images from Unsplash for in-article use."""
    images = await unsplash.search_images(topic, count=count)
    if not images:
        logger.info(f"No Unsplash images found for '{topic}'. Using empty list.")
        return []
    return images


def build_image_html(images: list[dict]) -> str:
    """Build HTML snippets for inline images with proper attribution."""
    html_parts = []
    for img in images:
        html_parts.append(
            f'<figure class="wp-block-image size-large">'
            f'<img src="{img["url"]}" alt="{img["alt"]}" />'
            f'<figcaption>Photo by '
            f'<a href="{img["credit_url"]}?utm_source=dailyaifinder&utm_medium=referral" '
            f'target="_blank" rel="noopener">{img["credit"]}</a> on '
            f'<a href="https://unsplash.com?utm_source=dailyaifinder&utm_medium=referral" '
            f'target="_blank" rel="noopener">Unsplash</a></figcaption>'
            f'</figure>'
        )
    return "\n\n".join(html_parts)
