"""
AI Content Writer — Generates EEAT-compliant blog articles using Gemini.
Supports both SaaS tool reviews and general AI blog posts.
"""
import logging
import re
from typing import Optional
from pathlib import Path

from google.genai import types

import config
from services.key_manager import key_manager
from services.wordpress import get_affiliate_url

logger = logging.getLogger(__name__)


def _load_prompt(filename: str) -> str:
    """Load a prompt template from the prompts/ directory."""
    path = config.PROMPTS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning(f"Prompt file not found: {path}")
    return ""


def _extract_tool_slug(url: str) -> str:
    """Extract a slug-friendly name from a URL.
    e.g., 'https://www.anara.com/pricing' → 'anara'
    """
    match = re.search(r"https?://(?:www\.)?([^./]+)", url)
    return match.group(1).lower() if match else "tool"


async def write_tool_review(
    tool_url: str,
    research_data: str,
    tool_name: str = "",
) -> dict:
    """Generate a complete EEAT tool review article.
    
    Returns a dict with keys:
        title, meta_description, excerpt, content_html, tags,
        category_slug, tool_slug, affiliate_url
    """
    client = key_manager.get_genai_client()
    if not client:
        return {"error": "No API keys available. Please add a key with /addkey."}

    tool_slug = _extract_tool_slug(tool_url)
    affiliate_url = get_affiliate_url(tool_slug) or tool_url

    system_prompt = _load_prompt("system.txt")
    review_prompt = _load_prompt("tool_review.txt")

    full_prompt = f"""{system_prompt}

{review_prompt}

---
**TOOL URL:** {tool_url}
**TOOL NAME:** {tool_name or tool_slug.title()}
**TOOL SLUG:** {tool_slug}
**AFFILIATE/CTA LINK:** {affiliate_url}

**RESEARCH DATA (Use this as your factual source):**
{research_data}

---

Now write the complete article. Output ONLY the article in clean HTML format.
At the very beginning, before the HTML, output these on separate lines:
TITLE: [Your SEO-optimized title]
META: [Your meta description, 150-160 chars]
EXCERPT: [A compelling 2-sentence excerpt]
TAGS: [comma-separated relevant tags]
CATEGORY: ai-tools
---
[Then the full HTML article content below]
"""

    try:
        response = client.models.generate_content(
            model=config.GEMINI_DEFAULT_MODEL,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=8192,
            ),
        )
        raw_text = response.text or ""
        return _parse_article_output(raw_text, tool_slug, affiliate_url)

    except Exception as e:
        logger.error(f"Article generation failed: {e}")
        return {"error": str(e)[:500]}


async def write_blog_post(
    topic: str,
    research_data: str,
) -> dict:
    """Generate a general EEAT blog post article.
    
    Returns a dict with keys:
        title, meta_description, excerpt, content_html, tags, category_slug
    """
    client = key_manager.get_genai_client()
    if not client:
        return {"error": "No API keys available. Please add a key with /addkey."}

    system_prompt = _load_prompt("system.txt")
    blog_prompt = _load_prompt("blog_post.txt")

    full_prompt = f"""{system_prompt}

{blog_prompt}

---
**TOPIC:** {topic}

**RESEARCH DATA (Use this as your factual source):**
{research_data}

---

Now write the complete article. Output ONLY the article in clean HTML format.
At the very beginning, before the HTML, output these on separate lines:
TITLE: [Your SEO-optimized title]
META: [Your meta description, 150-160 chars]
EXCERPT: [A compelling 2-sentence excerpt]
TAGS: [comma-separated relevant tags]
CATEGORY: [one of: ai-tools, comparisons, tutorials, productivity, industry-news]
---
[Then the full HTML article content below]
"""

    try:
        response = client.models.generate_content(
            model=config.GEMINI_DEFAULT_MODEL,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=8192,
            ),
        )
        raw_text = response.text or ""
        return _parse_article_output(raw_text, "", "")

    except Exception as e:
        logger.error(f"Blog post generation failed: {e}")
        return {"error": str(e)[:500]}


def _parse_article_output(raw_text: str, tool_slug: str = "", affiliate_url: str = "") -> dict:
    """Parse the structured output from Gemini into a clean dict."""
    result = {
        "title": "",
        "meta_description": "",
        "excerpt": "",
        "content_html": "",
        "tags": [],
        "category_slug": "ai-tools",
        "tool_slug": tool_slug,
        "affiliate_url": affiliate_url,
    }

    lines = raw_text.strip().split("\n")
    html_start = 0

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("TITLE:"):
            result["title"] = stripped[6:].strip()
        elif stripped.startswith("META:"):
            result["meta_description"] = stripped[5:].strip()
        elif stripped.startswith("EXCERPT:"):
            result["excerpt"] = stripped[8:].strip()
        elif stripped.startswith("TAGS:"):
            tags_str = stripped[5:].strip()
            result["tags"] = [t.strip() for t in tags_str.split(",") if t.strip()]
        elif stripped.startswith("CATEGORY:"):
            result["category_slug"] = stripped[9:].strip()
        elif stripped == "---":
            html_start = i + 1
            break

    # Everything after the --- line is the HTML content
    if html_start > 0 and html_start < len(lines):
        html_content = "\n".join(lines[html_start:])
        # Clean up any markdown code fences that Gemini might add
        html_content = re.sub(r"^```html?\s*", "", html_content.strip())
        html_content = re.sub(r"\s*```$", "", html_content.strip())
        result["content_html"] = html_content
    else:
        # Fallback: try to find HTML content in the raw text
        html_match = re.search(r"(<[hH][1-6][^>]*>.*)", raw_text, re.DOTALL)
        if html_match:
            result["content_html"] = html_match.group(1)
        else:
            result["content_html"] = raw_text

    # If title is still empty, try to extract from HTML h1
    if not result["title"]:
        h1_match = re.search(r"<h1[^>]*>(.*?)</h1>", result["content_html"], re.IGNORECASE)
        if h1_match:
            result["title"] = re.sub(r"<[^>]+>", "", h1_match.group(1)).strip()

    return result
