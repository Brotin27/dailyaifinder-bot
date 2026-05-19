"""
AI Image Generator
- Generates custom featured images using Gemini Imagen 3
- Falls back to Unsplash stock images for in-article illustrations
"""
import io
import logging
from typing import Optional

from google.genai import types
from PIL import Image

import config
from services.key_manager import key_manager
from services import unsplash

logger = logging.getLogger(__name__)


async def generate_featured_image(
    article_title: str,
    tool_name: str = "",
) -> Optional[bytes]:
    """Generate a custom featured image using Gemini Imagen 3.
    
    Returns PNG image bytes or None on failure.
    """
    client = key_manager.get_genai_client()
    if not client:
        logger.error("No API key available for image generation.")
        return None

    # Build a creative prompt for a premium blog thumbnail
    image_prompt = f"""Create a premium, modern blog article featured image/thumbnail for the following:

Title: "{article_title}"
{f'Tool/Brand: {tool_name}' if tool_name else ''}

Style Requirements:
- Clean, professional, premium tech blog aesthetic
- Modern 3D render style with soft gradients
- Dark background with vibrant accent colors (cyan, blue, purple tones)
- Abstract tech elements (nodes, circuits, waves, geometric shapes)
- Do NOT include any text, logos, or watermarks in the image
- Cinematic lighting with depth of field
- 16:9 aspect ratio composition
- Should feel like a premium tech publication cover image"""

    try:
        response = client.models.generate_images(
            model=config.GEMINI_IMAGE_MODEL,
            prompt=image_prompt,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="16:9",
            ),
        )

        if response.generated_images:
            image_data = response.generated_images[0].image
            if image_data and image_data.image_bytes:
                logger.info(f"Generated featured image for: {article_title}")
                return image_data.image_bytes

        logger.warning("Imagen returned no images.")
        return None

    except Exception as e:
        logger.error(f"Image generation failed: {e}")
        return None


async def get_inline_images(
    topic: str,
    count: int = 3,
) -> list[dict]:
    """Get royalty-free stock images from Unsplash for in-article use.
    
    Returns list of dicts with keys: url, alt, credit, credit_url
    """
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
