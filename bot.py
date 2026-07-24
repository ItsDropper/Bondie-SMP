"""
Orb SMP Discord Bot
--------------------
Commands (all admin/mod-permission gated):
- /say <message> [channel]          Post a message as the bot.
- /ticket-panel [channel] [...]     Send a "Create Ticket" panel. Clicking it asks
                                     one question, then opens a private ticket
                                     channel under TICKET_CATEGORY_ID.
- /announcement [channel]           Compose an announcement privately over DM
                                     (title + message + optional image/file
                                     attachments) so nothing is visible in the
                                     server until it's actually posted.
- /warn /kick /ban /timeout /untimeout /clear   Basic moderation tools.

Runs a tiny Flask server alongside the bot so it can be deployed as a Render
free "Web Service" (which requires something bound to a port).
"""

import os
import asyncio
import threading
from datetime import timedelta

import discord
from discord import app_commands, ui
from discord.ext import commands
from flask import Flask
from dotenv import load_dotenv

load_dotenv()

# ── Configuration ────────────────────────────────────────────────────────────
TOKEN = os.getenv("DISCORD_TOKEN")

GUILD_ID = os.getenv("GUILD_ID")
GUILD_ID = int(GUILD_ID) if GUILD_ID else None

TICKET_CATEGORY_ID = int(os.getenv("TICKET_CATEGORY_ID", "1529393937171746918"))

SUPPORT_ROLE_ID = os.getenv("SUPPORT_ROLE_ID")
SUPPORT_ROLE_ID = int(SUPPORT_ROLE_ID) if SUPPORT_ROLE_ID else None

# Optional: where /warn, /kick, /ban, /timeout, /clear actions get logged.
MOD_LOG_CHANNEL_ID = os.getenv("MOD_LOG_CHANNEL_ID")
MOD_LOG_CHANNEL_ID = int(MOD_LOG_CHANNEL_ID) if MOD_LOG_CHANNEL_ID else None

PORT = int(os.getenv("PORT", "8080"))

# In-memory warning counts: {guild_id: {user_id: count}}. Resets on restart —
# swap for a real database if you want warnings to persist long-term.
warnings: dict[int, dict[int, int]] = {}

# ── Tiny web server (keeps Render's Web Service port check happy) ───────────
web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "Orb SMP bot is running."


def run_web_server():
    web_app.run(host="0.0.0.0", port=PORT)


# ── Discord bot setup ─────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True  # needed to reliably resolve members for moderation commands
bot = commands.Bot(command_prefix="!", intents=intents)


def ticket_topic(user_id: int) -> str:
    return f"orb-ticket:{user_id}"


async def log_mod_action(
    guild: discord.Guild,
    action: str,
    target: discord.abc.User,
    moderator: discord.abc.User,
    reason: str | None,
):
    """Post a moderation action to MOD_LOG_CHANNEL_ID, if configured."""
    if not MOD_LOG_CHANNEL_ID:
        return
    channel = guild.get_channel(MOD_LOG_CHANNEL_ID)
    if not channel:
        return
    embed = discord.Embed(title=f"Moderation: {action}", color=0xE67E22)
    embed.add_field(name="Target", value=f"{target} ({target.id})", inline=False)
    embed.add_field(name="Moderator", value=f"{moderator} ({moderator.id})", inline=False)
    embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
    embed.timestamp = discord.utils.utcnow()
    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        pass


