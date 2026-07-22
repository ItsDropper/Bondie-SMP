const {
  ModalBuilder,
  TextInputBuilder,
  TextInputStyle,
  ActionRowBuilder,
  EmbedBuilder,
  ButtonBuilder,
  ButtonStyle,
  ChannelType,
  PermissionFlagsBits,
  MessageFlags,
} = require('discord.js');
const config = require('../config');

const TICKET_MODAL_ID = 'orb_ticket_modal';
const TICKET_REASON_ID = 'orb_ticket_reason';
const TICKET_CREATE_BUTTON_ID = 'orb_ticket_create';
const TICKET_CLOSE_BUTTON_ID = 'orb_ticket_close';

// Handles a click on the "Create Ticket" button — opens the reason modal.
async function handleTicketButton(interaction) {
  const modal = new ModalBuilder()
    .setCustomId(TICKET_MODAL_ID)
    .setTitle('Create a Support Ticket');

  const reasonInput = new TextInputBuilder()
    .setCustomId(TICKET_REASON_ID)
    .setLabel('Why are you creating this ticket?')
    .setStyle(TextInputStyle.Paragraph)
    .setPlaceholder('Describe your issue or question...')
    .setRequired(true)
    .setMaxLength(1000);

  modal.addComponents(new ActionRowBuilder().addComponents(reasonInput));

  await interaction.showModal(modal);
}

// Handles submission of the reason modal — creates the ticket channel.
async function handleTicketModalSubmit(interaction) {
  const reason = interaction.fields.getTextInputValue(TICKET_REASON_ID);
  const guild = interaction.guild;

  await interaction.deferReply({ flags: MessageFlags.Ephemeral });

  // Prevent duplicate open tickets from the same user.
  const existing = guild.channels.cache.find(
    c => c.type === ChannelType.GuildText && c.topic === `orb-ticket:${interaction.user.id}`
  );
  if (existing) {
    return interaction.editReply({
      content: `You already have an open ticket: ${existing}`,
    });
  }

  const category = await guild.channels
    .fetch(config.ticketCategoryId)
    .catch(() => null);

  const permissionOverwrites = [
    {
      id: guild.roles.everyone.id,
      deny: [PermissionFlagsBits.ViewChannel],
    },
    {
      id: interaction.user.id,
      allow: [
        PermissionFlagsBits.ViewChannel,
        PermissionFlagsBits.SendMessages,
        PermissionFlagsBits.ReadMessageHistory,
        PermissionFlagsBits.AttachFiles,
      ],
    },
    {
      id: interaction.client.user.id,
      allow: [
        PermissionFlagsBits.ViewChannel,
        PermissionFlagsBits.SendMessages,
        PermissionFlagsBits.ManageChannels,
      ],
    },
  ];

  if (config.supportRoleId) {
    permissionOverwrites.push({
      id: config.supportRoleId,
      allow: [
        PermissionFlagsBits.ViewChannel,
        PermissionFlagsBits.SendMessages,
        PermissionFlagsBits.ReadMessageHistory,
      ],
    });
  }

  let ticketChannel;
  try {
    ticketChannel = await guild.channels.create({
      name: `ticket-${interaction.user.username}`.toLowerCase().slice(0, 90),
      type: ChannelType.GuildText,
      parent: category && category.type === ChannelType.GuildCategory ? category.id : undefined,
      topic: `orb-ticket:${interaction.user.id}`,
      permissionOverwrites,
    });
  } catch (err) {
    console.error('Failed to create ticket channel:', err);
    return interaction.editReply({
      content:
        'I could not create your ticket channel. Please make sure I have the Manage Channels permission and a valid ticket category is set.',
    });
  }

  const embed = new EmbedBuilder()
    .setTitle('New Support Ticket')
    .setColor(0x2b2d31)
    .addFields(
      { name: 'Opened by', value: `${interaction.user}`, inline: true },
      { name: 'Reason', value: reason.slice(0, 1024) }
    )
    .setTimestamp();

  const closeRow = new ActionRowBuilder().addComponents(
    new ButtonBuilder()
      .setCustomId(TICKET_CLOSE_BUTTON_ID)
      .setLabel('Close Ticket')
      .setEmoji('🔒')
      .setStyle(ButtonStyle.Danger)
  );

  const pingContent = config.supportRoleId
    ? `${interaction.user} • <@&${config.supportRoleId}>`
    : `${interaction.user}`;

  await ticketChannel.send({
    content: pingContent,
    embeds: [embed],
    components: [closeRow],
  });

  await interaction.editReply({
    content: `Your ticket has been created: ${ticketChannel}`,
  });
}

// Handles a click on the "Close Ticket" button.
async function handleCloseButton(interaction) {
  const isAdmin = interaction.memberPermissions?.has(PermissionFlagsBits.Administrator);
  const isSupport = config.supportRoleId && interaction.member.roles.cache.has(config.supportRoleId);
  const isOpener = interaction.channel.topic === `orb-ticket:${interaction.user.id}`;

  if (!isAdmin && !isSupport && !isOpener) {
    return interaction.reply({
      content: 'You do not have permission to close this ticket.',
      flags: MessageFlags.Ephemeral,
    });
  }

  await interaction.reply({ content: 'Closing this ticket in 5 seconds...' });
  setTimeout(() => {
    interaction.channel.delete().catch(err => console.error('Failed to delete ticket channel:', err));
  }, 5000);
}

module.exports = {
  TICKET_MODAL_ID,
  TICKET_CREATE_BUTTON_ID,
  TICKET_CLOSE_BUTTON_ID,
  handleTicketButton,
  handleTicketModalSubmit,
  handleCloseButton,
};
