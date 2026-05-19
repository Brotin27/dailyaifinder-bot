"""
WordPress REST API Client
- Create posts (draft or publish)
- Upload images to Media Library
- Set featured images
- Auto-update affiliate links in published posts (backfill)
"""
import json
import logging
import re
import base64
from pathlib import Path
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)


def _auth_header() -> dict:
    """Build Basic Auth header from WordPress Application Password."""
    token = base64.b64encode(
        f"{config.WP_USERNAME}:{config.WP_APP_PASSWORD}".encode()
    ).decode()
    return {"Authorization": f"Basic {token}"}


# ── Media Upload ──────────────────────────────────────────────────────

def upload_image(image_bytes: bytes, filename: str, mime_type: str = "image/png") -> Optional[dict]:
    """Upload an image to WordPress Media Library.
    Returns the media object dict (with 'id' and 'source_url') or None.
    """
    url = f"{config.WP_API_BASE}/media"
    headers = {
        **_auth_header(),
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": mime_type,
    }

    try:
        resp = requests.post(url, headers=headers, data=image_bytes, timeout=60)
        resp.raise_for_status()
        media = resp.json()
        logger.info(f"Uploaded image '{filename}' → ID {media['id']}")
        return media
    except Exception as e:
        logger.error(f"Failed to upload image '{filename}': {e}")
        return None


# ── Category Management ───────────────────────────────────────────────

