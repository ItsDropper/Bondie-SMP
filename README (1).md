# Orb SMP Discord Bot (Python)

A single-file Discord bot with:
- `/say <message> [channel]` — Admin-only. Makes the bot post a message.
- `/ticket-panel [channel] [title] [description]` — Admin-only. Sends a support panel with a
  "Create Ticket" button. Clicking it asks one question, **"Why are you creating this ticket?"**,
  then creates a private ticket channel under `TICKET_CATEGORY_ID` and pings the user (plus a
  support role, if set). Includes a "Close Ticket" button.

It also runs a tiny Flask server on `PORT` alongside the bot, purely so it satisfies Render's
free **Web Service** port check (Discord bots don't normally need this).

## 1. Create the bot

1. https://discord.com/developers/applications → **New Application**.
2. **Bot** tab → **Reset Token** → copy it. This is your `DISCORD_TOKEN`.
3. **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Manage Channels`, `Send Messages`, `Embed Links`, `Read Message History`,
     `View Channels`
   - Open the generated URL and invite the bot to your server.

## 2. Run it locally (optional)

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # fill in DISCORD_TOKEN
python bot.py
```

Slash commands sync automatically on startup (to `GUILD_ID` if set, otherwise globally).

## 3. Deploy on Render as a Web Service (free tier)

1. Push this folder to GitHub.
2. Render dashboard → **New → Web Service** → connect your repo.
3. Settings:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
4. Add environment variables (Environment tab):
   - `DISCORD_TOKEN` — your bot token
   - `GUILD_ID` — `1345829900606771250`
   - `TICKET_CATEGORY_ID` — `1529393937171746918`
   - `SUPPORT_ROLE_ID` — `1529084117906624542` (optional — remove if you don't want it)
5. Deploy.

Render will detect the Flask server binding to the port it assigns and mark the service healthy,
even though the actual "work" (the Discord connection) runs independently on the same process.

### Free tier tradeoff

Render's free Web Service tier spins down after 15 minutes with no HTTP traffic, which will
disconnect the bot. To keep it awake 24/7 for free, use an external uptime pinger (e.g.
UptimeRobot or cron-job.org) to hit your Render URL (`https://your-service.onrender.com`) every
5–10 minutes. This isn't bulletproof — an occasional cold start / brief disconnect is still
possible — but it's the standard free-tier workaround. If you want zero downtime, Render's paid
Starter plan ($7/mo) removes the spin-down entirely.

## Notes

- Both commands are restricted to Administrators via `default_permissions`, and double-checked
  in code.
- Only one open ticket per user is allowed (tracked via the channel topic).
- If you ever change `TICKET_CATEGORY_ID`, `GUILD_ID`, or `SUPPORT_ROLE_ID`, just update the
  Render environment variables and redeploy — no code changes needed.
