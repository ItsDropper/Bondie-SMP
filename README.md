# Orb SMP Discord Bot

A minimal Discord bot with:
- `/say <message> [channel]` — Admin-only. Makes the bot post a message.
- `/ticket-panel [channel] [title] [description]` — Admin-only. Sends a support panel with a
  "Create Ticket" button. Clicking it asks one question, **"Why are you creating this ticket?"**,
  then creates a private ticket channel under the configured category and pings the user
  (plus your support role, if you set one). A "Close Ticket" button is included for cleanup.

## 1. Create the bot

1. Go to https://discord.com/developers/applications → **New Application**.
2. Go to **Bot** → **Reset Token** → copy it (this is your `DISCORD_TOKEN`).
3. Under **Bot**, make sure **Public Bot** is off if you don't want others adding it.
4. Copy the **Application ID** from **General Information** (this is your `CLIENT_ID`).
5. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Manage Channels`, `Send Messages`, `Embed Links`, `Read Message History`,
     `View Channels`
   - Open the generated URL and invite the bot to your server.

## 2. Install & configure

```bash
npm install
cp .env.example .env
```

Fill in `.env`:

```
DISCORD_TOKEN=your-bot-token
CLIENT_ID=your-application-id
GUILD_ID=your-server-id          # optional but recommended for instant command updates
TICKET_CATEGORY_ID=1529393937171746918
SUPPORT_ROLE_ID=                 # optional: role to ping + auto-add to every ticket
```

To get your server ID / category ID: enable Developer Mode in Discord
(Settings → Advanced → Developer Mode), then right-click the server or category → **Copy ID**.

Make sure the ID in `TICKET_CATEGORY_ID` is an actual **category**, and that the bot's role is
positioned high enough in the role list / has `Manage Channels` so it can create channels there.

## 3. Deploy the commands and start the bot

```bash
npm run deploy   # registers /say and /ticket-panel
npm start        # logs the bot in
```

## Deploying on Render

This repo includes a `render.yaml` blueprint with your `CLIENT_ID`, `GUILD_ID`,
`TICKET_CATEGORY_ID`, and `SUPPORT_ROLE_ID` already filled in (none of these are secret).
The only thing you need to type in yourself is `DISCORD_TOKEN`.

1. Push this repo to GitHub (make sure `.env` is **not** committed — it's already in
   `.gitignore`).
2. In the Render dashboard: **New → Blueprint**, connect the repo, and Render will detect
   `render.yaml` automatically.
3. When prompted, paste in your `DISCORD_TOKEN` (this is the only manual field).
4. Click **Apply** / **Deploy**. Render will:
   - Provision a Background Worker (correct for a Discord bot — no HTTP port needed)
   - Run `npm install && node deploy-commands.js` on every build, which registers/updates your
     slash commands automatically — no need to run that step locally
   - Start the bot with `node index.js`

Note: Render's Background Workers don't have a free tier — the blueprint uses the `starter`
plan (~$7/mo) so the bot stays online 24/7 instead of sleeping.

If you ever change `CLIENT_ID`, `GUILD_ID`, `TICKET_CATEGORY_ID`, or `SUPPORT_ROLE_ID`, just
edit the values in `render.yaml`, commit, and push — Render will pick up the change on the next
deploy.

## Usage

- Run `/ticket-panel` in whichever channel you want the support panel to live.
- A user clicks **Create Ticket**, answers the one question in the popup, and a private channel
  is created for them under your configured category.
- Anyone with Administrator, the support role (if set), or the ticket opener can press
  **Close Ticket** to delete the channel.

## Notes

- Both commands are restricted at the Discord permission level (`Administrator`) via
  `setDefaultMemberPermissions`, and double-checked in code — server owners can technically
  loosen this in **Server Settings → Integrations**, so if you want it locked down further,
  restrict it there too.
- One open ticket per user is enforced (checked via the channel topic).
