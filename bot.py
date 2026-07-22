#!/usr/bin/env python3
"""
100K Launch Bot
================

A Telegram bot that powers a 20-day, $100K digital-product launch:

  * Tracks which of the 20 launch days you're on and what's left to do.
  * Shows a daily checklist and lets you mark tasks done from Telegram.
  * Generates launch content (YouTube scripts, blog outlines, email
    sequences, Reddit comments, Twitter threads, product descriptions)
    using the Claude API.
  * Tracks revenue and business metrics and compares them against the
    targets needed to hit $100K by day 20.
  * Persists everything to a single JSON file so state survives restarts.

Run it with:

    python bot.py

See README.md for setup, deployment (Replit), and troubleshooting.
"""

import asyncio
import json
import logging
import os
import random
import sys
import tempfile
from datetime import date
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

try:
    import anthropic
except ImportError:  # pragma: no cover - anthropic is a hard requirement
    anthropic = None


# ======================================================================
# Configuration & Logging
# ======================================================================

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "").strip() or "claude-opus-4-8"
DATA_FILE = Path(os.getenv("DATA_FILE", "").strip() or "data.json")
LAUNCH_START_DATE = os.getenv("LAUNCH_START_DATE", "").strip()

_raw_allowed_user = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
TELEGRAM_ALLOWED_USER_ID: Optional[int] = int(_raw_allowed_user) if _raw_allowed_user else None

ENABLE_KEEP_ALIVE = os.getenv("ENABLE_KEEP_ALIVE", "").strip().lower() in ("1", "true", "yes")

AUTO_GENERATE_ENABLED = os.getenv("AUTO_GENERATE_ENABLED", "").strip().lower() in ("1", "true", "yes")
AUTO_GENERATE_INTERVAL_HOURS = float(os.getenv("AUTO_GENERATE_INTERVAL_HOURS", "").strip() or "24")
AUTO_GENERATE_TYPES: List[str] = [
    t.strip().lower()
    for t in os.getenv("AUTO_GENERATE_TYPES", "youtube,blog,reddit,twitter").split(",")
    if t.strip()
]

LAUNCH_LENGTH_DAYS = 20

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("100k_bot")

# A single lock protects data.json from concurrent read/modify/write races
# when multiple commands run close together (e.g. two users, or a fast
# double-tap of a command).
_data_lock = asyncio.Lock()

_anthropic_client: Optional["anthropic.Anthropic"] = None
if ANTHROPIC_API_KEY and anthropic is not None:
    _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ======================================================================
# Default data & business targets
# ======================================================================

DEFAULT_METRICS: Dict[str, float] = {
    "views": 0,
    "email_subscribers": 0,
    "sales": 0,
    "youtube_videos": 0,
    "blog_posts": 0,
    "reddit_posts": 0,
    "twitter_posts": 0,
}

# Where each metric needs to land BY DAY 20 in order to plausibly hit
# $100K. These are used only to compute "on track / behind" comparisons
# in /stats -- they are estimates, not guarantees.
FINAL_TARGETS: Dict[str, float] = {
    "views": 500_000,
    "email_subscribers": 10_000,
    "sales": 2_000,
    "youtube_videos": 20,
    "blog_posts": 40,
    "reddit_posts": 100,
    "twitter_posts": 400,
    "revenue": 100_000,
}


def _default_data() -> Dict[str, Any]:
    """Return a fresh data structure for a brand-new launch."""
    start_date = LAUNCH_START_DATE or date.today().isoformat()
    return {
        "start_date": start_date,
        "tasks_completed": [],
        "metrics": dict(DEFAULT_METRICS),
        "revenue": 0,
        "chat_id": None,
        "auto_generate_index": 0,
    }


# ======================================================================
# Persistent JSON storage
# ======================================================================

