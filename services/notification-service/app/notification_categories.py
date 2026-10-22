"""Bell-notification categories and per-user delivery preferences.

Every notification published to `general_notifications` carries a `category`.
Configurable categories can be muted per user; mandatory ones (battle, system)
always arrive in full.

Modes:
- `all`  — saved to the bell and pushed as a popup (with sound on the client)
- `bell` — saved to the bell and pushed with `silent: true` (no popup/sound)
- `off`  — neither saved nor pushed
"""

import json
import logging
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.orm import Session

from models import NotificationPreference

logger = logging.getLogger(__name__)

# ── Categories ──────────────────────────────────────────────────────────────
CATEGORY_MESSAGES = "messages"
CATEGORY_SOCIAL = "social"
CATEGORY_TRADE = "trade"
CATEGORY_PARTY = "party"
CATEGORY_WORLD = "world"
CATEGORY_PROGRESS = "progress"
CATEGORY_BATTLE = "battle"
CATEGORY_SYSTEM = "system"

# Order matters: it is the order of keys in the API response.
CONFIGURABLE_CATEGORIES = (
    CATEGORY_MESSAGES,
    CATEGORY_SOCIAL,
    CATEGORY_TRADE,
    CATEGORY_PARTY,
    CATEGORY_WORLD,
    CATEGORY_PROGRESS,
)
MANDATORY_CATEGORIES = (CATEGORY_BATTLE, CATEGORY_SYSTEM)
ALL_CATEGORIES = CONFIGURABLE_CATEGORIES + MANDATORY_CATEGORIES

DEFAULT_CATEGORY = CATEGORY_SYSTEM

# ── Modes ───────────────────────────────────────────────────────────────────
MODE_ALL = "all"
MODE_BELL = "bell"
MODE_OFF = "off"
MODES = (MODE_ALL, MODE_BELL, MODE_OFF)
DEFAULT_MODE = MODE_ALL

INVALID_PREFERENCE_DETAIL = "Недопустимое значение настройки уведомлений"

# Fallback for producers that do not (yet) send `category`.
WS_TYPE_CATEGORY_MAP: Dict[str, str] = {
    # character-service
    "character_request_rejected": CATEGORY_PROGRESS,
    # battle-service — battle flow
    "battle_resumed": CATEGORY_BATTLE,
    "pvp_death_character_lost": CATEGORY_BATTLE,
    "pvp_invitation": CATEGORY_BATTLE,
    "pvp_battle_start": CATEGORY_BATTLE,
    "battle_frozen": CATEGORY_BATTLE,
    "battle_force_finished": CATEGORY_BATTLE,
    "join_request_approved": CATEGORY_BATTLE,
    "join_request_rejected": CATEGORY_BATTLE,
    "battle_paused": CATEGORY_BATTLE,
    "battle_timeout_dropout": CATEGORY_BATTLE,
    "battle_participant_dropped": CATEGORY_BATTLE,
    "party_started": CATEGORY_BATTLE,
    # battle-service — battle groups / party-service squads
    "party_left": CATEGORY_PARTY,
    "party_disbanded": CATEGORY_PARTY,
    "party_invitation": CATEGORY_PARTY,
    "party_response": CATEGORY_PARTY,
    "party_kicked": CATEGORY_PARTY,
    # inventory-service — auction
    "auction_sold": CATEGORY_TRADE,
    "auction_won": CATEGORY_TRADE,
    "auction_expired": CATEGORY_TRADE,
    "auction_outbid": CATEGORY_TRADE,
    # user-service — social
    "friend_request": CATEGORY_SOCIAL,
    "friend_accepted": CATEGORY_SOCIAL,
    "wall_post": CATEGORY_SOCIAL,
    # notification-service — support tickets
    "ticket_reply": CATEGORY_SYSTEM,
    "ticket_new_message": CATEGORY_SYSTEM,
    "ticket_status_changed": CATEGORY_SYSTEM,
}


def resolve_category(category: Optional[str], ws_type: Optional[str]) -> str:
    """Explicit valid category > ws_type fallback > system."""
    if category in ALL_CATEGORIES:
        return category
    if ws_type and ws_type in WS_TYPE_CATEGORY_MAP:
        return WS_TYPE_CATEGORY_MAP[ws_type]
    return DEFAULT_CATEGORY


# ── Preferences storage ─────────────────────────────────────────────────────

def _load_stored(db: Session, user_id: int) -> Dict[str, str]:
    row = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == user_id
    ).first()
    if row is None or not row.settings:
        return {}
    try:
        stored = json.loads(row.settings)
    except (ValueError, TypeError):
        logger.warning("Corrupt notification preferences for user %s, using defaults", user_id)
        return {}
    return stored if isinstance(stored, dict) else {}


def get_preferences(db: Session, user_id: int) -> Dict[str, str]:
    """Full preferences dict: every configurable category, defaults filled in,
    unknown/invalid stored values ignored."""
    stored = _load_stored(db, user_id)
    result = {}
    for cat in CONFIGURABLE_CATEGORIES:
        mode = stored.get(cat)
        result[cat] = mode if mode in MODES else DEFAULT_MODE
    return result


def validate_preferences_update(update: Dict[str, str]) -> bool:
    """True when every key is a configurable category and every value a mode."""
    for cat, mode in update.items():
        if cat not in CONFIGURABLE_CATEGORIES or mode not in MODES:
            return False
    return True


def save_preferences(db: Session, user_id: int, update: Dict[str, str]) -> Dict[str, str]:
    """Merge a (pre-validated) partial update into the stored preferences."""
    merged = get_preferences(db, user_id)
    merged.update(update)
    row = db.query(NotificationPreference).filter(
        NotificationPreference.user_id == user_id
    ).first()
    payload = json.dumps(merged)
    if row is None:
        row = NotificationPreference(user_id=user_id, settings=payload, updated_at=datetime.utcnow())
        db.add(row)
    else:
        row.settings = payload
        row.updated_at = datetime.utcnow()
    db.commit()
    return merged


def get_user_mode(db: Session, user_id: int, category: str) -> str:
    """Delivery mode for a user and category; mandatory categories are always `all`."""
    if category not in CONFIGURABLE_CATEGORIES:
        return MODE_ALL
    try:
        return get_preferences(db, user_id)[category]
    except Exception as e:
        # Fail open: a broken preference lookup must not swallow notifications.
        logger.error("Failed to read notification preferences for user %s: %s", user_id, e)
        db.rollback()
        return DEFAULT_MODE
