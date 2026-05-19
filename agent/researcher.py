"""
AI Researcher — Scrapes a tool's website and uses Gemini's grounding
search to gather real-time factual information for EEAT articles.
"""
import logging
import re
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from google.genai import types

import config
from services.key_manager import key_manager

logger = logging.getLogger(__name__)


async def scrape_website(url: str) -> dict:
    """Scrape a website for basic information (title, description, headings, text)."""
    result = {"url": url, "title": "", "description": "", "headings": [], "body_text": ""}

    try:
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Title
        title_tag = soup.find("title")
        result["title"] = title_tag.get_text(strip=True) if title_tag else ""

        # Meta description
        meta = soup.find("meta", attrs={"name": "description"})
        result["description"] = meta["content"].strip() if meta and meta.get("content") else ""

        # Headings
        for tag in soup.find_all(re.compile(r"^h[1-3]$")):
            text = tag.get_text(strip=True)
            if text:
                result["headings"].append(text)

        # Body text (first 3000 chars to avoid token explosion)
        for script_or_style in soup(["script", "style", "nav", "footer", "header"]):
            script_or_style.decompose()
        body_text = soup.get_text(separator=" ", strip=True)
        result["body_text"] = body_text[:3000]

    except Exception as e:
        logger.error(f"Failed to scrape {url}: {e}")
        result["body_text"] = f"Could not scrape the website. Error: {str(e)[:200]}"

    return result


async def research_tool(url: str, tool_name: str = "") -> str:
    """Use Gemini grounding search to research a SaaS tool comprehensively.
    
    Returns a structured research report string.
    """
    client = key_manager.get_genai_client()
    if not client:
        return "❌ No API keys available. Please add a key with /addkey."

    # First scrape the website
    scraped = await scrape_website(url)
    name = tool_name or scraped["title"] or url

    research_prompt = f"""You are a senior tech journalist researching a SaaS/AI tool for a comprehensive review article.

**Tool URL:** {url}
**Tool Name:** {name}

**Scraped Website Data:**
- Title: {scraped['title']}
- Description: {scraped['description']}
- Key Headings: {', '.join(scraped['headings'][:15])}
- Page Content Preview: {scraped['body_text'][:1500]}

**Your Task:**
Research this tool thoroughly using Google Search and provide a structured report covering:

1. **What the tool does** (one-paragraph summary)
2. **Key Features** (list at least 5-8 major features with brief descriptions)
3. **Pricing & Plans** (all tiers with prices if available)
4. **Target Audience** (who should use this tool)
5. **Pros** (at least 5 genuine advantages)
6. **Cons** (at least 3 honest disadvantages or limitations)
7. **Top Competitors/Alternatives** (3-5 similar tools)
8. **Real User Sentiment** (what actual users say — positive and negative)
9. **Unique Selling Points** (what makes it different from competitors)

Be factual, cite specific numbers/prices where possible. Do NOT hallucinate features."""

    try:
        response = client.models.generate_content(
            model=config.GEMINI_DEFAULT_MODEL,
            contents=research_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.3,
            ),
        )
        return response.text or "Research returned empty results."

    except Exception as e:
        error_str = str(e)
        logger.error(f"Research failed: {error_str}")

        # Handle quota exhaustion
        if "429" in error_str or "quota" in error_str.lower():
            key = key_manager.get_next_key()  # this was already incremented
            if key:
                key_manager.mark_exhausted(key, error_str[:200])

        return f"❌ Research failed: {error_str[:300]}"


async def research_topic(topic: str) -> str:
    """Use Gemini grounding search to research a general blog topic.
    
    Returns a structured research report string.
    """
    client = key_manager.get_genai_client()
    if not client:
        return "❌ No API keys available. Please add a key with /addkey."

    research_prompt = f"""You are a senior AI/tech journalist researching a topic for a comprehensive blog article.

**Topic:** {topic}

**Your Task:**
Research this topic thoroughly using Google Search and provide a structured report covering:

1. **Topic Overview** (what this is about, why it matters in 2025/2026)
2. **Key Facts & Statistics** (real numbers, market data, usage stats)
3. **Main Points to Cover** (6-8 major subtopics/angles)
4. **Expert Opinions** (what industry experts or companies are saying)
5. **Real-World Examples** (specific tools, companies, or case studies)
6. **Common Misconceptions** (myths to debunk)
7. **Future Outlook** (predictions, trends)

Be factual, cite specific numbers where possible. Do NOT hallucinate data."""

    try:
        response = client.models.generate_content(
            model=config.GEMINI_DEFAULT_MODEL,
            contents=research_prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.3,
            ),
        )
        return response.text or "Research returned empty results."

    except Exception as e:
        logger.error(f"Topic research failed: {e}")
        return f"❌ Research failed: {str(e)[:300]}"