# ══════════════════════════════════════════════════════════════════════════
# Ticket system
# ══════════════════════════════════════════════════════════════════════════
class TicketReasonModal(ui.Modal, title="Create a Support Ticket"):
    reason = ui.TextInput(
        label="Why are you creating this ticket?",
        style=discord.TextStyle.paragraph,
        placeholder="Describe your issue or question...",
        required=True,
        max_length=1000,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        existing = discord.utils.get(
            guild.text_channels, topic=ticket_topic(interaction.user.id)
        )
        if existing:
            await interaction.followup.send(
                f"You already have an open ticket: {existing.mention}", ephemeral=True
            )
            return

        category = guild.get_channel(TICKET_CATEGORY_ID)
        if not isinstance(category, discord.CategoryChannel):
            category = None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            ),
        }
        if SUPPORT_ROLE_ID:
            role = guild.get_role(SUPPORT_ROLE_ID)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                )

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{interaction.user.name}".lower()[:90],
                category=category,
                overwrites=overwrites,
                topic=ticket_topic(interaction.user.id),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "I don't have permission to create ticket channels. "
                "Check my Manage Channels permission and the ticket category.",
                ephemeral=True,
            )
            return
        except Exception as exc:  # noqa: BLE001
            await interaction.followup.send(
                f"Something went wrong creating your ticket: {exc}", ephemeral=True
            )
            return

        embed = discord.Embed(title="New Support Ticket", color=0x2B2D31)
        embed.add_field(name="Opened by", value=interaction.user.mention, inline=True)
        embed.add_field(name="Reason", value=self.reason.value[:1024], inline=False)
        embed.timestamp = discord.utils.utcnow()

        ping = interaction.user.mention
        if SUPPORT_ROLE_ID:
            ping += f" • <@&{SUPPORT_ROLE_ID}>"

        await channel.send(content=ping, embed=embed, view=TicketCloseView())
        await interaction.followup.send(
            f"Your ticket has been created: {channel.mention}", ephemeral=True
        )


class TicketCloseView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="Close Ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="orb_ticket_close",
    )
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        member = interaction.user
        is_admin = member.guild_permissions.administrator
        is_support = SUPPORT_ROLE_ID and any(r.id == SUPPORT_ROLE_ID for r in member.roles)
        is_opener = interaction.channel.topic == ticket_topic(member.id)

        if not (is_admin or is_support or is_opener):
            await interaction.response.send_message(
                "You do not have permission to close this ticket.", ephemeral=True
            )
            return

        await interaction.response.send_message("Closing this ticket in 5 seconds...")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception as exc:  # noqa: BLE001
            print(f"Failed to delete ticket channel: {exc}")


class TicketPanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="Create Ticket",
        emoji="🎫",
        style=discord.ButtonStyle.primary,
        custom_id="orb_ticket_create",
    )
    async def create_ticket(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(TicketReasonModal())


@bot.tree.command(name="say", description="Make the bot say something (Admin only)")
@app_commands.describe(
    message="What the bot should say",
    channel="Channel to send in (defaults to current channel)",
)
@app_commands.default_permissions(administrator=True)
async def say(
    interaction: discord.Interaction,
    message: str,
    channel: discord.TextChannel = None,
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "You need Administrator permission to use this command.", ephemeral=True
        )
        return

    target = channel or interaction.channel
    try:
        await target.send(message)
        await interaction.response.send_message(
            f"Message sent in {target.mention}.", ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to send messages there.", ephemeral=True
        )


@bot.tree.command(
    name="ticket-panel", description="Send the support ticket creation panel (Admin only)"
)
@app_commands.describe(
    channel="Channel to send the panel in (defaults to current channel)",
    title="Panel title (optional)",
    description="Panel description (optional)",
)
@app_commands.default_permissions(administrator=True)
async def ticket_panel(
    interaction: discord.Interaction,
    channel: discord.TextChannel = None,
    title: str = None,
    description: str = None,
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "You need Administrator permission to use this command.", ephemeral=True
        )
        return

    target = channel or interaction.channel
    embed = discord.Embed(
        title=title or "Orb SMP Support",
        description=description
        or (
            "Need help? Click the button below to open a support ticket.\n"
            "You will be asked one quick question before your ticket is created."
        ),
        color=0x2B2D31,
    )
    embed.set_footer(text="Orb SMP Support")

    try:
        await target.send(embed=embed, view=TicketPanelView())
        await interaction.response.send_message(
            f"Ticket panel sent in {target.mention}.", ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to send messages there.", ephemeral=True
        )


# ══════════════════════════════════════════════════════════════════════════
# Announcement system — composed privately over DM so nothing leaks into the
# server (no visible command args, no draft messages) until it's posted.
# ══════════════════════════════════════════════════════════════════════════
class AnnouncementModal(ui.Modal, title="Compose Announcement"):
    ann_title = ui.TextInput(
        label="Title",
        style=discord.TextStyle.short,
        max_length=256,
        required=True,
    )
    ann_body = ui.TextInput(
        label="Message",
        style=discord.TextStyle.paragraph,
        max_length=4000,
        required=True,
    )

    def __init__(self, target_channel: discord.TextChannel):
        super().__init__()
        self.target_channel = target_channel

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Got it. Now reply here with any images/files to attach "
            "(Discord's normal upload limit applies — no Nitro needed), "
            "or type `skip` to post without attachments. You have 5 minutes.",
        )

        dm_channel = interaction.channel

        def check(msg: discord.Message) -> bool:
            return msg.author.id == interaction.user.id and msg.channel.id == dm_channel.id

        try:
            reply = await bot.wait_for("message", check=check, timeout=300)
        except asyncio.TimeoutError:
            await dm_channel.send("Timed out waiting for attachments. Run `/announcement` again.")
            return

        files = []
        if reply.content.strip().lower() != "skip":
            for attachment in reply.attachments:
                files.append(await attachment.to_file())

        embed = discord.Embed(
            title=self.ann_title.value,
            description=self.ann_body.value,
            color=0x2B2D31,
        )
        embed.set_footer(text="Orb SMP Announcement")
        embed.timestamp = discord.utils.utcnow()

        # First image attachment (if any) becomes the embed's big image.
        image_file = next((f for f in files if _looks_like_image(f.filename)), None)
        if image_file:
            embed.set_image(url=f"attachment://{image_file.filename}")

        try:
            await self.target_channel.send(embed=embed, files=files if files else None)
            await dm_channel.send(f"Announcement posted in {self.target_channel.mention}.")
        except discord.Forbidden:
            await dm_channel.send(
                "I don't have permission to post in that channel. Nothing was sent."
            )
        except discord.HTTPException as exc:
            await dm_channel.send(f"Discord rejected the post ({exc}). Nothing was sent.")


def _looks_like_image(filename: str) -> bool:
    return filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))


class AnnouncementStartView(ui.View):
    def __init__(self, target_channel: discord.TextChannel):
        super().__init__(timeout=600)
        self.target_channel = target_channel

    @ui.button(label="Compose Announcement", emoji="📢", style=discord.ButtonStyle.primary)
    async def start(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(AnnouncementModal(self.target_channel))


@bot.tree.command(
    name="announcement",
    description="Compose an announcement privately over DM, then post it (Admin only)",
)
@app_commands.describe(channel="Channel to post the announcement in")
@app_commands.default_permissions(administrator=True)
async def announcement(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "You need Administrator permission to use this command.", ephemeral=True
        )
        return

    target = channel or interaction.channel

    try:
        dm = await interaction.user.create_dm()
        await dm.send(
            f"Let's put together an announcement for {target.mention}. Click below to start — "
            "nothing you type here will be visible in the server until it's posted.",
            view=AnnouncementStartView(target),
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            "I couldn't DM you. Enable DMs from server members and try again.", ephemeral=True
        )
        return

    await interaction.response.send_message("Check your DMs to compose the announcement.", ephemeral=True)


# ══════════════════════════════════════════════════════════════════════════
# Moderation
# ══════════════════════════════════════════════════════════════════════════
@bot.tree.command(name="warn", description="Warn a member")
@app_commands.describe(member="Member to warn", reason="Reason for the warning")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.default_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    guild_warns = warnings.setdefault(interaction.guild.id, {})
    guild_warns[member.id] = guild_warns.get(member.id, 0) + 1
    count = guild_warns[member.id]

    try:
        await member.send(
            f"You were warned in **{interaction.guild.name}**.\nReason: {reason}\n"
            f"This is warning #{count} for you."
        )
    except discord.Forbidden:
        pass

    await log_mod_action(interaction.guild, f"Warn (#{count})", member, interaction.user, reason)
    await interaction.response.send_message(
        f"{member.mention} has been warned. They now have **{count}** warning(s).", ephemeral=True
    )


@bot.tree.command(name="kick", description="Kick a member")
@app_commands.describe(member="Member to kick", reason="Reason for the kick")
@app_commands.checks.has_permissions(kick_members=True)
@app_commands.default_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    try:
        await member.send(f"You were kicked from **{interaction.guild.name}**.\nReason: {reason}")
    except discord.Forbidden:
        pass

    try:
        await member.kick(reason=reason)
    except discord.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to kick that member (check role hierarchy).", ephemeral=True
        )
        return

    await log_mod_action(interaction.guild, "Kick", member, interaction.user, reason)
    await interaction.response.send_message(f"{member.mention} has been kicked.", ephemeral=True)