def _atomic_write(path: Path, payload: Dict[str, Any]) -> None:
    """Write JSON to disk atomically so a crash mid-write can't corrupt data."""
    directory = path.parent if str(path.parent) else Path(".")
    fd, tmp_name = tempfile.mkstemp(prefix=".data_", suffix=".tmp", dir=str(directory))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def load_data() -> Dict[str, Any]:
    """Load launch data from DATA_FILE, creating it with defaults if missing.

    Also defensively fills in any keys that might be missing from an
    older/partial data file so the bot never crashes on a KeyError.
    """
    if not DATA_FILE.exists():
        data = _default_data()
        _atomic_write(DATA_FILE, data)
        logger.info("Created new data file at %s", DATA_FILE)
        return data

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read %s (%s). Starting fresh.", DATA_FILE, exc)
        data = _default_data()
        _atomic_write(DATA_FILE, data)
        return data

    # Backfill any missing top-level keys.
    defaults = _default_data()
    changed = False
    for key, value in defaults.items():
        if key not in data:
            data[key] = value
            changed = True
    for key, value in DEFAULT_METRICS.items():
        if key not in data.get("metrics", {}):
            data.setdefault("metrics", {})[key] = value
            changed = True
    if changed:
        _atomic_write(DATA_FILE, data)

    return data


async def save_data(data: Dict[str, Any]) -> None:
    """Persist launch data to disk. Safe to call from concurrent handlers."""
    async with _data_lock:
        await asyncio.to_thread(_atomic_write, DATA_FILE, data)


# ======================================================================
# Launch day / date math
# ======================================================================

def get_current_day(data: Dict[str, Any]) -> int:
    """Return which day of the 20-day launch it is (clamped to 1..20)."""
    try:
        start = date.fromisoformat(data["start_date"])
    except (ValueError, KeyError):
        start = date.today()
    elapsed = (date.today() - start).days + 1
    return max(1, min(elapsed, LAUNCH_LENGTH_DAYS))


def get_days_remaining(day: int) -> int:
    """Days left in the launch, given the current day number."""
    return max(0, LAUNCH_LENGTH_DAYS - day)


def get_launch_status_label(day: int) -> str:
    """A short human label for where we are in the launch."""
    if day <= 1:
        return "Setup Day"
    if day <= 5:
        return "Content Sprint"
    if day <= 12:
        return "Growth Phase"
    return "Final Push"


# ======================================================================
# Daily task checklists
# ======================================================================

DAY_1_TASKS: List[str] = [
    "Create your Gumroad seller account and verify payment details",
    "Create 3 digital products in Gumroad priced at $27, $47, and $97",
    "Set up a Medium account and create/claim your publication",
    "Set up your YouTube channel: banner, profile picture, description, and links",
    "Set up a MailerLite account and start your welcome email sequence",
    "Set up your Twitter/X profile: bio, pinned tweet, and product links",
    "Join 10 relevant subreddits in your niche and read each community's rules",
    "Build a tracking spreadsheet with UTM links for every platform",
]

DAY_2_TASKS: List[str] = [
    "Record and upload your first YouTube video",
    "Post 3 genuinely helpful replies in your target Reddit communities",
    "Publish 2 blog posts on Medium linking to your lead magnet",
    "Send 5 Twitter/X threads promoting your free resource",
]

DAY_3_TASKS: List[str] = [
    "Record and upload your 2nd YouTube video",
    "Publish 2 more SEO-optimized blog posts",
    "Engage authentically in 5 Reddit threads in your niche",
    "Schedule a week of tweets/threads using a content calendar",
]

DAY_4_TASKS: List[str] = [
    "Upload your 3rd YouTube video",
    "Finish building your 5-email automated welcome sequence",
    "Publish 2 blog posts that link directly to a paid product",
    "Reply to comments and DMs across all platforms from the last 24 hours",
]

DAY_5_TASKS: List[str] = [
    "Upload your 4th YouTube video",
    "Test your full email automation flow end-to-end (signup to sale)",
    "Publish 2 blog posts optimized for buyer-intent keywords",
    "Post a Twitter/X thread specifically promoting your lead magnet",
]

# Days 6-20 repeat the same 4-task rhythm: ship, measure, engage, improve.
ONGOING_TASKS: List[str] = [
    "Upload today's YouTube video or Short",
    "Check today's metrics dashboard (views, subscribers, sales)",
    "Reply to every comment, DM, and Reddit reply from the last 24 hours",
    "Optimize one underperforming piece of content (thumbnail, title, or hook)",
]

