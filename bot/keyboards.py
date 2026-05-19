"""
Telegram Inline Keyboards — Buttons for Publish/Edit/Delete draft flow.
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def draft_actions(draft_id: str) -> InlineKeyboardMarkup:
    """Keyboard shown after a draft preview is sent to Telegram."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Publish", callback_data=f"publish:{draft_id}"),
            InlineKeyboardButton("❌ Delete", callback_data=f"delete:{draft_id}"),
        ],
    ])


def confirm_publish(draft_id: str) -> InlineKeyboardMarkup:
    """Confirmation keyboard before publishing."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Yes, Publish!", callback_data=f"confirm_publish:{draft_id}"),
            InlineKeyboardButton("🔙 Cancel", callback_data=f"cancel:{draft_id}"),
        ],
    ])


def confirm_delete(draft_id: str) -> InlineKeyboardMarkup:
    """Confirmation keyboard before deleting."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🗑️ Yes, Delete", callback_data=f"confirm_delete:{draft_id}"),
            InlineKeyboardButton("🔙 Cancel", callback_data=f"cancel:{draft_id}"),
        ],
    ])
