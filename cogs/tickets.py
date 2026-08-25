import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import io
import re
import chat_exporter
from datetime import datetime, timezone

DATA_FILE = "tickets.json"
MAX_CATEGORIES = 5

COLOR_SUCCESS = 0x57F287
COLOR_ERROR = 0xED4245
COLOR_INFO = 0x5865F2
COLOR_WARN = 0xFEE75C


def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_guild(data: dict, guild_id: str) -> dict:
    return data.setdefault(guild_id, {
        "transcript_channel": None,
        "support_roles": [],
        "panel_message": "📩 Open a ticket by selecting a category below.",
        "categories": {},
        "tickets": {}
    })


def simple_view(text: str, color: int = COLOR_INFO) -> discord.ui.LayoutView:
    class _V(discord.ui.LayoutView):
        container = discord.ui.Container(
            discord.ui.TextDisplay(text),
            accent_color=color
        )
    return _V()


async def generate_and_send_transcript(
    bot: commands.Bot,
    channel: discord.TextChannel,
    transcript_channel: discord.TextChannel,
    ticket_data: dict,
    closed_by: discord.Member
):
    transcript = await chat_exporter.export(channel, bot=bot, military_time=True)
    if not transcript:
        return

    file = discord.File(
        io.BytesIO(transcript.encode()),
        filename=f"transcript-{channel.name}.html"
    )

    participants = ticket_data.get("participants", {})
    participant_lines = []
    for uid, count in participants.items():
        try:
            member = transcript_channel.guild.get_member(int(uid))
            name = member.mention if member else f"`{uid}`"
        except Exception:
            name = f"`{uid}`"
        participant_lines.append(f"{name} — {count} message(s)")

    participants_text = "\n".join(participant_lines) if participant_lines else "None"

    opened_at = ticket_data.get("opened_at", "Unknown")
    opener_id = ticket_data.get("opener_id")
    opener = transcript_channel.guild.get_member(int(opener_id)) if opener_id else None
    opener_mention = opener.mention if opener else f"`{opener_id}`"

    info_text = (
        f"## 📄 Transcript — {channel.name}\n"
        f"**Category:** {ticket_data.get('category', 'Unknown')}\n"
        f"**Opened by:** {opener_mention}\n"
        f"**Closed/Deleted by:** {closed_by.mention}\n"
        f"**Opened at:** {opened_at}\n\n"
        f"**Participants:**\n{participants_text}"
    )

    class TranscriptView(discord.ui.LayoutView):
        container = discord.ui.Container(
            discord.ui.TextDisplay(info_text),
            accent_color=COLOR_INFO
        )

    await transcript_channel.send(view=TranscriptView(), file=file)


class PanelButtonView(discord.ui.LayoutView):
    def __init__(self, categories: dict, guild_id: str, panel_msg: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id

        btn_row = discord.ui.ActionRow()
        for cat_id, cat in list(categories.items())[:5]:
            btn = discord.ui.Button(
                label=cat["name"],
                style=discord.ButtonStyle.primary,
                custom_id=f"ticket_open:{guild_id}:{cat_id}"
            )
            btn.callback = self._make_callback(cat_id)
            btn_row.add_item(btn)

        container = discord.ui.Container(
            discord.ui.TextDisplay(panel_msg),
            discord.ui.Separator(visible=True),
            btn_row,
            accent_color=COLOR_INFO
        )
        self.add_item(container)

    def _make_callback(self, cat_id: str):
        async def callback(interaction: discord.Interaction):
            await open_ticket(interaction, cat_id)
        return callback


class PanelSelectView(discord.ui.LayoutView):
    def __init__(self, categories: dict, guild_id: str, panel_msg: str):
        super().__init__(timeout=None)
        self.guild_id = guild_id

        options = [
            discord.SelectOption(label=cat["name"], value=cat_id)
            for cat_id, cat in list(categories.items())[:5]
        ]

        select = discord.ui.Select(
            placeholder="Choose a category...",
            options=options,
            custom_id=f"ticket_select:{guild_id}"
        )
        select.callback = self.on_select

        select_row = discord.ui.ActionRow()
        select_row.add_item(select)

        container = discord.ui.Container(
            discord.ui.TextDisplay(panel_msg),
            discord.ui.Separator(visible=True),
            select_row,
            accent_color=COLOR_INFO
        )
        self.add_item(container)

    async def on_select(self, interaction: discord.Interaction):
        cat_id = interaction.data["values"][0]
        await open_ticket(interaction, cat_id)


async def open_ticket(interaction: discord.Interaction, cat_id: str):
    await interaction.response.defer(ephemeral=True)

    data = load_data()
    gd = get_guild(data, str(interaction.guild_id))
    cat = gd["categories"].get(cat_id)

    if not cat:
        await interaction.followup.send(
            view=simple_view("❌ That category no longer exists.", COLOR_ERROR),
            ephemeral=True
        )
        return

    for ticket in gd["tickets"].values():
        if (
            ticket.get("opener_id") == str(interaction.user.id)
            and ticket.get("cat_id") == cat_id
            and ticket.get("status") != "deleted"
        ):
            await interaction.followup.send(
                view=simple_view(f"⚠️ You already have an open **{cat['name']}** ticket.", COLOR_WARN),
                ephemeral=True
            )
            return

    guild = interaction.guild
    channel_cat = guild.get_channel(int(cat["channel_category"])) if cat.get("channel_category") else None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    }
    for role_id in gd["support_roles"]:
        role = guild.get_role(int(role_id))
        if role:
            overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)

    ticket_channel = await guild.create_text_channel(
        name=f"ticket-{interaction.user.name}",
        category=channel_cat,
        overwrites=overwrites,
        topic=f"Ticket by {interaction.user} ({interaction.user.id}) | Category: {cat['name']}"
    )

    ticket_id = str(ticket_channel.id)
    gd["tickets"][ticket_id] = {
        "channel_id": ticket_id,
        "cat_id": cat_id,
        "category": cat["name"],
        "opener_id": str(interaction.user.id),
        "opener_name": str(interaction.user),
        "opened_at": f"<t:{int(datetime.now(timezone.utc).timestamp())}:F>",
        "status": "open",
        "participants": {}
    }
    save_data(data)

    await interaction.followup.send(
        view=simple_view(f"✅ Your ticket has been created: {ticket_channel.mention}", COLOR_SUCCESS),
        ephemeral=True
    )

    await send_welcome_message(ticket_channel, cat, interaction.user, gd["support_roles"])