DAILY_TASKS: Dict[int, List[str]] = {
    1: DAY_1_TASKS,
    2: DAY_2_TASKS,
    3: DAY_3_TASKS,
    4: DAY_4_TASKS,
    5: DAY_5_TASKS,
}


def get_tasks_for_day(day: int) -> List[str]:
    """Return the checklist for a given launch day (1-20)."""
    return DAILY_TASKS.get(day, ONGOING_TASKS)


def get_completed_indices(data: Dict[str, Any], day: int) -> List[int]:
    """Return the list of completed task indices for the given day."""
    prefix = f"{day}:"
    completed = []
    for entry in data.get("tasks_completed", []):
        if entry.startswith(prefix):
            try:
                completed.append(int(entry.split(":", 1)[1]))
            except (ValueError, IndexError):
                continue
    return completed


ENCOURAGEMENTS: List[str] = [
    "🔥 Nice work. Momentum compounds -- keep stacking wins.",
    "💪 Done is better than perfect. On to the next one.",
    "🚀 That's one more brick in the $100K wall.",
    "✅ Logged. Small daily actions are what actually build this.",
    "🎯 Stacking tasks like that is exactly how the 20 days get won.",
    "⚡ Consistency beats intensity. Great job checking that off.",
]


# ======================================================================
# Claude content generation
# ======================================================================

DEFAULT_NICHE = "AI-powered digital products and side hustles"

CONTENT_SPECS: Dict[str, Dict[str, Any]] = {
    "youtube": {
        "label": "YouTube Video Scripts",
        "count": 5,
        "metric": "youtube_videos",
        "max_tokens": 4096,
        "system": (
            "You are an expert YouTube scriptwriter and content strategist "
            "who writes high-retention scripts for creators in the {niche} space."
        ),
        "user": (
            "Generate {count} complete YouTube video script outlines for 10-minute "
            "videos about {niche}. For EACH video provide:\n"
            "1. An attention-grabbing title (under 60 characters)\n"
            "2. A 15-second hook script for the very first seconds\n"
            "3. A full outline: Intro -> 3-5 Main Points (one sentence on what to say "
            "for each) -> Call-to-action\n"
            "4. 3 SEO tags/keywords\n\n"
            "Number each video clearly (Video 1, Video 2, ...) and format with "
            "headers so it's ready to film today."
        ),
    },
    "blog": {
        "label": "Blog Post Outlines",
        "count": 5,
        "metric": "blog_posts",
        "max_tokens": 4096,
        "system": (
            "You are an SEO content strategist who writes high-converting blog "
            "outlines for the {niche} niche."
        ),
        "user": (
            "Generate {count} SEO-optimized blog post outlines (~2,000 words each) "
            "about {niche}. For EACH post include:\n"
            "1. SEO title with a target keyword\n"
            "2. Meta description (under 155 characters)\n"
            "3. H2/H3 section headers with a 1-2 sentence description of what each "
            "section covers\n"
            "4. A content upgrade / lead magnet idea to capture emails\n"
            "5. Suggested internal/external link opportunities\n\n"
            "Number each post clearly and format so it's ready to write from "
            "immediately."
        ),
    },
    "email": {
        "label": "Email Sequence",
        "count": 5,
        "metric": None,
        "max_tokens": 4096,
        "system": (
            "You are a direct-response email copywriter who writes welcome "
            "sequences that convert cold subscribers into buyers in the {niche} "
            "space."
        ),
        "user": (
            "Write a 5-email welcome sequence for new subscribers in {niche}. "
            "The emails, in order, must be:\n"
            "1. Welcome -- deliver the promised freebie, set expectations\n"
            "2. Value -- teach one genuinely useful, actionable tip\n"
            "3. Proof -- a case study, result, or testimonial-style story\n"
            "4. Objection-handling -- address the #1 reason people don't buy\n"
            "5. Scarcity -- urgency/deadline-driven push to purchase\n\n"
            "For EACH email give: Subject line, Preview text, and full body copy "
            "ready to paste into an email tool."
        ),
    },
    "reddit": {
        "label": "Reddit Comments",
        "count": 10,
        "metric": "reddit_posts",
        "max_tokens": 3072,
        "system": (
            "You are a genuine, helpful member of Reddit communities about "
            "{niche}. You never sound promotional or salesy."
        ),
        "user": (
            "Write {count} authentic, genuinely helpful Reddit comments/replies "
            "for subreddits about {niche}. Each comment should:\n"
            "- Lead with real value or a direct answer to a plausible question\n"
            "- Sound like a real person, not an ad -- varied tone, length, and "
            "voice across the {count} comments\n"
            "- Only subtly mention a relevant resource/product where natural, "
            "never as a hard sell\n"
            "- Avoid spammy language, links, or anything that reads as marketing\n\n"
            "Number each comment 1-{count}."
        ),
    },
    "twitter": {
        "label": "Twitter/X Threads",
        "count": 20,
        "metric": "twitter_posts",
        "max_tokens": 6144,
        "system": (
            "You are a Twitter/X growth expert who writes high-engagement threads "
            "about {niche}."
        ),
        "user": (
            "Generate {count} Twitter/X threads (3-5 tweets each) about {niche}. "
            "Each thread needs:\n"
            "- Tweet 1: a strong hook that stops the scroll\n"
            "- 2-3 body tweets packed with real value/insight\n"
            "- A final tweet with a clear call-to-action\n"
            "- 2-3 relevant hashtags total per thread (not per tweet)\n\n"
            "Number the threads (Thread 1, Thread 2, ...) and number the tweets "
            "within each thread (1/, 2/, etc.)."
        ),
    },
    "product": {
        "label": "Product Descriptions",
        "count": 3,
        "metric": None,
        "max_tokens": 2048,
        "system": (
            "You are a direct-response copywriter who writes high-converting "
            "digital product sales pages for the {niche} niche."
        ),
        "user": (
            "Write 3 product descriptions/sales pages for digital products in "
            "{niche}, priced at $27, $47, and $97. For EACH product include:\n"
            "1. Product name\n"
            "2. One-line value proposition\n"
            "3. Target buyer description\n"
            "4. 5-7 bullet-point benefits (not just features)\n"
            "5. An FAQ section addressing 2 common objections\n"
            "6. A scarcity or bonus element appropriate to the price point\n\n"
            "Clearly label which product is the $27, $47, and $97 tier."
        ),
    },
}