@bot.tree.command(name="ban", description="Ban a member")
@app_commands.describe(
    member="Member to ban",
    reason="Reason for the ban",
    delete_hours="Delete this member's messages from the last N hours (0-168, default 0)",
)
@app_commands.checks.has_permissions(ban_members=True)
@app_commands.default_permissions(ban_members=True)
async def ban(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided",
    delete_hours: app_commands.Range[int, 0, 168] = 0,
):
    try:
        await member.send(f"You were banned from **{interaction.guild.name}**.\nReason: {reason}")
    except discord.Forbidden:
        pass

    try:
        await member.ban(reason=reason, delete_message_seconds=delete_hours * 3600)
    except discord.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to ban that member (check role hierarchy).", ephemeral=True
        )
        return

    await log_mod_action(interaction.guild, "Ban", member, interaction.user, reason)
    await interaction.response.send_message(f"{member.mention} has been banned.", ephemeral=True)


@bot.tree.command(name="timeout", description="Temporarily mute a member")
@app_commands.describe(
    member="Member to timeout",
    minutes="Duration in minutes (max 40320 = 28 days)",
    reason="Reason for the timeout",
)
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.default_permissions(moderate_members=True)
async def timeout(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: app_commands.Range[int, 1, 40320],
    reason: str = "No reason provided",
):
    try:
        await member.timeout(timedelta(minutes=minutes), reason=reason)
    except discord.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to timeout that member (check role hierarchy).",
            ephemeral=True,
        )
        return

    await log_mod_action(interaction.guild, f"Timeout ({minutes}m)", member, interaction.user, reason)
    await interaction.response.send_message(
        f"{member.mention} has been timed out for {minutes} minute(s).", ephemeral=True
    )


@bot.tree.command(name="untimeout", description="Remove a member's timeout")
@app_commands.describe(member="Member to remove timeout from")
@app_commands.checks.has_permissions(moderate_members=True)
@app_commands.default_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, member: discord.Member):
    try:
        await member.timeout(None)
    except discord.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to modify that member's timeout.", ephemeral=True
        )
        return

    await log_mod_action(interaction.guild, "Timeout removed", member, interaction.user, None)
    await interaction.response.send_message(f"{member.mention}'s timeout has been removed.", ephemeral=True)


@bot.tree.command(name="clear", description="Bulk delete recent messages in this channel")
@app_commands.describe(amount="Number of messages to delete (1-100)")
@app_commands.checks.has_permissions(manage_messages=True)
@app_commands.default_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"Deleted {len(deleted)} message(s).", ephemeral=True)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "You don't have permission to use this command."
    else:
        msg = f"Something went wrong: {error}"
        print(f"Command error: {error}")

    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


# ── Startup ───────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    bot.add_view(TicketPanelView())
    bot.add_view(TicketCloseView())

    if GUILD_ID:
        guild_obj = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild_obj)
        await bot.tree.sync(guild=guild_obj)
    else:
        await bot.tree.sync()

    print(f"Logged in as {bot.user} (commands synced)")


def main():
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN is not set. Add it to your environment variables.")

    threading.Thread(target=run_web_server, daemon=True).start()
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