async def send_welcome_message(
    channel: discord.TextChannel,
    cat: dict,
    opener: discord.Member,
    support_role_ids: list
):
    welcome_text = cat.get("welcome_message", "Welcome! Support will be with you shortly.")
    welcome_text = welcome_text.replace("{user}", opener.mention).replace("{category}", cat["name"])

    role_pings = " ".join(f"<@&{r}>" for r in support_role_ids) if support_role_ids else ""
    bottom_text = role_pings if role_pings else None

    class WelcomeView(discord.ui.LayoutView):
        def __init__(self_inner):
            super().__init__(timeout=None)

            close_btn = discord.ui.Button(
                label="Close Ticket",
                style=discord.ButtonStyle.danger,
                custom_id=f"ticket_close:{channel.id}"
            )
            close_btn.callback = self_inner.close_callback

            btn_row = discord.ui.ActionRow()
            btn_row.add_item(close_btn)

            inner_items = [discord.ui.TextDisplay(welcome_text)]
            if bottom_text:
                inner_items.append(discord.ui.Separator(visible=False))
                inner_items.append(discord.ui.TextDisplay(bottom_text))
            inner_items.append(discord.ui.Separator(visible=True))
            inner_items.append(btn_row)

            container = discord.ui.Container(
                *inner_items,
                accent_color=COLOR_INFO
            )
            self_inner.add_item(container)

        async def close_callback(self_inner, interaction: discord.Interaction):
            await close_ticket(interaction, channel)

    await channel.send(view=WelcomeView())