class ContentGenerationError(Exception):
    """Raised when the Claude API call fails or is misconfigured."""


async def generate_with_claude(content_type: str, niche: str) -> str:
    """Call the Claude API and return generated launch content as text.

    Runs the blocking Anthropic SDK call in a worker thread so it never
    blocks the bot's asyncio event loop.
    """
    if _anthropic_client is None:
        raise ContentGenerationError(
            "ANTHROPIC_API_KEY is not configured. Add it to your .env file "
            "and restart the bot."
        )

    spec = CONTENT_SPECS[content_type]
    system_prompt = spec["system"].format(niche=niche)
    user_prompt = spec["user"].format(niche=niche, count=spec["count"])

    def _call() -> str:
        response = _anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=spec["max_tokens"],
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )

    try:
        text = await asyncio.to_thread(_call)
    except anthropic.APIError as exc:  # type: ignore[union-attr]
        logger.error("Claude API error while generating %s: %s", content_type, exc)
        raise ContentGenerationError(
            "Claude API request failed. Check your ANTHROPIC_API_KEY, account "
            "credits, and try again in a moment."
        ) from exc
    except Exception as exc:  # pragma: no cover - defensive catch-all
        logger.exception("Unexpected error generating %s content", content_type)
        raise ContentGenerationError(f"Unexpected error: {exc}") from exc

    if not text.strip():
        raise ContentGenerationError("Claude returned an empty response. Try again.")
    return text.strip()


