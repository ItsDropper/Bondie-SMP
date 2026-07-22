"""
Orb SMP Discord Bot
--------------------
- /say <message> [channel]        Admin only. Makes the bot post a message.
- /ticket-panel [channel] [...]   Admin only. Sends a panel with a "Create Ticket"
                                   button. Clicking it asks one question,
                                   "Why are you creating this ticket?", then opens
                                   a private ticket channel under TICKET_CATEGORY_ID.

Runs a tiny Flask server alongside the bot so it can be deployed as a Render
"Web Service" (which requires something bound to a port) instead of a paid
Background Worker.
"""

import os
import asyncio
import threading

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

PORT = int(os.getenv("PORT", "8080"))

# ── Tiny web server (keeps Render's Web Service port check happy) ───────────
web_app = Flask(__name__)


@web_app.route("/")
def home():
    return "Orb SMP bot is running."


def run_web_server():
    web_app.run(host="0.0.0.0", port=PORT)


# ── Discord bot setup ─────────────────────────────────────────────────────────
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def ticket_topic(user_id: int) -> str:
    return f"orb-ticket:{user_id}"


# ── Ticket UI: reason modal, panel button, close button ─────────────────────
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

        # Prevent duplicate open tickets from the same user.
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


# ── Slash commands ────────────────────────────────────────────────────────────
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


# ── Startup ───────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    # Re-register persistent views so buttons keep working after a restart.
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

    # Run the web server in the background so Render sees an open port,
    # while the bot itself runs on the main thread.
    threading.Thread(target=run_web_server, daemon=True).start()
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
