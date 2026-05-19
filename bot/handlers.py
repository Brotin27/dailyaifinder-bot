"""
Telegram Bot Command Handlers
All /commands are defined here and registered in main.py.
"""
import json
import io
import time
import uuid
import logging
from typing import Optional

from telegram import Update, InputFile
from telegram.ext import ContextTypes
from telegram.constants import ParseMode, ChatAction

import config
from services.key_manager import key_manager
from services import wordpress as wp
from agent import researcher, writer, image_gen
from bot import keyboards

logger = logging.getLogger(__name__)


# ── Auth decorator ─────────────────────────────────────────────────────

def admin_only(func):
    """Decorator to restrict commands to the admin Telegram user only."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if config.TELEGRAM_ADMIN_ID and user_id != config.TELEGRAM_ADMIN_ID:
            await update.message.reply_text("⛔ You are not authorized to use this bot.")
            return
        return await func(update, context)
    return wrapper


# ── Draft storage helpers ──────────────────────────────────────────────

def _load_drafts() -> list[dict]:
    if config.DRAFTS_FILE.exists():
        try:
            return json.loads(config.DRAFTS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, TypeError):
            return []
    return []


def _save_drafts(drafts: list[dict]):
    config.DRAFTS_FILE.write_text(json.dumps(drafts, indent=2), encoding="utf-8")


def _get_draft(draft_id: str) -> Optional[dict]:
    drafts = _load_drafts()
    for d in drafts:
        if d["id"] == draft_id:
            return d
    return None


def _remove_draft(draft_id: str):
    drafts = _load_drafts()
    drafts = [d for d in drafts if d["id"] != draft_id]
    _save_drafts(drafts)


# ═══════════════════════════════════════════════════════════════════════
# COMMANDS
# ═══════════════════════════════════════════════════════════════════════

@admin_only
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    await update.message.reply_text(
        "🤖 **Daily AI Finder Bot** is online!\n\n"
        "Use /help to see all available commands.\n"
        "Your Telegram ID: `{}`".format(update.effective_user.id),
        parse_mode=ParseMode.MARKDOWN,
    )


@admin_only
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = """🤖 **Daily AI Finder Bot — Commands**

📝 **Content Creation**
• `/tool <url>` — Research a SaaS tool & write a review
• `/post <topic>` — Write a general AI blog post

📄 **Draft Management**
• `/drafts` — Show all pending drafts
• `/publish <id>` — Publish a draft to WordPress
• `/delete <id>` — Delete a draft

🔗 **Affiliate Links**
• `/setaffiliate <slug> <url>` — Map an affiliate link
• `/affiliates` — Show all mapped affiliate links

🔑 **API Key Management**
• `/addkey <api_key>` — Add a Gemini API key
• `/removekey <index>` — Remove a key by index
• `/keys` — List all keys with status
• `/validatekeys` — Test all keys