async def close_ticket(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_data()
    gd = get_guild(data, str(interaction.guild_id))
    ticket = gd["tickets"].get(str(channel.id))

    if not ticket:
        await interaction.response.send_message(
            view=simple_view("❌ Ticket data not found.", COLOR_ERROR),
            ephemeral=True
        )
        return

    member = interaction.guild.get_member(interaction.user.id)
    is_support = any(int(r) in [role.id for role in member.roles] for r in gd["support_roles"])
    is_opener = str(interaction.user.id) == ticket.get("opener_id")

    if not member.guild_permissions.administrator and not is_support and not is_opener:
        await interaction.response.send_message(
            view=simple_view("❌ You don't have permission to close this ticket.", COLOR_ERROR),
            ephemeral=True
        )
        return

    await interaction.response.defer()

    opener = interaction.guild.get_member(int(ticket["opener_id"]))
    if opener:
        try:
            await channel.set_permissions(opener, overwrite=None)
        except Exception:
            pass

    ticket["status"] = "closed"
    save_data(data)

    class ClosedView(discord.ui.LayoutView):
        def __init__(self_inner):
            super().__init__(timeout=None)

            reopen_btn = discord.ui.Button(
                label="Reopen",
                style=discord.ButtonStyle.success,
                custom_id=f"ticket_reopen:{channel.id}"
            )
            reopen_btn.callback = self_inner.reopen_callback

            delete_btn = discord.ui.Button(
                label="Delete",
                style=discord.ButtonStyle.danger,
                custom_id=f"ticket_delete:{channel.id}"
            )
            delete_btn.callback = self_inner.delete_callback

            btn_row = discord.ui.ActionRow()
            btn_row.add_item(reopen_btn)
            btn_row.add_item(delete_btn)

            container = discord.ui.Container(
                discord.ui.TextDisplay(
                    f"🔒 Ticket closed by {interaction.user.mention}.\n"
                    f"Use the buttons below to reopen or permanently delete this ticket."
                ),
                discord.ui.Separator(visible=True),
                btn_row,
                accent_color=COLOR_WARN
            )
            self_inner.add_item(container)

        async def reopen_callback(self_inner, interaction2: discord.Interaction):
            await reopen_ticket(interaction2, channel)

        async def delete_callback(self_inner, interaction2: discord.Interaction):
            await delete_ticket(interaction2, channel)

    await interaction.followup.send(view=ClosedView())


async def reopen_ticket(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_data()
    gd = get_guild(data, str(interaction.guild_id))
    ticket = gd["tickets"].get(str(channel.id))

    member = interaction.guild.get_member(interaction.user.id)
    is_support = any(int(r) in [role.id for role in member.roles] for r in gd["support_roles"])

    if not member.guild_permissions.administrator and not is_support:
        await interaction.response.send_message(
            view=simple_view("❌ Only support staff can reopen tickets.", COLOR_ERROR),
            ephemeral=True
        )
        return

    opener = interaction.guild.get_member(int(ticket["opener_id"]))
    if opener:
        try:
            await channel.set_permissions(opener, view_channel=True, send_messages=True, read_message_history=True)
        except Exception:
            pass

    ticket["status"] = "open"
    save_data(data)

    await interaction.response.edit_message(
        view=simple_view(f"🔓 Ticket reopened by {interaction.user.mention}.", COLOR_SUCCESS)
    )


async def delete_ticket(interaction: discord.Interaction, channel: discord.TextChannel):
    data = load_data()
    gd = get_guild(data, str(interaction.guild_id))
    ticket = gd["tickets"].get(str(channel.id))

    member = interaction.guild.get_member(interaction.user.id)
    is_support = any(int(r) in [role.id for role in member.roles] for r in gd["support_roles"])

    if not member.guild_permissions.administrator and not is_support:
        await interaction.response.send_message(
            view=simple_view("❌ Only support staff can delete tickets.", COLOR_ERROR),
            ephemeral=True
        )
        return

    await interaction.response.defer()

    transcript_channel_id = gd.get("transcript_channel")
    if transcript_channel_id:
        transcript_channel = interaction.guild.get_channel(int(transcript_channel_id))
        if transcript_channel:
            try:
                transcript = await chat_exporter.export(channel, bot=interaction.client, military_time=True)
                if transcript:
                    file = discord.File(
                        io.BytesIO(transcript.encode()),
                        filename=f"transcript-{channel.name}.html"
                    )

                    participants = ticket.get("participants", {})
                    participant_lines = []
                    for uid, count in participants.items():
                        m = interaction.guild.get_member(int(uid))
                        name = m.mention if m else f"`{uid}`"
                        participant_lines.append(f"{name} — {count} message(s)")

                    participants_text = "\n".join(participant_lines) if participant_lines else "None"
                    opener_id = ticket.get("opener_id")
                    opener = interaction.guild.get_member(int(opener_id)) if opener_id else None
                    opener_mention = opener.mention if opener else f"`{opener_id}`"

                    embed = discord.Embed(
                        title=f"📄 Transcript — {channel.name}",
                        color=discord.Color.blurple(),
                        timestamp=datetime.now(timezone.utc)
                    )
                    embed.add_field(name="Category", value=ticket.get('category', 'Unknown'), inline=True)
                    embed.add_field(name="Opened by", value=opener_mention, inline=True)
                    embed.add_field(name="Closed/Deleted by", value=interaction.user.mention, inline=True)
                    embed.add_field(name="Opened at", value=ticket.get('opened_at', 'Unknown'), inline=False)
                    embed.add_field(name="Participants", value=participants_text, inline=False)

                    await transcript_channel.send(embed=embed, file=file)
            except Exception as e:
                await transcript_channel.send(
                    view=simple_view(f"⚠️ Transcript generation failed: `{e}`", COLOR_WARN)
                )

    ticket["status"] = "deleted"
    save_data(data)

    await channel.delete(reason=f"Ticket deleted by {interaction.user}")


class SetupDashboard(discord.ui.LayoutView):
    def __init__(self, guild_id: str):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self._build()

    def _build(self):
        self.clear_items()
        data = load_data()
        gd = get_guild(data, self.guild_id)

        transcript_id = gd.get("transcript_channel")
        transcript_text = f"<#{transcript_id}>" if transcript_id else "Not set"
        roles_text = ", ".join(f"<@&{r}>" for r in gd["support_roles"]) if gd["support_roles"] else "None"
        categories_text = "\n".join(f"• {c['name']}" for c in gd["categories"].values()) if gd["categories"] else "None"

        general_btn = discord.ui.Button(label="⚙️ General", style=discord.ButtonStyle.primary)
        general_btn.callback = self.open_general
        roles_btn = discord.ui.Button(label="👥 Support Roles", style=discord.ButtonStyle.primary)
        roles_btn.callback = self.open_roles
        categories_btn = discord.ui.Button(label="📂 Categories", style=discord.ButtonStyle.primary)
        categories_btn.callback = self.open_categories
        panel_btn = discord.ui.Button(label="📋 Panel Message", style=discord.ButtonStyle.primary)
        panel_btn.callback = self.open_panel

        row = discord.ui.ActionRow()
        row.add_item(general_btn)
        row.add_item(roles_btn)
        row.add_item(categories_btn)
        row.add_item(panel_btn)

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"## 🎫 Ticket Setup\n\n"
                f"**Transcript Channel:** {transcript_text}\n"
                f"**Support Roles:** {roles_text}\n"
                f"**Categories ({len(gd['categories'])}/{MAX_CATEGORIES}):**\n{categories_text}"
            ),
            discord.ui.Separator(visible=True),
            row,
            accent_color=COLOR_INFO
        )
        self.add_item(container)

    async def open_general(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GeneralSetupModal(self.guild_id, self))

    async def open_roles(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            view=RolesManageView(self.guild_id),
            ephemeral=True
        )

    async def open_categories(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            view=CategoriesManageView(self.guild_id),
            ephemeral=True
        )

    async def open_panel(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PanelMessageModal(self.guild_id, self))

    async def refresh(self, interaction: discord.Interaction):
        self._build()
        await interaction.response.edit_message(view=self)