def split_message(text: str, limit: int = 3800) -> List[str]:
    """Split text into Telegram-safe chunks (max message length is 4096)."""
    if len(text) <= limit:
        return [text]

    chunks: List[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n\n", 0, limit)
        if split_at == -1:
            split_at = remaining.rfind("\n", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


# ======================================================================
# Access control
# ======================================================================

def restricted(handler):
    """Decorator that limits bot usage to TELEGRAM_ALLOWED_USER_ID, if set."""

    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if TELEGRAM_ALLOWED_USER_ID is not None:
            user = update.effective_user
            if user is None or user.id != TELEGRAM_ALLOWED_USER_ID:
                if update.message:
                    await update.message.reply_text(
                        "🚫 This bot is private and configured for a specific user."
                    )
                logger.warning(
                    "Blocked unauthorized access attempt from user_id=%s",
                    user.id if user else "unknown",
                )
                return
        return await handler(update, context)

    return wrapper


# ======================================================================
# Command handlers
# ======================================================================

@restricted
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start - Welcome message, current day, and command overview."""
    data = load_data()
    day = get_current_day(data)
    remaining = get_days_remaining(day)

    # Remember this chat so scheduled auto-generation (if enabled) has
    # somewhere to deliver content.
    if data.get("chat_id") != update.effective_chat.id:
        data["chat_id"] = update.effective_chat.id
        await save_data(data)

    message = (
        "🚀 *Welcome to the 100K Launch Bot!*\n\n"
        f"You're on *Day {day} of {LAUNCH_LENGTH_DAYS}* "
        f"({get_launch_status_label(day)}) -- {remaining} days remaining.\n\n"
        "*Available commands:*\n"
        "/day -- Where you are in the 20-day launch\n"
        "/checklist -- Today's tasks and your progress\n"
        "/done \\[task] -- Mark a task complete\n"
        "/generate \\[type] -- Create AI content (youtube, blog, email, reddit, "
        "twitter, product)\n"
        "/stats -- Your revenue and metrics dashboard\n"
        "/track \\[metric] \\[value] -- Update a metric\n"
        "/help -- Full command reference\n\n"
        "Let's get to $100K. Start with `/checklist`."
    )
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


@restricted
async def day_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/day - Show which day of 20 we're on and days remaining."""
    data = load_data()
    day = get_current_day(data)
    remaining = get_days_remaining(day)
    progress_bar = _progress_bar(day / LAUNCH_LENGTH_DAYS)

    message = (
        f"📅 *Day {day} of {LAUNCH_LENGTH_DAYS}* -- {get_launch_status_label(day)}\n"
        f"{progress_bar}\n\n"
        f"⏳ {remaining} day{'s' if remaining != 1 else ''} remaining\n"
        f"🗓 Launch started: {data.get('start_date')}\n\n"
        "Run /checklist to see today's tasks."
    )
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


@restricted
async def checklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/checklist - Show today's tasks with completion status and progress."""
    data = load_data()
    day = get_current_day(data)
    tasks = get_tasks_for_day(day)
    completed = set(get_completed_indices(data, day))

    lines = [f"📋 *Day {day} Checklist* ({len(tasks)} tasks)\n"]
    for i, task in enumerate(tasks):
        mark = "✅" if i in completed else "▫️"
        lines.append(f"{mark} {task}")

    pct = round((len(completed) / len(tasks)) * 100) if tasks else 0
    lines.append(f"\n📊 Progress: {pct}% ({len(completed)}/{len(tasks)})")
    lines.append(_progress_bar(pct / 100))
    example = " ".join(tasks[0].split()[:3]).lower()
    lines.append(
        "\nUse `/done <part of a task name>` to check one off, e.g. "
        f"`/done {example}`"
    )

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


@restricted
async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/done [task name] - Mark today's matching task as complete."""
    if not context.args:
        await update.message.reply_text(
            "Usage: `/done <part of a task name>`\n"
            "Example: `/done gumroad`\n\n"
            "Run /checklist to see today's exact task wording.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    query = " ".join(context.args).strip().lower()
    data = load_data()
    day = get_current_day(data)
    tasks = get_tasks_for_day(day)

    matches = [i for i, task in enumerate(tasks) if query in task.lower()]

    if not matches:
        task_list = "\n".join(f"- {t}" for t in tasks)
        await update.message.reply_text(
            f"❌ No task matching '{query}' found for Day {day}.\n\n"
            f"Today's tasks:\n{task_list}"
        )
        return

    if len(matches) > 1:
        options = "\n".join(f"- {tasks[i]}" for i in matches)
        await update.message.reply_text(
            f"⚠️ That matched {len(matches)} tasks -- be more specific:\n{options}"
        )
        return

    idx = matches[0]
    key = f"{day}:{idx}"
    if key in data["tasks_completed"]:
        await update.message.reply_text(f"You've already marked that done ✅\n\n\"{tasks[idx]}\"")
        return

    data["tasks_completed"].append(key)
    await save_data(data)

    completed = get_completed_indices(data, day)
    pct = round((len(completed) / len(tasks)) * 100)
    encouragement = random.choice(ENCOURAGEMENTS)

    await update.message.reply_text(
        f"✅ Marked complete: \"{tasks[idx]}\"\n\n"
        f"{encouragement}\n\n"
        f"📊 Day {day} progress: {pct}% ({len(completed)}/{len(tasks)})"
    )


@restricted
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/stats - Revenue and metrics dashboard vs. expected targets."""
    data = load_data()
    day = get_current_day(data)
    metrics = data.get("metrics", {})
    revenue = data.get("revenue", 0)

    expected_revenue = round(FINAL_TARGETS["revenue"] * day / LAUNCH_LENGTH_DAYS)
    revenue_pct_of_final = round((revenue / FINAL_TARGETS["revenue"]) * 100, 1)

    lines = [
        f"📊 *Launch Dashboard -- Day {day}/{LAUNCH_LENGTH_DAYS}*\n",
        f"💰 *Revenue:* ${revenue:,.2f} of ${FINAL_TARGETS['revenue']:,} goal "
        f"({revenue_pct_of_final}%)",
        f"   Expected by today: ${expected_revenue:,} -- "
        f"{_status_emoji(revenue, expected_revenue)}\n",
        "*Metrics:*",
    ]

    labels = {
        "views": "👁 Views",
        "email_subscribers": "📧 Email subscribers",
        "sales": "🛒 Sales",
        "youtube_videos": "📹 YouTube videos",
        "blog_posts": "📝 Blog posts",
        "reddit_posts": "💬 Reddit posts",
        "twitter_posts": "🐦 Twitter posts",
    }

    for key, label in labels.items():
        current = metrics.get(key, 0)
        target_final = FINAL_TARGETS.get(key, 0)
        expected_now = round(target_final * day / LAUNCH_LENGTH_DAYS)
        status = _status_emoji(current, expected_now)
        lines.append(
            f"{label}: {current:,.0f} (expected ~{expected_now:,} today, "
            f"goal {target_final:,}) {status}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


VALID_TRACK_METRICS = list(DEFAULT_METRICS.keys()) + ["revenue"]


@restricted
async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/track [metric] [value] - Set a metric to a new value and save it."""
    if len(context.args) < 2:
        metric_list = ", ".join(VALID_TRACK_METRICS)
        await update.message.reply_text(
            "Usage: `/track <metric> <value>`\n"
            f"Valid metrics: {metric_list}\n"
            "Example: `/track views 1500`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    metric = context.args[0].lower()
    raw_value = context.args[1]

    if metric not in VALID_TRACK_METRICS:
        metric_list = ", ".join(VALID_TRACK_METRICS)
        await update.message.reply_text(
            f"❌ Unknown metric '{metric}'.\nValid metrics: {metric_list}"
        )
        return

    try:
        value = float(raw_value)
    except ValueError:
        await update.message.reply_text(
            f"❌ '{raw_value}' isn't a number. Example: `/track sales 12`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if value < 0:
        await update.message.reply_text("❌ Metrics can't be negative.")
        return

    data = load_data()
    if metric == "revenue":
        data["revenue"] = round(value, 2)
        display_value = f"${value:,.2f}"
    else:
        # Whole-number metrics (views, sales, post counts, etc.)
        value = round(value)
        data.setdefault("metrics", {})[metric] = value
        display_value = f"{value:,.0f}"

    await save_data(data)

    await update.message.reply_text(f"✅ Updated *{metric}* to {display_value}", parse_mode=ParseMode.MARKDOWN)


@restricted
async def generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/generate [type] [optional topic] - Generate AI launch content."""
    if not context.args:
        types_list = ", ".join(CONTENT_SPECS.keys())
        await update.message.reply_text(
            "Usage: `/generate <type> [optional topic]`\n"
            f"Types: {types_list}\n"
            "Example: `/generate youtube AI productivity tools`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    content_type = context.args[0].lower()
    if content_type not in CONTENT_SPECS:
        types_list = ", ".join(CONTENT_SPECS.keys())
        await update.message.reply_text(f"❌ Unknown type '{content_type}'.\nValid types: {types_list}")
        return

    niche = " ".join(context.args[1:]).strip() or DEFAULT_NICHE
    spec = CONTENT_SPECS[content_type]

    status_msg = await update.message.reply_text(
        f"⏳ Generating {spec['count']} {spec['label'].lower()}... this can take up to a minute."
    )

    try:
        content = await generate_with_claude(content_type, niche)
    except ContentGenerationError as exc:
        await status_msg.edit_text(f"❌ {exc}")
        return

    header = f"✨ *{spec['label']}* -- {niche}\n\n"
    chunks = split_message(header + content)

    await status_msg.delete()
    for chunk in chunks:
        await update.message.reply_text(chunk, parse_mode=None)

    await update.message.reply_text(
        "Tip: use /track to log results once you publish this content, e.g. "
        "`/track youtube_videos 1`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def auto_generate_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Scheduled job: generate the next content type in rotation and push it
    to the chat that last ran /start. No-ops until /start has been run once
    (there's nowhere to deliver content to yet).
    """
    data = load_data()
    chat_id = data.get("chat_id")
    if chat_id is None:
        logger.info("Auto-generate skipped: no chat has run /start yet.")
        return
    if not AUTO_GENERATE_TYPES:
        return

    idx = data.get("auto_generate_index", 0) % len(AUTO_GENERATE_TYPES)
    content_type = AUTO_GENERATE_TYPES[idx]
    data["auto_generate_index"] = (idx + 1) % len(AUTO_GENERATE_TYPES)
    await save_data(data)

    if content_type not in CONTENT_SPECS:
        logger.warning("Auto-generate: '%s' in AUTO_GENERATE_TYPES is not a valid type.", content_type)
        return

    spec = CONTENT_SPECS[content_type]
    try:
        content = await generate_with_claude(content_type, DEFAULT_NICHE)
    except ContentGenerationError as exc:
        logger.error("Auto-generate failed for %s: %s", content_type, exc)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⚠️ Scheduled auto-generation of {spec['label']} failed: {exc}",
        )
        return

    header = f"🤖 *Auto-generated {spec['label']}*\n\n"
    for chunk in split_message(header + content):
        await context.bot.send_message(chat_id=chat_id, text=chunk, parse_mode=None)
    logger.info("Auto-generated %s content delivered to chat_id=%s", content_type, chat_id)


@restricted
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help - Full command reference with usage examples."""
    message = (
        "🛟 *100K Launch Bot -- Command Reference*\n\n"
        "*/start*\n  Welcome message and current day overview.\n\n"
        "*/day*\n  Shows which day of 20 you're on and days remaining.\n\n"
        "*/checklist*\n  Shows today's tasks with ✅ for completed ones and your "
        "progress percentage.\n\n"
        "*/done <task name>*\n  Marks a task complete by matching part of its "
        "text.\n  Example: `/done youtube video`\n\n"
        "*/generate <type> [topic]*\n  Generates AI content with Claude.\n"
        "  Types: youtube, blog, email, reddit, twitter, product\n"
        "  Example: `/generate blog AI side hustles`\n\n"
        "*/stats*\n  Revenue + metrics dashboard, compared against the pace "
        "needed to hit $100K by day 20.\n\n"
        "*/track <metric> <value>*\n  Updates a metric to a new value.\n"
        f"  Metrics: {', '.join(VALID_TRACK_METRICS)}\n"
        "  Example: `/track revenue 250`\n\n"
        "*/help*\n  This message.\n\n"
        "See README.md in the project for full setup and deployment docs."
    )
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fallback for unrecognized commands."""
    if update.message:
        await update.message.reply_text(
            "🤔 I don't recognize that command. Try /help to see everything I can do."
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global error handler so a single failing update never crashes the bot."""
    logger.error("Unhandled exception while processing update: %s", update, exc_info=context.error)
    if isinstance(update, Update) and update.message:
        try:
            await update.message.reply_text(
                "⚠️ Something went wrong handling that command. It's been logged -- "
                "please try again."
            )
        except Exception:  # pragma: no cover - best-effort notification
            logger.exception("Failed to notify user about error")


# ======================================================================
# Small formatting helpers
# ======================================================================

def _progress_bar(fraction: float, length: int = 10) -> str:
    """Render a simple text progress bar, e.g. '[██████----] 60%'."""
    fraction = max(0.0, min(1.0, fraction))
    filled = round(fraction * length)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {round(fraction * 100)}%"


def _status_emoji(current: float, expected: float) -> str:
    """✅ if at/ahead of pace, ⚠️ if somewhat behind, 🔴 if far behind."""
    if expected <= 0:
        return "✅"
    ratio = current / expected
    if ratio >= 1.0:
        return "✅ on track"
    if ratio >= 0.5:
        return "⚠️ behind"
    return "🔴 far behind"


# ======================================================================
# Application bootstrap
# ======================================================================

def _validate_config() -> None:
    """Fail fast with a clear message if required configuration is missing."""
    if not TELEGRAM_BOT_TOKEN:
        sys.exit(
            "ERROR: TELEGRAM_BOT_TOKEN is not set.\n"
            "1. Copy .env.example to .env\n"
            "2. Get a token from @BotFather on Telegram\n"
            "3. Put it in .env as TELEGRAM_BOT_TOKEN=...\n"
        )
    if anthropic is None:
        logger.warning(
            "The 'anthropic' package is not installed. /generate will not work "
            "until you `pip install -r requirements.txt`."
        )
    elif not ANTHROPIC_API_KEY:
        logger.warning(
            "ANTHROPIC_API_KEY is not set. /generate will reply with a config "
            "error until it's added to .env."
        )


def main() -> None:
    """Configure and run the bot with long polling."""
    _validate_config()
    load_data()  # ensure data.json exists before we start serving traffic

    if ENABLE_KEEP_ALIVE:
        import keep_alive

        keep_alive.start()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("day", day_command))
    application.add_handler(CommandHandler("checklist", checklist_command))
    application.add_handler(CommandHandler("done", done_command))
    application.add_handler(CommandHandler("generate", generate_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("track", track_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    application.add_error_handler(error_handler)

    if AUTO_GENERATE_ENABLED:
        if application.job_queue is None:
            logger.warning(
                "AUTO_GENERATE_ENABLED is set but the JobQueue isn't available. "
                "Install the job-queue extra: pip install 'python-telegram-bot[job-queue]'."
            )
        elif not AUTO_GENERATE_TYPES:
            logger.warning("AUTO_GENERATE_ENABLED is set but AUTO_GENERATE_TYPES is empty.")
        else:
            application.job_queue.run_repeating(
                auto_generate_job,
                interval=AUTO_GENERATE_INTERVAL_HOURS * 3600,
                first=30,
                name="auto_generate",
            )
            logger.info(
                "Auto-generate scheduled every %.1fh, rotating through: %s",
                AUTO_GENERATE_INTERVAL_HOURS,
                ", ".join(AUTO_GENERATE_TYPES),
            )

    logger.info(
        "100K Launch Bot starting up (model=%s, data_file=%s, restricted=%s)",
        CLAUDE_MODEL,
        DATA_FILE,
        bool(TELEGRAM_ALLOWED_USER_ID),
    )
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