⚙️ **System**
• `/help` — Show this message
• `/myid` — Show your Telegram user ID"""

    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the user's Telegram ID (useful for setting up TELEGRAM_ADMIN_ID)."""
    await update.message.reply_text(
        f"Your Telegram User ID: `{update.effective_user.id}`",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── Content Creation ──────────────────────────────────────────────────

@admin_only
async def cmd_tool(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /tool <url> — Research a SaaS tool and write a review."""
    if not context.args:
        await update.message.reply_text("Usage: `/tool <url>`\nExample: `/tool https://anara.com`", parse_mode=ParseMode.MARKDOWN)
        return

    tool_url = context.args[0]
    tool_name = " ".join(context.args[1:]) if len(context.args) > 1 else ""

    await update.message.reply_chat_action(ChatAction.TYPING)
    status_msg = await update.message.reply_text(
        f"🔍 **Researching** `{tool_url}`...\nThis takes 1-2 minutes. Please wait.",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Step 1: Research
    research_data = await researcher.research_tool(tool_url, tool_name)
    if research_data.startswith("❌"):
        await status_msg.edit_text(research_data, parse_mode=ParseMode.MARKDOWN)
        return

    await status_msg.edit_text("📝 **Research complete!** Now writing the article...", parse_mode=ParseMode.MARKDOWN)

    # Step 2: Write article
    article = await writer.write_tool_review(tool_url, research_data, tool_name)
    if "error" in article:
        await status_msg.edit_text(f"❌ Article generation failed:\n{article['error']}", parse_mode=ParseMode.MARKDOWN)
        return

    await status_msg.edit_text("🎨 **Article written!** Generating featured image...", parse_mode=ParseMode.MARKDOWN)

    # Step 3: Generate featured image
    image_bytes = await image_gen.generate_featured_image(
        article["title"],
        tool_name or article.get("tool_slug", ""),
    )

    # Step 4: Get inline stock images
    inline_images = await image_gen.get_inline_images(
        article["title"],
        count=2,
    )

    # Step 5: Save as draft
    draft_id = str(uuid.uuid4())[:8]
    draft = {
        "id": draft_id,
        "type": "tool_review",
        "title": article["title"],
        "meta_description": article["meta_description"],
        "excerpt": article["excerpt"],
        "content_html": article["content_html"],
        "tags": article["tags"],
        "category_slug": article["category_slug"],
        "tool_slug": article.get("tool_slug", ""),
        "affiliate_url": article.get("affiliate_url", ""),
        "tool_url": tool_url,
        "image_bytes_hex": image_bytes.hex() if image_bytes else "",
        "inline_images": inline_images,
        "created_at": time.time(),
    }

    drafts = _load_drafts()
    drafts.append(draft)
    _save_drafts(drafts)

    # Step 6: Send preview to Telegram
    preview_text = (
        f"✅ **Draft Ready!** (ID: `{draft_id}`)\n\n"
        f"📰 **{article['title']}**\n\n"
        f"📝 {article['excerpt'][:400]}\n\n"
        f"🏷️ Tags: {', '.join(article['tags'][:5])}\n"
        f"📁 Category: {article['category_slug']}\n"
        f"🔗 Tool: {tool_url}\n"
        f"💰 Affiliate: {'✅ Mapped' if article.get('affiliate_url') != tool_url else '⏳ Not mapped yet'}"
    )

    if image_bytes:
        await update.message.reply_photo(
            photo=InputFile(io.BytesIO(image_bytes), filename="featured.png"),
            caption=preview_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboards.draft_actions(draft_id),
        )
    else:
        await update.message.reply_text(
            preview_text + "\n\n⚠️ Featured image generation failed (will use Unsplash fallback).",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboards.draft_actions(draft_id),
        )

    await status_msg.delete()


@admin_only
async def cmd_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /post <topic> — Write a general AI blog post."""
    if not context.args:
        await update.message.reply_text(
            "Usage: `/post <topic>`\nExample: `/post Top 10 Free AI Tools for Students in 2026`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    topic = " ".join(context.args)

    await update.message.reply_chat_action(ChatAction.TYPING)
    status_msg = await update.message.reply_text(
        f"🔍 **Researching:** {topic}\nThis takes 1-2 minutes. Please wait.",
        parse_mode=ParseMode.MARKDOWN,
    )

    # Step 1: Research
    research_data = await researcher.research_topic(topic)
    if research_data.startswith("❌"):
        await status_msg.edit_text(research_data, parse_mode=ParseMode.MARKDOWN)
        return

    await status_msg.edit_text("📝 **Research complete!** Now writing the article...", parse_mode=ParseMode.MARKDOWN)

    # Step 2: Write article
    article = await writer.write_blog_post(topic, research_data)
    if "error" in article:
        await status_msg.edit_text(f"❌ Article generation failed:\n{article['error']}", parse_mode=ParseMode.MARKDOWN)
        return

    await status_msg.edit_text("🎨 **Article written!** Generating featured image...", parse_mode=ParseMode.MARKDOWN)

    # Step 3: Generate featured image
    image_bytes = await image_gen.generate_featured_image(article["title"])

    # Step 4: Get inline stock images
    inline_images = await image_gen.get_inline_images(topic, count=2)

    # Step 5: Save as draft
    draft_id = str(uuid.uuid4())[:8]
    draft = {
        "id": draft_id,
        "type": "blog_post",
        "title": article["title"],
        "meta_description": article["meta_description"],
        "excerpt": article["excerpt"],
        "content_html": article["content_html"],
        "tags": article["tags"],
        "category_slug": article["category_slug"],
        "tool_slug": "",
        "affiliate_url": "",
        "tool_url": "",
        "image_bytes_hex": image_bytes.hex() if image_bytes else "",
        "inline_images": inline_images,
        "created_at": time.time(),
    }

    drafts = _load_drafts()
    drafts.append(draft)
    _save_drafts(drafts)

    # Step 6: Send preview
    preview_text = (
        f"✅ **Draft Ready!** (ID: `{draft_id}`)\n\n"
        f"📰 **{article['title']}**\n\n"
        f"📝 {article['excerpt'][:400]}\n\n"
        f"🏷️ Tags: {', '.join(article['tags'][:5])}\n"
        f"📁 Category: {article['category_slug']}"
    )

    if image_bytes:
        await update.message.reply_photo(
            photo=InputFile(io.BytesIO(image_bytes), filename="featured.png"),
            caption=preview_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboards.draft_actions(draft_id),
        )
    else:
        await update.message.reply_text(
            preview_text + "\n\n⚠️ Featured image generation failed.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboards.draft_actions(draft_id),
        )

    await status_msg.delete()


# ── Draft Management ──────────────────────────────────────────────────

@admin_only
async def cmd_drafts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /drafts — List all pending drafts."""
    drafts = _load_drafts()
    if not drafts:
        await update.message.reply_text("📭 No pending drafts.")
        return

    lines = ["📄 **Pending Drafts:**\n"]
    for d in drafts:
        type_emoji = "🔧" if d["type"] == "tool_review" else "📝"
        lines.append(f"{type_emoji} `{d['id']}` — **{d['title'][:60]}**")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


# ── Inline Button Callbacks ───────────────────────────────────────────

async def _smart_edit_message(query, text: str, reply_markup=None):
    """Edit a message's caption (if photo) or text (if plain text).
    Handles the 'There is no caption in the message to edit' error.
    """
    try:
        await query.edit_message_caption(
            caption=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup,
        )
    except Exception:
        try:
            await query.edit_message_text(
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup,
            )
        except Exception as e:
            logger.error(f"Failed to edit message: {e}")


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline keyboard button presses."""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id

    if config.TELEGRAM_ADMIN_ID and user_id != config.TELEGRAM_ADMIN_ID:
        await query.answer("⛔ Not authorized.", show_alert=True)
        return

    if data.startswith("publish:"):
        draft_id = data.split(":")[1]
        await query.edit_message_reply_markup(reply_markup=keyboards.confirm_publish(draft_id))

    elif data.startswith("delete:"):
        draft_id = data.split(":")[1]
        await query.edit_message_reply_markup(reply_markup=keyboards.confirm_delete(draft_id))

    elif data.startswith("confirm_publish:"):
        draft_id = data.split(":")[1]
        await _do_publish(query, draft_id)

    elif data.startswith("confirm_delete:"):
        draft_id = data.split(":")[1]
        _remove_draft(draft_id)
        await _smart_edit_message(query, f"🗑️ Draft `{draft_id}` deleted.")

    elif data.startswith("cancel:"):
        draft_id = data.split(":")[1]
        await query.edit_message_reply_markup(reply_markup=keyboards.draft_actions(draft_id))


async def _do_publish(query, draft_id: str):
    """Publish a draft to WordPress."""
    draft = _get_draft(draft_id)
    if not draft:
        await _smart_edit_message(query, f"❌ Draft `{draft_id}` not found.")
        return

    await _smart_edit_message(query, f"⏳ Publishing `{draft_id}` to WordPress...")

    # Upload featured image if available
    featured_media_id = None
    if draft.get("image_bytes_hex"):
        image_bytes = bytes.fromhex(draft["image_bytes_hex"])
        slug = draft.get("tool_slug") or draft["id"]
        media = wp.upload_image(
            image_bytes,
            filename=f"{slug}-featured.png",
            mime_type="image/png",
        )
        if media:
            featured_media_id = media["id"]

    # Inject inline images into content HTML
    content_html = draft["content_html"]
    if draft.get("inline_images"):
        inline_html = image_gen.build_image_html(draft["inline_images"])
        import re
        parts = re.split(r"(</h2>)", content_html, maxsplit=1)
        if len(parts) >= 3:
            content_html = parts[0] + parts[1] + "\n\n" + inline_html + "\n\n" + parts[2]
        else:
            content_html = content_html + "\n\n" + inline_html

    # Create WordPress post
    post = wp.create_post(
        title=draft["title"],
        content_html=content_html,
        excerpt=draft["excerpt"],
        category_slug=draft["category_slug"],
        tags=draft["tags"],
        featured_media_id=featured_media_id,
        status="publish",
        meta_description=draft["meta_description"],
    )

    if not post:
        await _smart_edit_message(query, f"❌ Failed to publish draft `{draft_id}` to WordPress.")
        return

    # Track for affiliate backfill if needed
    tool_slug = draft.get("tool_slug", "")
    if tool_slug and draft.get("affiliate_url") == draft.get("tool_url"):
        wp.add_pending_affiliate(tool_slug, post["id"])

    # Remove from drafts
    _remove_draft(draft_id)

    post_url = post.get("link", f"https://dailyaifinder.com/?p={post['id']}")
    await _smart_edit_message(
        query,
        f"🚀 **Published!**\n\n"
        f"📰 **{draft['title']}**\n"
        f"🔗 {post_url}\n"
        f"📊 Post ID: `{post['id']}`",
    )


# ── API Key Management ────────────────────────────────────────────────

@admin_only
async def cmd_addkey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /addkey <api_key> [label]."""
    if not context.args:
        await update.message.reply_text("Usage: `/addkey <api_key> [label]`", parse_mode=ParseMode.MARKDOWN)
        return

    api_key = context.args[0]
    label = " ".join(context.args[1:]) if len(context.args) > 1 else ""
    result = key_manager.add_key(api_key, label)
    await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_removekey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /removekey <index>."""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: `/removekey <index>`\nUse /keys to see key indices.", parse_mode=ParseMode.MARKDOWN)
        return

    index = int(context.args[0])
    result = key_manager.remove_key(index)
    await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /keys — List all API keys with status."""
    result = key_manager.list_keys()
    await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def cmd_validatekeys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /validatekeys — Test all API keys."""
    await update.message.reply_chat_action(ChatAction.TYPING)
    status_msg = await update.message.reply_text("🔍 Testing all API keys... Please wait.")
    result = await key_manager.validate_all_keys()
    await status_msg.edit_text(result, parse_mode=ParseMode.MARKDOWN)


# ── Affiliate Link Management ─────────────────────────────────────────

@admin_only
async def cmd_setaffiliate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setaffiliate <tool_slug> <affiliate_url>."""
    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/setaffiliate <tool_slug> <affiliate_url>`\n"
            "Example: `/setaffiliate anara https://anara.com?ref=dailyaifinder`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    tool_slug = context.args[0].lower()
    affiliate_url = context.args[1]

    # Save the mapping
    wp.save_affiliate_link(tool_slug, affiliate_url)

    # Auto-backfill existing posts
    status_msg = await update.message.reply_text(
        f"✅ Affiliate link saved for `{tool_slug}`!\n"
        f"🔄 Scanning published posts for auto-update...",
        parse_mode=ParseMode.MARKDOWN,
    )

    updated_count = wp.backfill_affiliate_links(tool_slug, affiliate_url)

    if updated_count > 0:
        await status_msg.edit_text(
            f"✅ Affiliate link saved for `{tool_slug}`!\n"
            f"🔄 **{updated_count} published post(s)** updated with your affiliate link!\n"
            f"🔗 `{affiliate_url}`",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await status_msg.edit_text(
            f"✅ Affiliate link saved for `{tool_slug}`!\n"
            f"📝 No existing posts found to update.\n"
            f"🔗 `{affiliate_url}`\n\n"
            f"Future articles about this tool will automatically use this link.",
            parse_mode=ParseMode.MARKDOWN,
        )


@admin_only
async def cmd_affiliates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /affiliates — List all mapped affiliate links."""
    links = wp.load_affiliate_links()
    if not links:
        await update.message.reply_text("📭 No affiliate links mapped yet. Use /setaffiliate to add one.")
        return

    lines = ["🔗 **Affiliate Link Mappings:**\n"]
    for slug, url in links.items():
        lines.append(f"• `{slug}` → {url}")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