def get_or_create_category(slug: str, name: str = "") -> Optional[int]:
    """Get a category ID by slug, or create it if it doesn't exist."""
    url = f"{config.WP_API_BASE}/categories?slug={slug}"
    try:
        resp = requests.get(url, headers=_auth_header(), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data:
            return data[0]["id"]
    except Exception as e:
        logger.error(f"Error fetching category '{slug}': {e}")

    # Create the category if it doesn't exist
    if not name:
        name = config.WP_CATEGORIES.get(slug, slug.replace("-", " ").title())
    try:
        resp = requests.post(
            f"{config.WP_API_BASE}/categories",
            headers={**_auth_header(), "Content-Type": "application/json"},
            json={"name": name, "slug": slug},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["id"]
    except Exception as e:
        logger.error(f"Error creating category '{slug}': {e}")
        return None


# ── Tag Management ────────────────────────────────────────────────────

def get_or_create_tags(tag_names: list[str]) -> list[int]:
    """Get or create tags by name. Returns list of tag IDs."""
    tag_ids = []
    for name in tag_names:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        try:
            resp = requests.get(
                f"{config.WP_API_BASE}/tags?slug={slug}",
                headers=_auth_header(),
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if data:
                tag_ids.append(data[0]["id"])
                continue
        except Exception:
            pass

        try:
            resp = requests.post(
                f"{config.WP_API_BASE}/tags",
                headers={**_auth_header(), "Content-Type": "application/json"},
                json={"name": name, "slug": slug},
                timeout=15,
            )
            resp.raise_for_status()
            tag_ids.append(resp.json()["id"])
        except Exception as e:
            logger.error(f"Error creating tag '{name}': {e}")

    return tag_ids


# ── Post Creation ─────────────────────────────────────────────────────

def create_post(
    title: str,
    content_html: str,
    excerpt: str = "",
    category_slug: str = "ai-tools",
    tags: list[str] | None = None,
    featured_media_id: int | None = None,
    status: str = "draft",
    meta_description: str = "",
) -> Optional[dict]:
    """Create a new WordPress post.
    
    Args:
        status: 'draft' or 'publish'
    
    Returns the created post dict or None.
    """
    category_id = get_or_create_category(category_slug)
    tag_ids = get_or_create_tags(tags or [])

    post_data = {
        "title": title,
        "content": content_html,
        "excerpt": excerpt,
        "status": status,
        "categories": [category_id] if category_id else [],
        "tags": tag_ids,
    }

    if featured_media_id:
        post_data["featured_media"] = featured_media_id

    # Add Yoast/RankMath compatible meta description
    if meta_description:
        post_data["meta"] = {
            "_yoast_wpseo_metadesc": meta_description,
            "rank_math_description": meta_description,
        }

    try:
        resp = requests.post(
            f"{config.WP_API_BASE}/posts",
            headers={**_auth_header(), "Content-Type": "application/json"},
            json=post_data,
            timeout=30,
        )
        resp.raise_for_status()
        post = resp.json()
        logger.info(f"Created post '{title}' → ID {post['id']} (status: {status})")
        return post
    except Exception as e:
        logger.error(f"Failed to create post '{title}': {e}")
        return None


def publish_post(post_id: int) -> Optional[dict]:
    """Change a draft post to published."""
    try:
        resp = requests.post(
            f"{config.WP_API_BASE}/posts/{post_id}",
            headers={**_auth_header(), "Content-Type": "application/json"},
            json={"status": "publish"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Failed to publish post {post_id}: {e}")
        return None


def delete_post(post_id: int) -> bool:
    """Delete (trash) a WordPress post."""
    try:
        resp = requests.delete(
            f"{config.WP_API_BASE}/posts/{post_id}",
            headers=_auth_header(),
            timeout=15,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Failed to delete post {post_id}: {e}")
        return False


# ── Affiliate Link Backfill ────────────────────────────────────────────

def backfill_affiliate_links(tool_slug: str, affiliate_url: str) -> int:
    """Scan all posts tagged with `tool_slug` and replace plain URLs
    with the affiliate URL. Returns the number of posts updated.
    """
    updated_count = 0
    page = 1

    # Load pending affiliates to find which posts need updating
    pending = _load_pending_affiliates()
    post_ids = pending.get(tool_slug, [])

    if not post_ids:
        logger.info(f"No pending posts found for tool '{tool_slug}'.")
        return 0

    for post_id in post_ids:
        try:
            # Fetch the current post content
            resp = requests.get(
                f"{config.WP_API_BASE}/posts/{post_id}",
                headers=_auth_header(),
                timeout=15,
            )
            resp.raise_for_status()
            post = resp.json()
            old_content = post["content"]["rendered"]

            # The plain URL pattern to find (e.g., https://anara.com)
            # We replace href links pointing to the tool's base domain
            # Extract domain from affiliate URL for matching
            tool_domain_match = re.search(r"https?://(?:www\.)?([^/?#]+)", affiliate_url)
            if not tool_domain_match:
                continue
            tool_domain = tool_domain_match.group(1)

            # Replace all href attributes pointing to the tool's domain
            new_content = re.sub(
                rf'href="(https?://(?:www\.)?{re.escape(tool_domain)}[^"]*)"',
                f'href="{affiliate_url}"',
                old_content,
            )

            if new_content != old_content:
                update_resp = requests.post(
                    f"{config.WP_API_BASE}/posts/{post_id}",
                    headers={**_auth_header(), "Content-Type": "application/json"},
                    json={"content": new_content},
                    timeout=15,
                )
                update_resp.raise_for_status()
                updated_count += 1
                logger.info(f"Updated affiliate link in post {post_id}")

        except Exception as e:
            logger.error(f"Error updating post {post_id}: {e}")

    # Remove from pending since they're now updated
    if tool_slug in pending:
        del pending[tool_slug]
        _save_pending_affiliates(pending)

    return updated_count


# ── Affiliate Data Helpers ─────────────────────────────────────────────

def load_affiliate_links() -> dict:
    """Load the affiliate link mappings from JSON."""
    if config.AFFILIATE_LINKS_FILE.exists():
        try:
            return json.loads(config.AFFILIATE_LINKS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def save_affiliate_link(tool_slug: str, affiliate_url: str):
    """Save or update an affiliate link mapping."""
    links = load_affiliate_links()
    links[tool_slug] = affiliate_url
    config.AFFILIATE_LINKS_FILE.write_text(
        json.dumps(links, indent=2), encoding="utf-8"
    )


def get_affiliate_url(tool_slug: str) -> Optional[str]:
    """Get the affiliate URL for a tool slug, or None if not mapped."""
    return load_affiliate_links().get(tool_slug)


def _load_pending_affiliates() -> dict:
    if config.PENDING_AFFILIATES_FILE.exists():
        try:
            return json.loads(config.PENDING_AFFILIATES_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError):
            return {}
    return {}


def _save_pending_affiliates(data: dict):
    config.PENDING_AFFILIATES_FILE.write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )


def add_pending_affiliate(tool_slug: str, post_id: int):
    """Record a published post that needs affiliate link backfill later."""
    pending = _load_pending_affiliates()
    if tool_slug not in pending:
        pending[tool_slug] = []
    if post_id not in pending[tool_slug]:
        pending[tool_slug].append(post_id)
    _save_pending_affiliates(pending)
