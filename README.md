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
- **`/generate <type> [topic]`** -- Generate AI content with Google Gemini
  (free tier). Types: `youtube`, `blog`, `email`, `reddit`, `twitter`, `product`.
- **`/stats`** -- Revenue and metrics dashboard, compared against the pace
  needed to hit $100K by day 20.
- **`/track <metric> <value>`** -- Update a metric (views, sales, revenue, etc).
- **`/help`** -- Full command reference.
- **Scheduled auto-generation** (optional) -- automatically runs `/generate`
  on a timer and pushes the result to your chat, rotating through content
  types, so you don't have to trigger it by hand. See below.

Data (launch start date, completed tasks, metrics, revenue) persists to
`data.json` and survives restarts.

---

## Requirements

- Python 3.9+
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- A Google Gemini API key (free, from [Google AI Studio](https://aistudio.google.com/apikey))

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

**Google Gemini API key (free):**

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and
   sign in with a Google account.
2. Click **Create API key**. No credit card is required for the free tier.
3. Copy the key it gives you.
4. Paste it into `.env` as `GEMINI_API_KEY`.

**(Optional) Restrict the bot to yourself:**

1. Message [@userinfobot](https://t.me/userinfobot) on Telegram to get your
   numeric user ID.
2. Put it in `.env` as `TELEGRAM_ALLOWED_USER_ID`. Leave blank to let anyone
   who finds the bot use it.

### 4. Edit `.env`

```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_ALLOWED_USER_ID=
GEMINI_API_KEY=AIzaSy...
GEMINI_MODEL=gemini-2.0-flash
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

This repo ships a `.replit` config, so importing it runs `setup.sh` and then
`bot.py` automatically -- no manual run-command setup needed.

1. On [replit.com](https://replit.com), click **Create App** -> **Import
   from GitHub** and point it at this repo (or upload the project files
   into a new Python Repl).
2. Open the **Secrets** tool (padlock icon in the sidebar) and add:
   - `TELEGRAM_BOT_TOKEN`
   - `GEMINI_API_KEY`
   - `TELEGRAM_ALLOWED_USER_ID` (optional)
   - `GEMINI_MODEL` (optional, defaults to `gemini-2.0-flash`)
   - `ENABLE_KEEP_ALIVE` = `true` (turns on the keep-alive web server below)
3. Replit secrets are injected as environment variables automatically --
   `python-dotenv` finds nothing in `.env` and falls through to them, so you
   don't need to upload a `.env` file to Replit at all.
4. Click **Run**. The console should log `100K Launch Bot starting up...`
   and, with `ENABLE_KEEP_ALIVE=true`, `Keep-alive server started on port ...`.
5. **Keep it running 24/7 (free tier):** Replit's free tier spins a Repl
   down after it stops receiving HTTP traffic. This repo's `keep_alive.py`
   runs a tiny web server (enabled via the `ENABLE_KEEP_ALIVE` secret above)
   specifically so an external pinger can keep the process awake:
   1. Copy your Repl's public URL (shown once it's running -- looks like
      `https://<repl-name>.<username>.repl.co`).
   2. Create a free monitor at [UptimeRobot](https://uptimerobot.com) (or
      [cron-job.org](https://cron-job.org)) that does an HTTP GET on that
      URL every 5 minutes.
   3. As long as the monitor keeps pinging, the Repl -- and the Telegram
      bot's polling loop running alongside it -- stays alive.
   - If your Replit plan includes "Always On" or a Reserved VM, use that
     instead and skip the external pinger (you can leave
     `ENABLE_KEEP_ALIVE=false` in that case).

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
  "revenue": 0,
  "chat_id": null,
  "auto_generate_index": 0
}
```

`chat_id` is set automatically the first time you run `/start` -- it's how
scheduled auto-generation (see above) knows where to deliver content.
`auto_generate_index` tracks which content type is next in the rotation.

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

## Scheduled auto-generation

Instead of typing `/generate` yourself, the bot can generate content on a
timer and push it straight to your chat -- no external scheduler needed, it
runs inside the same process using `python-telegram-bot`'s built-in JobQueue.

**Setup:**

1. Send `/start` to the bot at least once (this is how it learns which chat
   to deliver auto-generated content to -- it's saved in `data.json`).
2. Set these in `.env` (or Replit Secrets):

   ```bash
   AUTO_GENERATE_ENABLED=true
   AUTO_GENERATE_INTERVAL_HOURS=24
   AUTO_GENERATE_TYPES=youtube,blog,reddit,twitter
   ```
3. Restart the bot. Thirty seconds after startup it runs once immediately
   (so you can confirm it's wired up), then repeats every
   `AUTO_GENERATE_INTERVAL_HOURS`.

**How it rotates:** each run generates the next type in `AUTO_GENERATE_TYPES`
(in order, wrapping back to the start), using the default niche. Change the
niche by editing `DEFAULT_NICHE` in `bot.py` if the default ("AI-powered
digital products and side hustles") doesn't match your launch.

Generated content is delivered as regular messages, headed with
"🤖 Auto-generated ...". It does **not** auto-update your `/stats` metrics --
use `/track` once you've actually published something, same as with a
manual `/generate`.

If `GEMINI_API_KEY` is missing or a request fails, you'll get a short
warning message instead of the content, and the rotation still advances to
the next type on the following run.

---

## Troubleshooting

**"TELEGRAM_BOT_TOKEN is not set" and the bot exits immediately**
Copy `.env.example` to `.env` and fill in a real token from @BotFather.

**`/generate` replies with a config error**
`GEMINI_API_KEY` is missing or invalid. Double-check the key in `.env` (or
Replit Secrets) at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).

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

**Gemini API errors / rate limits**
The bot surfaces a friendly error message and logs the actual error to the
console. Wait a moment and retry `/generate`; the free tier has a requests-
per-minute limit -- if you're hitting it, space out `/generate` calls or
reduce `AUTO_GENERATE_INTERVAL_HOURS`.

---

## Project structure

```
100kbot/
├── bot.py            # Main bot (all commands, Gemini integration, storage)
├── keep_alive.py      # Optional Flask server so free-tier hosts don't sleep the bot
├── .replit            # Replit run/deploy config (auto-detected on import)
├── requirements.txt   # Python dependencies
├── .env.example       # Environment variable template
├── setup.sh           # Automated setup script
├── README.md          # This file
└── data.json          # Created automatically on first run (persistent storage)
```