class GeneralSetupModal(discord.ui.Modal, title="General Setup"):
    transcript = discord.ui.TextInput(
        label="Transcript Channel ID",
        placeholder="Paste the channel ID",
        required=False
    )

    def __init__(self, guild_id: str, parent: SetupDashboard):
        super().__init__()
        self.guild_id = guild_id
        self.parent = parent
        data = load_data()
        gd = get_guild(data, guild_id)
        self.transcript.default = gd.get("transcript_channel") or ""

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        gd = get_guild(data, self.guild_id)

        val = self.transcript.value.strip()
        if val:
            ch = interaction.guild.get_channel(int(val)) if val.isdigit() else None
            if not ch:
                await interaction.response.send_message(
                    view=simple_view("❌ Channel not found. Please provide a valid channel ID.", COLOR_ERROR),
                    ephemeral=True
                )
                return
            gd["transcript_channel"] = val
        save_data(data)
        await self.parent.refresh(interaction)


class PanelMessageModal(discord.ui.Modal, title="Panel Message"):
    message = discord.ui.TextInput(
        label="Panel Message",
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(self, guild_id: str, parent: SetupDashboard):
        super().__init__()
        self.guild_id = guild_id
        self.parent = parent
        data = load_data()
        gd = get_guild(data, guild_id)
        self.message.default = gd.get("panel_message", "")

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        gd = get_guild(data, self.guild_id)
        gd["panel_message"] = self.message.value.strip()
        save_data(data)
        await self.parent.refresh(interaction)


class RolesManageView(discord.ui.LayoutView):
    def __init__(self, guild_id: str):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self._build()

    def _build(self):
        self.clear_items()
        data = load_data()
        gd = get_guild(data, self.guild_id)
        roles_text = "\n".join(f"• <@&{r}>" for r in gd["support_roles"]) if gd["support_roles"] else "No roles set."

        add_btn = discord.ui.Button(label="Add Role", style=discord.ButtonStyle.success)
        add_btn.callback = self.add_role
        remove_btn = discord.ui.Button(label="Remove Role", style=discord.ButtonStyle.danger)
        remove_btn.callback = self.remove_role

        row = discord.ui.ActionRow()
        row.add_item(add_btn)
        row.add_item(remove_btn)

        container = discord.ui.Container(
            discord.ui.TextDisplay(f"## 👥 Support Roles\n\n{roles_text}"),
            discord.ui.Separator(visible=True),
            row,
            accent_color=COLOR_INFO
        )
        self.add_item(container)

    async def add_role(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AddRoleModal(self.guild_id, self))

    async def remove_role(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RemoveRoleModal(self.guild_id, self))

    async def refresh(self, interaction: discord.Interaction):
        self._build()
        await interaction.response.edit_message(view=self)


class AddRoleModal(discord.ui.Modal, title="Add Support Role"):
    role_input = discord.ui.TextInput(
        label="Role Mention or ID",
        placeholder="@RoleName or 123456789012345678"
    )

    def __init__(self, guild_id: str, parent: RolesManageView):
        super().__init__()
        self.guild_id = guild_id
        self.parent = parent

    async def on_submit(self, interaction: discord.Interaction):
        val = self.role_input.value.strip()
        role_id = None

        match = re.match(r"<@&(\d+)>", val)
        if match:
            role_id = match.group(1)
        elif val.isdigit():
            role_id = val

        if not role_id:
            await interaction.response.send_message(
                view=simple_view("❌ Invalid role. Use a mention like @Role or a role ID.", COLOR_ERROR),
                ephemeral=True
            )
            return

        role = interaction.guild.get_role(int(role_id))
        if not role:
            await interaction.response.send_message(
                view=simple_view("❌ Role not found in this server.", COLOR_ERROR),
                ephemeral=True
            )
            return

        data = load_data()
        gd = get_guild(data, self.guild_id)
        if role_id in gd["support_roles"]:
            await interaction.response.send_message(
                view=simple_view("⚠️ That role is already added.", COLOR_WARN),
                ephemeral=True
            )
            return

        gd["support_roles"].append(role_id)
        save_data(data)
        await self.parent.refresh(interaction)


class RemoveRoleModal(discord.ui.Modal, title="Remove Support Role"):
    role_input = discord.ui.TextInput(
        label="Role Mention or ID",
        placeholder="@RoleName or 123456789012345678"
    )

    def __init__(self, guild_id: str, parent: RolesManageView):
        super().__init__()
        self.guild_id = guild_id
        self.parent = parent

    async def on_submit(self, interaction: discord.Interaction):
        val = self.role_input.value.strip()
        role_id = None

        match = re.match(r"<@&(\d+)>", val)
        if match:
            role_id = match.group(1)
        elif val.isdigit():
            role_id = val

        if not role_id:
            await interaction.response.send_message(
                view=simple_view("❌ Invalid role.", COLOR_ERROR),
                ephemeral=True
            )
            return

        data = load_data()
        gd = get_guild(data, self.guild_id)
        if role_id not in gd["support_roles"]:
            await interaction.response.send_message(
                view=simple_view("❌ That role is not in the support roles list.", COLOR_ERROR),
                ephemeral=True
            )
            return

        gd["support_roles"].remove(role_id)
        save_data(data)
        await self.parent.refresh(interaction)


class CategoriesManageView(discord.ui.LayoutView):
    def __init__(self, guild_id: str):
        super().__init__(timeout=120)
        self.guild_id = guild_id
        self._build()

    def _build(self):
        self.clear_items()
        data = load_data()
        gd = get_guild(data, self.guild_id)
        cats = gd["categories"]

        cats_text = "\n".join(f"• **{c['name']}**" for c in cats.values()) if cats else "No categories yet."

        create_btn = discord.ui.Button(label="➕ Create", style=discord.ButtonStyle.success)
        create_btn.callback = self.create_category

        inner = [
            discord.ui.TextDisplay(f"## 📂 Categories ({len(cats)}/{MAX_CATEGORIES})\n\n{cats_text}"),
            discord.ui.Separator(visible=True),
        ]

        top_row = discord.ui.ActionRow()
        top_row.add_item(create_btn)

        if cats:
            edit_btn = discord.ui.Button(label="✏️ Edit", style=discord.ButtonStyle.primary)
            edit_btn.callback = self.edit_category
            delete_btn = discord.ui.Button(label="🗑️ Delete", style=discord.ButtonStyle.danger)
            delete_btn.callback = self.delete_category
            top_row.add_item(edit_btn)
            top_row.add_item(delete_btn)

        inner.append(top_row)
        container = discord.ui.Container(*inner, accent_color=COLOR_INFO)
        self.add_item(container)

    async def create_category(self, interaction: discord.Interaction):
        data = load_data()
        gd = get_guild(data, self.guild_id)
        if len(gd["categories"]) >= MAX_CATEGORIES:
            await interaction.response.send_message(
                view=simple_view(f"❌ Maximum of {MAX_CATEGORIES} categories reached.", COLOR_ERROR),
                ephemeral=True
            )
            return
        await interaction.response.send_modal(CreateCategoryModal(self.guild_id, self))

    async def edit_category(self, interaction: discord.Interaction):
        data = load_data()
        gd = get_guild(data, self.guild_id)
        if not gd["categories"]:
            await interaction.response.send_message(
                view=simple_view("❌ No categories to edit.", COLOR_ERROR),
                ephemeral=True
            )
            return
        await interaction.response.send_message(
            view=CategorySelectView(self.guild_id, "edit", self),
            ephemeral=True
        )

    async def delete_category(self, interaction: discord.Interaction):
        data = load_data()
        gd = get_guild(data, self.guild_id)
        if not gd["categories"]:
            await interaction.response.send_message(
                view=simple_view("❌ No categories to delete.", COLOR_ERROR),
                ephemeral=True
            )
            return
        await interaction.response.send_message(
            view=CategorySelectView(self.guild_id, "delete", self),
            ephemeral=True
        )

    async def refresh(self, interaction: discord.Interaction):
        self._build()
        await interaction.response.edit_message(view=self)


class CategorySelectView(discord.ui.LayoutView):
    def __init__(self, guild_id: str, action: str, parent: CategoriesManageView):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.action = action
        self.parent = parent

        data = load_data()
        gd = get_guild(data, guild_id)

        options = [
            discord.SelectOption(label=cat["name"], value=cat_id)
            for cat_id, cat in gd["categories"].items()
        ]

        select = discord.ui.Select(placeholder="Select a category...", options=options)
        select.callback = self.on_select

        select_row = discord.ui.ActionRow()
        select_row.add_item(select)

        label = "edit" if action == "edit" else "delete"
        container = discord.ui.Container(
            discord.ui.TextDisplay(f"Select a category to {label}:"),
            discord.ui.Separator(visible=True),
            select_row,
            accent_color=COLOR_INFO
        )
        self.add_item(container)

    async def on_select(self, interaction: discord.Interaction):
        cat_id = interaction.data["values"][0]
        if self.action == "edit":
            data = load_data()
            gd = get_guild(data, self.guild_id)
            cat = gd["categories"].get(cat_id)
            await interaction.response.send_modal(EditCategoryModal(self.guild_id, cat_id, cat, self.parent))
        else:
            await interaction.response.send_message(
                view=ConfirmDeleteCategoryView(self.guild_id, cat_id, self.parent),
                ephemeral=True
            )


class CreateCategoryModal(discord.ui.Modal, title="Create Category"):
    name = discord.ui.TextInput(label="Category Name", max_length=30)
    channel_category_id = discord.ui.TextInput(
        label="Channel Category ID",
        placeholder="Right-click a category → Copy ID",
        required=False
    )
    welcome_message = discord.ui.TextInput(
        label="Welcome Message",
        style=discord.TextStyle.paragraph,
        placeholder="Use {user} for mention, {category} for name",
        max_length=500
    )

    def __init__(self, guild_id: str, parent: CategoriesManageView):
        super().__init__()
        self.guild_id = guild_id
        self.parent = parent

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        gd = get_guild(data, self.guild_id)

        cat_channel_id = self.channel_category_id.value.strip()
        if cat_channel_id:
            ch = interaction.guild.get_channel(int(cat_channel_id)) if cat_channel_id.isdigit() else None
            if not ch or not isinstance(ch, discord.CategoryChannel):
                await interaction.response.send_message(
                    view=simple_view("❌ Invalid channel category ID.", COLOR_ERROR),
                    ephemeral=True
                )
                return

        cat_id = str(int(datetime.now(timezone.utc).timestamp()))
        gd["categories"][cat_id] = {
            "name": self.name.value.strip(),
            "channel_category": cat_channel_id or None,
            "welcome_message": self.welcome_message.value.strip()
        }
        save_data(data)
        await self.parent.refresh(interaction)


class EditCategoryModal(discord.ui.Modal, title="Edit Category"):
    name = discord.ui.TextInput(label="Category Name", max_length=30)
    channel_category_id = discord.ui.TextInput(
        label="Channel Category ID",
        required=False
    )
    welcome_message = discord.ui.TextInput(
        label="Welcome Message",
        style=discord.TextStyle.paragraph,
        max_length=500
    )

    def __init__(self, guild_id: str, cat_id: str, cat: dict, parent: CategoriesManageView):
        super().__init__()
        self.guild_id = guild_id
        self.cat_id = cat_id
        self.parent = parent
        self.name.default = cat.get("name", "")
        self.channel_category_id.default = cat.get("channel_category") or ""
        self.welcome_message.default = cat.get("welcome_message", "")

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        gd = get_guild(data, self.guild_id)

        cat_channel_id = self.channel_category_id.value.strip()
        if cat_channel_id:
            ch = interaction.guild.get_channel(int(cat_channel_id)) if cat_channel_id.isdigit() else None
            if not ch or not isinstance(ch, discord.CategoryChannel):
                await interaction.response.send_message(
                    view=simple_view("❌ Invalid channel category ID.", COLOR_ERROR),
                    ephemeral=True
                )
                return

        gd["categories"][self.cat_id] = {
            "name": self.name.value.strip(),
            "channel_category": cat_channel_id or None,
            "welcome_message": self.welcome_message.value.strip()
        }
        save_data(data)
        await self.parent.refresh(interaction)


class ConfirmDeleteCategoryView(discord.ui.LayoutView):
    def __init__(self, guild_id: str, cat_id: str, parent: CategoriesManageView):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.cat_id = cat_id
        self.parent = parent

        confirm_btn = discord.ui.Button(label="Confirm Delete", style=discord.ButtonStyle.danger)
        confirm_btn.callback = self.confirm
        cancel_btn = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        cancel_btn.callback = self.cancel

        row = discord.ui.ActionRow()
        row.add_item(confirm_btn)
        row.add_item(cancel_btn)

        container = discord.ui.Container(
            discord.ui.TextDisplay("⚠️ Are you sure you want to delete this category?"),
            discord.ui.Separator(visible=True),
            row,
            accent_color=COLOR_WARN
        )
        self.add_item(container)

    async def confirm(self, interaction: discord.Interaction):
        data = load_data()
        gd = get_guild(data, self.guild_id)
        if self.cat_id in gd["categories"]:
            del gd["categories"][self.cat_id]
            save_data(data)
        for child in self.walk_children():
            if hasattr(child, 'disabled'):
                child.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(
            view=simple_view("✅ Category deleted.", COLOR_SUCCESS),
            ephemeral=True
        )

    async def cancel(self, interaction: discord.Interaction):
        for child in self.walk_children():
            if hasattr(child, 'disabled'):
                child.disabled = True
        await interaction.response.edit_message(view=self)


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    ticket_group = app_commands.Group(name="ticket", description="Ticket system")

    def _is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator

    def _is_support(self, interaction: discord.Interaction) -> bool:
        data = load_data()
        gd = get_guild(data, str(interaction.guild_id))
        return any(int(r) in [role.id for role in interaction.user.roles] for r in gd["support_roles"])

    async def _get_ticket(self, ctx: commands.Context):
        """Fetch (ticket, guild_data) for the ticket channel this command was run in.
        Returns (None, guild_data) if the current channel isn't a tracked ticket."""
        data = load_data()
        gd = get_guild(data, str(ctx.guild.id))
        ticket = gd["tickets"].get(str(ctx.channel.id))
        return ticket, gd

    @ticket_group.command(name="setup", description="Open the ticket setup dashboard.")
    @app_commands.guild_only()
    async def setup(self, interaction: discord.Interaction):
        if not self._is_admin(interaction):
            await interaction.response.send_message(
                view=simple_view("❌ You need **Administrator** permission.", COLOR_ERROR),
                ephemeral=True
            )
            return
        await interaction.response.send_message(view=SetupDashboard(str(interaction.guild_id)))

    @ticket_group.command(name="panel", description="Send the ticket panel to a channel.")
    @app_commands.guild_only()
    @app_commands.describe(
        channel="Channel to send the panel to",
        style="Button or select menu style"
    )
    @app_commands.choices(style=[
        app_commands.Choice(name="Buttons", value="buttons"),
        app_commands.Choice(name="Select Menu", value="select")
    ])
    async def panel(self, interaction: discord.Interaction, channel: discord.TextChannel, style: app_commands.Choice[str]):
        if not self._is_admin(interaction):
            await interaction.response.send_message(
                view=simple_view("❌ You need **Administrator** permission.", COLOR_ERROR),
                ephemeral=True
            )
            return

        data = load_data()
        gd = get_guild(data, str(interaction.guild_id))

        if not gd["categories"]:
            await interaction.response.send_message(
                view=simple_view("❌ No categories set up yet. Use `/ticket setup` first.", COLOR_ERROR),
                ephemeral=True
            )
            return

        panel_msg = gd.get("panel_message", "📩 Open a ticket by selecting a category below.")

        if style.value == "buttons":
            view = PanelButtonView(gd["categories"], str(interaction.guild_id), panel_msg)
        else:
            view = PanelSelectView(gd["categories"], str(interaction.guild_id), panel_msg)

        await channel.send(view=view)
        await interaction.response.send_message(
            view=simple_view(f"✅ Panel sent to {channel.mention}.", COLOR_SUCCESS),
            ephemeral=True
        )

    @ticket_group.command(name="add", description="Add a user to the current ticket.")
    @app_commands.guild_only()
    @app_commands.describe(user="User to add")
    async def add(self, interaction: discord.Interaction, user: discord.Member):
        if not self._is_admin(interaction) and not self._is_support(interaction):
            await interaction.response.send_message(
                view=simple_view("❌ No permission.", COLOR_ERROR), ephemeral=True
            )
            return

        data = load_data()
        gd = get_guild(data, str(interaction.guild_id))
        ticket = gd["tickets"].get(str(interaction.channel_id))

        if not ticket:
            await interaction.response.send_message(
                view=simple_view("❌ This is not a ticket channel.", COLOR_ERROR), ephemeral=True
            )
            return

        await interaction.channel.set_permissions(user, view_channel=True, send_messages=True, read_message_history=True)
        await interaction.response.send_message(
            view=simple_view(f"✅ {user.mention} has been added to the ticket.", COLOR_SUCCESS)
        )

    @commands.command(name="tremove")
    @commands.guild_only()
    async def tremove(self, ctx: commands.Context, user: discord.Member):
        ticket, gd = await self._get_ticket(ctx)
        if not ticket:
            return await ctx.send(view=simple_view("❌ This is not a ticket channel.", COLOR_ERROR))
        is_support = any(int(r) in [role.id for role in ctx.author.roles] for r in gd["support_roles"])
        if not ctx.author.guild_permissions.administrator and not is_support:
            return await ctx.send(view=simple_view("❌ No permission.", COLOR_ERROR))
        if str(user.id) == ticket.get("opener_id"):
            return await ctx.send(view=simple_view("❌ Cannot remove the ticket opener.", COLOR_ERROR))
        await ctx.channel.set_permissions(user, overwrite=None)
        await ctx.send(view=simple_view(f"✅ {user.mention} removed from ticket.", COLOR_SUCCESS))

    @commands.command(name="trename")
    @commands.guild_only()
    async def trename(self, ctx: commands.Context, *, name: str):
        ticket, gd = await self._get_ticket(ctx)
        if not ticket:
            return await ctx.send(view=simple_view("❌ This is not a ticket channel.", COLOR_ERROR))
        is_support = any(int(r) in [role.id for role in ctx.author.roles] for r in gd["support_roles"])
        if not ctx.author.guild_permissions.administrator and not is_support:
            return await ctx.send(view=simple_view("❌ No permission.", COLOR_ERROR))
        await ctx.channel.edit(name=name)
        await ctx.send(view=simple_view(f"✅ Ticket renamed to **{name}**.", COLOR_SUCCESS))

    @commands.command(name="tclose")
    @commands.guild_only()
    async def tclose(self, ctx: commands.Context):
        ticket, gd = await self._get_ticket(ctx)
        if not ticket:
            return await ctx.send(view=simple_view("❌ This is not a ticket channel.", COLOR_ERROR))
        is_support = any(int(r) in [role.id for role in ctx.author.roles] for r in gd["support_roles"])
        is_opener = str(ctx.author.id) == ticket.get("opener_id")
        if not ctx.author.guild_permissions.administrator and not is_support and not is_opener:
            return await ctx.send(view=simple_view("❌ No permission.", COLOR_ERROR))

        opener = ctx.guild.get_member(int(ticket["opener_id"]))
        if opener:
            try:
                await ctx.channel.set_permissions(opener, overwrite=None)
            except Exception:
                pass

        data = load_data()
        gd2 = get_guild(data, str(ctx.guild.id))
        gd2["tickets"][str(ctx.channel.id)]["status"] = "closed"
        save_data(data)

        class ClosedView(discord.ui.LayoutView):
            def __init__(self_inner):
                super().__init__(timeout=None)
                reopen_btn = discord.ui.Button(label="Reopen", style=discord.ButtonStyle.success, custom_id=f"ticket_reopen:{ctx.channel.id}")
                reopen_btn.callback = self_inner.reopen_callback
                delete_btn = discord.ui.Button(label="Delete", style=discord.ButtonStyle.danger, custom_id=f"ticket_delete:{ctx.channel.id}")
                delete_btn.callback = self_inner.delete_callback
                row = discord.ui.ActionRow()
                row.add_item(reopen_btn)
                row.add_item(delete_btn)
                container = discord.ui.Container(
                    discord.ui.TextDisplay(f"🔒 Ticket closed by {ctx.author.mention}."),
                    discord.ui.Separator(visible=True),
                    row,
                    accent_color=COLOR_WARN
                )
                self_inner.add_item(container)

            async def reopen_callback(self_inner, interaction: discord.Interaction):
                await reopen_ticket(interaction, ctx.channel)

            async def delete_callback(self_inner, interaction: discord.Interaction):
                await delete_ticket(interaction, ctx.channel)

        await ctx.send(view=ClosedView())

    @commands.command(name="treopen")
    @commands.guild_only()
    async def treopen(self, ctx: commands.Context):
        ticket, gd = await self._get_ticket(ctx)
        if not ticket:
            return await ctx.send(view=simple_view("❌ This is not a ticket channel.", COLOR_ERROR))
        is_support = any(int(r) in [role.id for role in ctx.author.roles] for r in gd["support_roles"])
        if not ctx.author.guild_permissions.administrator and not is_support:
            return await ctx.send(view=simple_view("❌ No permission.", COLOR_ERROR))

        opener = ctx.guild.get_member(int(ticket["opener_id"]))
        if opener:
            await ctx.channel.set_permissions(opener, view_channel=True, send_messages=True, read_message_history=True)

        data = load_data()
        gd2 = get_guild(data, str(ctx.guild.id))
        gd2["tickets"][str(ctx.channel.id)]["status"] = "open"
        save_data(data)

        await ctx.send(view=simple_view(f"🔓 Ticket reopened by {ctx.author.mention}.", COLOR_SUCCESS))

    @commands.command(name="tdelete")
    @commands.guild_only()
    async def tdelete(self, ctx: commands.Context):
        ticket, gd = await self._get_ticket(ctx)
        if not ticket:
            return await ctx.send(view=simple_view("❌ This is not a ticket channel.", COLOR_ERROR))
        is_support = any(int(r) in [role.id for role in ctx.author.roles] for r in gd["support_roles"])
        if not ctx.author.guild_permissions.administrator and not is_support:
            return await ctx.send(view=simple_view("❌ No permission.", COLOR_ERROR))

        transcript_channel_id = gd.get("transcript_channel")
        if transcript_channel_id:
            transcript_channel = ctx.guild.get_channel(int(transcript_channel_id))
            if transcript_channel:
                try:
                    transcript = await chat_exporter.export(ctx.channel, bot=self.bot, military_time=True)
                    if transcript:
                        file = discord.File(
                            io.BytesIO(transcript.encode()),
                            filename=f"transcript-{ctx.channel.name}.html"
                        )
                        participants = ticket.get("participants", {})
                        participant_lines = []
                        for uid, count in participants.items():
                            m = ctx.guild.get_member(int(uid))
                            name = m.mention if m else f"`{uid}`"
                            participant_lines.append(f"{name} — {count} message(s)")
                        participants_text = "\n".join(participant_lines) if participant_lines else "None"
                        opener_id = ticket.get("opener_id")
                        opener = ctx.guild.get_member(int(opener_id)) if opener_id else None
                        opener_mention = opener.mention if opener else f"`{opener_id}`"

                        embed = discord.Embed(
                            title=f"📄 Transcript — {ctx.channel.name}",
                            color=discord.Color.blurple(),
                            timestamp=datetime.now(timezone.utc)
                        )
                        embed.add_field(name="Category", value=ticket.get('category', 'Unknown'), inline=True)
                        embed.add_field(name="Opened by", value=opener_mention, inline=True)
                        embed.add_field(name="Closed/Deleted by", value=ctx.author.mention, inline=True)
                        embed.add_field(name="Opened at", value=ticket.get('opened_at', 'Unknown'), inline=False)
                        embed.add_field(name="Participants", value=participants_text, inline=False)

                        await transcript_channel.send(embed=embed, file=file)
                except Exception as e:
                    await transcript_channel.send(
                        view=simple_view(f"⚠️ Transcript generation failed: `{e}`", COLOR_WARN)
                    )

        data = load_data()
        gd2 = get_guild(data, str(ctx.guild.id))
        gd2["tickets"][str(ctx.channel.id)]["status"] = "deleted"
        save_data(data)

        await ctx.channel.delete(reason=f"Ticket deleted by {ctx.author}")


    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        data = load_data()
        gd = get_guild(data, str(message.guild.id))
        ticket = gd["tickets"].get(str(message.channel.id))
        if not ticket or ticket.get("status") == "deleted":
            return
        uid = str(message.author.id)
        ticket["participants"][uid] = ticket["participants"].get(uid, 0) + 1
        save_data(data)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
