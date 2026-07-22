const {
  SlashCommandBuilder,
  PermissionFlagsBits,
  MessageFlags,
  EmbedBuilder,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
} = require('discord.js');

module.exports = {
  data: new SlashCommandBuilder()
    .setName('ticket-panel')
    .setDescription('Send the support ticket creation panel (Admin only)')
    .addChannelOption(option =>
      option
        .setName('channel')
        .setDescription('Channel to send the panel in (defaults to current channel)')
        .setRequired(false)
    )
    .addStringOption(option =>
      option
        .setName('title')
        .setDescription('Panel title (optional)')
        .setRequired(false)
    )
    .addStringOption(option =>
      option
        .setName('description')
        .setDescription('Panel description (optional)')
        .setRequired(false)
    )
    .setDefaultMemberPermissions(PermissionFlagsBits.Administrator)
    .setDMPermission(false),

  async execute(interaction) {
    if (!interaction.memberPermissions?.has(PermissionFlagsBits.Administrator)) {
      return interaction.reply({
        content: 'You need Administrator permission to use this command.',
        flags: MessageFlags.Ephemeral,
      });
    }

    const targetChannel = interaction.options.getChannel('channel') || interaction.channel;
    const title = interaction.options.getString('title') || 'Orb SMP Support';
    const description =
      interaction.options.getString('description') ||
      'Need help? Click the button below to open a support ticket.\nYou will be asked one quick question before your ticket is created.';

    if (!targetChannel?.isTextBased()) {
      return interaction.reply({
        content: 'That channel is not a text channel I can send messages in.',
        flags: MessageFlags.Ephemeral,
      });
    }

    const embed = new EmbedBuilder()
      .setTitle(title)
      .setDescription(description)
      .setColor(0x2b2d31)
      .setFooter({ text: 'Orb SMP Support' });

    const row = new ActionRowBuilder().addComponents(
      new ButtonBuilder()
        .setCustomId('orb_ticket_create')
        .setLabel('Create Ticket')
        .setEmoji('🎫')
        .setStyle(ButtonStyle.Primary)
    );

    try {
      await targetChannel.send({ embeds: [embed], components: [row] });
      await interaction.reply({
        content: `Ticket panel sent in ${targetChannel}.`,
        flags: MessageFlags.Ephemeral,
      });
    } catch (err) {
      console.error('Failed to send ticket panel:', err);
      await interaction.reply({
        content: 'I could not send the panel there. Do I have permission to post in that channel?',
        flags: MessageFlags.Ephemeral,
      });
    }
  },
};
