const { SlashCommandBuilder, PermissionFlagsBits, MessageFlags } = require('discord.js');

module.exports = {
  data: new SlashCommandBuilder()
    .setName('say')
    .setDescription('Make the bot say something (Admin only)')
    .addStringOption(option =>
      option
        .setName('message')
        .setDescription('What the bot should say')
        .setRequired(true)
        .setMaxLength(2000)
    )
    .addChannelOption(option =>
      option
        .setName('channel')
        .setDescription('Channel to send the message in (defaults to current channel)')
        .setRequired(false)
    )
    .setDefaultMemberPermissions(PermissionFlagsBits.Administrator)
    .setDMPermission(false),

  async execute(interaction) {
    // Extra safety check on top of setDefaultMemberPermissions (which server admins
    // could technically override in Integrations settings).
    if (!interaction.memberPermissions?.has(PermissionFlagsBits.Administrator)) {
      return interaction.reply({
        content: 'You need Administrator permission to use this command.',
        flags: MessageFlags.Ephemeral,
      });
    }

    const message = interaction.options.getString('message', true);
    const targetChannel = interaction.options.getChannel('channel') || interaction.channel;

    if (!targetChannel?.isTextBased()) {
      return interaction.reply({
        content: 'That channel is not a text channel I can send messages in.',
        flags: MessageFlags.Ephemeral,
      });
    }

    try {
      await targetChannel.send({ content: message });
      await interaction.reply({
        content: `Message sent in ${targetChannel}.`,
        flags: MessageFlags.Ephemeral,
      });
    } catch (err) {
      console.error('Failed to send /say message:', err);
      await interaction.reply({
        content: 'I could not send that message. Do I have permission to post in that channel?',
        flags: MessageFlags.Ephemeral,
      });
    }
  },
};
