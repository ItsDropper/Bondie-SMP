const fs = require('fs');
const path = require('path');
const { Client, GatewayIntentBits, Collection, MessageFlags } = require('discord.js');
const config = require('./config');
const {
  TICKET_CREATE_BUTTON_ID,
  TICKET_MODAL_ID,
  TICKET_CLOSE_BUTTON_ID,
  handleTicketButton,
  handleTicketModalSubmit,
  handleCloseButton,
} = require('./utils/tickets');

const client = new Client({
  intents: [GatewayIntentBits.Guilds],
});

client.commands = new Collection();

const commandsPath = path.join(__dirname, 'commands');
for (const file of fs.readdirSync(commandsPath).filter(f => f.endsWith('.js'))) {
  const command = require(path.join(commandsPath, file));
  client.commands.set(command.data.name, command);
}

client.once('ready', () => {
  console.log(`Logged in as ${client.user.tag}`);
});

client.on('interactionCreate', async interaction => {
  try {
    if (interaction.isChatInputCommand()) {
      const command = client.commands.get(interaction.commandName);
      if (!command) return;
      await command.execute(interaction);
      return;
    }

    if (interaction.isButton()) {
      if (interaction.customId === TICKET_CREATE_BUTTON_ID) {
        return handleTicketButton(interaction);
      }
      if (interaction.customId === TICKET_CLOSE_BUTTON_ID) {
        return handleCloseButton(interaction);
      }
      return;
    }

    if (interaction.isModalSubmit()) {
      if (interaction.customId === TICKET_MODAL_ID) {
        return handleTicketModalSubmit(interaction);
      }
      return;
    }
  } catch (err) {
    console.error('Error handling interaction:', err);
    const errorPayload = {
      content: 'Something went wrong while handling that. Please try again.',
      flags: MessageFlags.Ephemeral,
    };
    if (interaction.deferred || interaction.replied) {
      await interaction.editReply(errorPayload).catch(() => {});
    } else {
      await interaction.reply(errorPayload).catch(() => {});
    }
  }
});

client.login(config.token);
