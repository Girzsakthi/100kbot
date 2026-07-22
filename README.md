# 100K Launch Bot

A Telegram bot that runs a 20-day, $100K digital-product launch: daily
checklists, AI-generated content (YouTube scripts, blog posts, email
sequences, Reddit comments, Twitter threads, product descriptions), and a
revenue/metrics dashboard. All state is stored in a single local JSON file --
no database required.

---

## Features

- **`/start`** -- Welcome message and current day overview.
- **`/day`** -- Which day of the 20-day launch you're on, and days remaining.
- **`/checklist`** -- Today's tasks with ✅ for completed ones and a progress bar.
- **`/done <task>`** -- Mark a task complete by matching part of its text.
- **`/generate <type> [topic]`** -- Generate AI content with Claude.
  Types: `youtube`, `blog`, `email`, `reddit`, `twitter`, `product`.
- **`/stats`** -- Revenue and metrics dashboard, compared against the pace
  needed to hit $100K by day 20.
- **`/track <metric> <value>`** -- Update a metric (views, sales, revenue, etc).
- **`/help`** -- Full command reference.

Data (launch start date, completed tasks, metrics, revenue) persists to
`data.json` and survives restarts.

---

## Requirements

- Python 3.9+
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- An Anthropic API key (from the [Anthropic Console](https://console.anthropic.com/))

---

## Setup

### 1. Clone / download this project

```bash
git clone <this-repo-url>
cd 100kbot
```

### 2. Run the setup script

```bash
chmod +x setup.sh
./setup.sh
```

This creates a virtual environment (skipped automatically on Replit),
installs dependencies from `requirements.txt`, and copies `.env.example` to
`.env`.

### 3. Get your API keys

**Telegram bot token:**

1. Open Telegram and message [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts (choose a name and username).
3. BotFather replies with a token like `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`.
4. Copy it into `.env` as `TELEGRAM_BOT_TOKEN`.

**Anthropic (Claude) API key:**

1. Go to [console.anthropic.com](https://console.anthropic.com/) and sign in.
2. Open **API Keys** in the left sidebar.
3. Click **Create Key** and copy the value (starts with `sk-ant-`).
4. Paste it into `.env` as `ANTHROPIC_API_KEY`.

**(Optional) Restrict the bot to yourself:**

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram to get your
   numeric user ID.
2. Put it in `.env` as `TELEGRAM_ALLOWED_USER_ID`. Leave blank to let anyone
   who finds the bot use it.

### 4. Edit `.env`

```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_ALLOWED_USER_ID=
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-opus-4-8
DATA_FILE=data.json
LAUNCH_START_DATE=
```

Leave `LAUNCH_START_DATE` blank to have the bot start counting from the day
you first run it, or set it to a `YYYY-MM-DD` date to backdate/schedule the
launch.

### 5. Run the bot

```bash
source venv/bin/activate   # skip on Replit
python bot.py
```

Open Telegram, find your bot by the username you gave BotFather, and send
`/start`.

---

## Deploying to Replit (free 24/7 hosting)

1. Create a new Repl, choose **Import from GitHub** (or upload the project
   files), select the Python template.
2. In the Repl, open the **Secrets** tool (padlock icon in the sidebar) and
   add:
   - `TELEGRAM_BOT_TOKEN`
   - `ANTHROPIC_API_KEY`
   - `TELEGRAM_ALLOWED_USER_ID` (optional)
   - `CLAUDE_MODEL` (optional, defaults to `claude-opus-4-8`)
3. Replit secrets are injected as environment variables automatically --
   `python-dotenv` will simply find nothing in `.env` and fall through to
   them, so you don't need to upload your `.env` file to Replit at all.
4. Set the Run command to `python bot.py` (or run `./setup.sh && python bot.py`
   once to install dependencies, then just `python bot.py` after).
5. Click **Run**. The console should log `100K Launch Bot starting up...`.
6. To keep it running 24/7 on Replit's free tier, use an uptime pinger
   (e.g. UptimeRobot) hitting a keep-alive endpoint, or use Replit's
   "Always On" / Reserved VM feature if available on your plan.

**Persisting data on Replit:** `data.json` is written to the Repl's
filesystem, which persists across restarts of the same Repl (but is not
guaranteed across a full Repl deletion/recreation). For long-term durability,
periodically download `data.json` as a backup.

---

## Data storage format

`data.json` (created automatically on first run):

```json
{
  "start_date": "2025-01-15",
  "tasks_completed": ["1:0", "1:3", "2:1"],
  "metrics": {
    "views": 0,
    "email_subscribers": 0,
    "sales": 0,
    "youtube_videos": 0,
    "blog_posts": 0,
    "reddit_posts": 0,
    "twitter_posts": 0
  },
  "revenue": 0
}
```

`tasks_completed` entries are `"<day>:<task_index>"` strings, e.g. `"1:0"`
means the first task of Day 1 is done.

---

## The 20-day checklist

| Day(s) | Focus | Tasks |
|---|---|---|
| 1 | Setup | 8 tasks: Gumroad account + products, Medium, YouTube channel, MailerLite, Twitter/X profile, join Reddit communities, tracking spreadsheet |
| 2 | First execution | 4 tasks: first video, Reddit replies, blog posts, Twitter threads |
| 3-5 | Content production | 4 tasks/day: more videos, blog posts, Reddit engagement, email automation |
| 6-20 | Ongoing growth | 4 tasks/day: upload video, check metrics, reply to comments, optimize underperforming content |

Run `/checklist` any day to see the exact task list and your progress.

---

## Content generation types

| Type | Command example | What it generates |
|---|---|---|
| YouTube scripts | `/generate youtube AI side hustles` | 5 script outlines: title, hook, outline, SEO tags |
| Blog outlines | `/generate blog passive income` | 5 SEO-optimized ~2,000-word outlines |
| Email sequence | `/generate email productivity tools` | 5-email welcome sequence (welcome/value/proof/objection/scarcity) |
| Reddit comments | `/generate reddit freelancing` | 10 authentic, non-promotional comments |
| Twitter threads | `/generate twitter no-code tools` | 20 threads of 3-5 tweets each |
| Product descriptions | `/generate product AI templates` | 3 sales pages for $27/$47/$97 products |

The topic/niche is optional -- omit it to use the default niche
("AI-powered digital products and side hustles").

---

## Troubleshooting

**"TELEGRAM_BOT_TOKEN is not set" and the bot exits immediately**
Copy `.env.example` to `.env` and fill in a real token from @BotFather.

**`/generate` replies with a config error**
`ANTHROPIC_API_KEY` is missing or invalid. Double-check the key in `.env` (or
Replit Secrets) and that your Anthropic account has available credits.

**Bot doesn't respond at all**
- Confirm the process is actually running and didn't crash (check the console/logs).
- Make sure you're messaging the correct bot username.
- If `TELEGRAM_ALLOWED_USER_ID` is set, confirm it matches your numeric Telegram user ID.

**Data resets after a restart**
Make sure `DATA_FILE` points to a persistent path and that the process has
write permission to that directory. On Replit, avoid using `/tmp` as the data
directory.

**`/done` says "no task matching" or "matched N tasks"**
Run `/checklist` to see the exact task wording for the current day, then
use a more specific (or shorter, more unique) substring.

**Claude API errors / rate limits**
The bot surfaces a friendly error message and logs the details. Wait a
moment and retry `/generate`; check your Anthropic Console for rate limit or
billing issues if it persists.

---

## Project structure

```
100kbot/
├── bot.py            # Main bot (all commands, Claude integration, storage)
├── requirements.txt   # Python dependencies
├── .env.example       # Environment variable template
├── setup.sh           # Automated setup script
├── README.md          # This file
└── data.json          # Created automatically on first run (persistent storage)
```
