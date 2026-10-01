import discord
from discord.ext import commands, tasks

import db
import ranking


RANKED_CHANNEL_NAME = "ranked-1v1"
RANKED_ROLE_NAME = "|--------------Ranked--------------|"
SIGNS_CHANNEL_NAME = "signs"
RANKED_LOGS_CHANNEL_NAME = "ranked-logs"

ADMIN_ROLE_ID = 1545123755909587004

MAX_RANK_GAP = 5



def find_channel_by_suffix(guild, suffix):
    return discord.utils.find(
        lambda c: c.name.lower().endswith(suffix.lower()),
        guild.text_channels,
    )


def is_staff(member: discord.Member) -> bool:
    return (
        member.guild_permissions.moderate_members
        or member.guild_permissions.administrator
    )


def is_admin(member: discord.Member) -> bool:
    """
    Only real human members with the configured admin role
    are considered eligible for the Call Admin ping.

    Bots are explicitly excluded so bots such as Dyno,
    Ticket tools, moderation bots, etc. are never added
    to the private match thread.
    """

    if member.bot:
        return False

    return any(
        role.id == ADMIN_ROLE_ID
        for role in member.roles
    )



async def ensure_ranked_setup(member):
    guild = member.guild

    role_names = {role.name for role in member.roles}
    roles_to_add = []

    if RANKED_ROLE_NAME not in role_names:
        ranked_role = discord.utils.find(
            lambda r: r.name.endswith("Ranked--------------|"),
            guild.roles,
        )

        if ranked_role is not None:
            roles_to_add.append(ranked_role)

    if ranking.get_rank_from_member(member) is None:
        starting_role_name = ranking.RANK_NAMES[1]["Low"]

        starting_role = discord.utils.get(
            guild.roles,
            name=starting_role_name,
        )

        if starting_role is not None:
            roles_to_add.append(starting_role)

    if roles_to_add:
        try:
            await member.add_roles(
                *roles_to_add,
                reason="Auto-granted on first ranked use",
                atomic=False,
            )
        except discord.Forbidden:
            return False

    return True


def can_use_ranked(member):
    role_names = {role.name for role in member.roles}

    has_ranked = (
        RANKED_ROLE_NAME in role_names
        or any(
            role.name.endswith("Ranked--------------|")
            for role in member.roles
        )
    )

    return (
        has_ranked
        and ranking.get_rank_from_member(member) is not None
    )


async def build_queue_embed(guild):
    queued = await db.get_queued_players()
    players = []

    for player in queued:
        member = guild.get_member(player["user_id"])

        if member is None:
            continue

        rank_name = ranking.format_member_rank(member)
        players.append(
            f"{member.mention} — **{rank_name}**"
        )

    queue_text = (
        "\n".join(players)
        if players
        else "No players are currently waiting."
    )

    embed = discord.Embed(
        title="🎮 1v1 Queue",
        description=(
            f"There is currently **{len(queued)} player(s)** "
            "waiting for a 1v1."
        ),
        color=discord.Color.blurple(),
    )

    embed.add_field(
        name="Players Waiting",
        value=str(len(queued)),
        inline=False,
    )

    embed.add_field(
        name="Queue",
        value=queue_text,
        inline=False,
    )

    return embed



class QueueView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Join Queue",
        style=discord.ButtonStyle.green,
        custom_id="ranked_join_queue",
    )
    async def join_queue(self, button, interaction):

        member = interaction.user

        if not isinstance(member, discord.Member):
            return await interaction.response.send_message(
                "This can only be used inside the server.",
                ephemeral=True,
            )

        setup_ok = await ensure_ranked_setup(member)

        if not setup_ok:
            return await interaction.response.send_message(
                "❌ I couldn't assign your ranked roles — "
                "my role is probably below the Ranked/rank roles. "
                "Ask an admin to move my role up.",
                ephemeral=True,
            )

        player = await db.get_player(member.id)

        if player["in_queue"]:
            return await interaction.response.send_message(
                "❌ You're already in the 1v1 queue.",
                ephemeral=True,
            )

        rank_name = ranking.format_member_rank(member)

        await db.set_queue_state(member.id, True)

        await interaction.response.send_message(
            f"✅ Joined the 1v1 queue as **{rank_name}**.",
            ephemeral=True,
        )

        await run_matchmaking(interaction.client)

    @discord.ui.button(
        label="Leave Queue",
        style=discord.ButtonStyle.red,
        custom_id="ranked_leave_queue",
    )
    async def leave_queue(self, button, interaction):

        player = await db.get_player(interaction.user.id)

        if not player["in_queue"]:
            return await interaction.response.send_message(
                "❌ You're not currently in the 1v1 queue.",
                ephemeral=True,
            )

        await db.set_queue_state(
            interaction.user.id,
            False,
        )

        await interaction.response.send_message(
            "✅ You left the 1v1 queue.",
            ephemeral=True,
        )

        await update_queue_panel(interaction.guild)


async def update_queue_panel(guild):

    channel = find_channel_by_suffix(
        guild,
        RANKED_CHANNEL_NAME,
    )

    if channel is None:
        return

    embed = await build_queue_embed(guild)

    async for message in channel.history(limit=100):

        if message.author.id != guild.me.id:
            continue

        if not message.embeds:
            continue

        if message.embeds[0].title != "🎮 1v1 Queue":
            continue

        try:
            await message.edit(
                embed=embed,
                view=QueueView(),
            )
        except discord.HTTPException:
            pass

        return

    try:
        await channel.send(
            embed=embed,
            view=QueueView(),
        )
    except discord.HTTPException:
        pass



class SubmitScoreModal(discord.ui.Modal):

    def __init__(self, match_id, player1, player2):
        super().__init__(title="Submit 1v1 Result")

        self.match_id = match_id
        self.player1 = player1
        self.player2 = player2

        self.winner_input = discord.ui.InputText(
            label="Winner username (exact)",
            placeholder=(
                f"{player1.display_name} or "
                f"{player2.display_name}"
            ),
        )

        self.winner_points = discord.ui.InputText(
            label="Winner points",
            placeholder="e.g. 15",
        )

        self.loser_points = discord.ui.InputText(
            label="Loser points",
            placeholder="e.g. 13",
        )

        self.add_item(self.winner_input)
        self.add_item(self.winner_points)
        self.add_item(self.loser_points)

    async def callback(self, interaction):

        if interaction.user.id not in (
            self.player1.id,
            self.player2.id,
        ):
            return await interaction.response.send_message(
                "Only the two players in this match can submit a result.",
                ephemeral=True,
            )

        name = self.winner_input.value.strip().lower()

        if name in (
            self.player1.display_name.lower(),
            self.player1.name.lower(),
        ):
            winner = self.player1
            loser = self.player2

        elif name in (
            self.player2.display_name.lower(),
            self.player2.name.lower(),
        ):
            winner = self.player2
            loser = self.player1

        else:
            return await interaction.response.send_message(
                "Couldn't match that name to either player.",
                ephemeral=True,
            )

        try:
            winner_points = int(
                self.winner_points.value.strip()
            )
            loser_points = int(
                self.loser_points.value.strip()
            )
        except ValueError:
            return await interaction.response.send_message(
                "Points must be numbers.",
                ephemeral=True,
            )

        if winner_points < 0 or loser_points < 0:
            return await interaction.response.send_message(
                "Points cannot be negative.",
                ephemeral=True,
            )

        # Winner must win by at least 2.
        if winner_points - loser_points < 2:
            return await interaction.response.send_message(
                "❌ The winner must win by at least **2 points**.",
                ephemeral=True,
            )

        # Acknowledge before MongoDB / Discord work.
        await interaction.response.defer()

        match = await db.get_match(self.match_id)

        if not match:
            return await interaction.edit_original_response(
                content="❌ Match not found."
            )

        if match["status"] != "pending":
            return await interaction.edit_original_response(
                content="❌ This match already has a submitted result."
            )

        result = await db.record_match_result(
            self.match_id,
            winner.id,
            loser.id,
            winner_points,
            loser_points,
            interaction.user.id,
        )

        if result is None:
            return await interaction.edit_original_response(
                content=(
                    "❌ Someone already submitted a result for this match."
                )
            )

        winner_player = await db.get_player(winner.id)
        loser_player = await db.get_player(loser.id)

        await db.update_player(
            winner.id,
            wins=winner_player["wins"] + 1,
        )

        await db.update_player(
            loser.id,
            losses=loser_player["losses"] + 1,
        )

        embed = discord.Embed(
            title="🏆 Ranked 1v1 Result",
            color=discord.Color.green(),
        )

        embed.add_field(
            name="Winner",
            value=(
                f"{winner.mention} — "
                f"{ranking.format_member_rank(winner)}"
            ),
            inline=False,
        )

        embed.add_field(
            name="Loser",
            value=(
                f"{loser.mention} — "
                f"{ranking.format_member_rank(loser)}"
            ),
            inline=False,
        )

        embed.add_field(
            name="Final Score",
            value=(
                f"**{winner_points} - {loser_points}**"
            ),
            inline=False,
        )

        embed.add_field(
            name="Submitted By",
            value=interaction.user.mention,
            inline=False,
        )

        embed.add_field(
            name="Status",
            value="✅ Result recorded.",
            inline=False,
        )

        await interaction.edit_original_response(
            content="",
            embed=embed,
            view=None,
        )

        # Send result to ranked logs.
        logs_channel = find_channel_by_suffix(
            interaction.guild,
            RANKED_LOGS_CHANNEL_NAME,
        )

        if logs_channel is not None:
            try:
                await logs_channel.send(
                    embed=embed,
                )
            except discord.HTTPException:
                pass

        # Disable the original match controls.
        try:
            if isinstance(
                interaction.channel,
                discord.Thread,
            ):
                await interaction.channel.edit(
                    archived=True,
                    locked=True,
                )
        except discord.HTTPException:
            pass



class MatchThreadView(discord.ui.View):

    def __init__(
        self,
        match_id,
        player1,
        player2,
    ):
        super().__init__(timeout=None)

        self.match_id = match_id
        self.player1 = player1
        self.player2 = player2

    @discord.ui.button(
        label="Submit Result",
        style=discord.ButtonStyle.blurple,
        custom_id="submit_result",
    )
    async def submit(self, button, interaction):

        if interaction.user.id not in (
            self.player1.id,
            self.player2.id,
        ):
            return await interaction.response.send_message(
                "Only the two players in this match can do that.",
                ephemeral=True,
            )

        match = await db.get_match(self.match_id)

        if not match:
            return await interaction.response.send_message(
                "❌ Match not found.",
                ephemeral=True,
            )

        if match["status"] != "pending":
            return await interaction.response.send_message(
                "❌ This match has already been completed.",
                ephemeral=True,
            )

        await interaction.response.send_modal(
            SubmitScoreModal(
                self.match_id,
                self.player1,
                self.player2,
            )
        )

    @discord.ui.button(
        label="Call Admin",
        style=discord.ButtonStyle.grey,
        custom_id="call_admin",
    )
    async def call_admin(self, button, interaction):

        if interaction.user.id not in (
            self.player1.id,
            self.player2.id,
        ):
            return await interaction.response.send_message(
                "Only the two players in this match can call an admin.",
                ephemeral=True,
            )

        await interaction.response.defer()

        claimed = await db.claim_admin_call(
            self.match_id,
            interaction.user.id,
        )

        if claimed is None:
            return await interaction.edit_original_response(
                content="❌ An admin has already been called for this match."
            )

        guild = interaction.guild
        thread = interaction.channel

        staff_members = [
            member
            for member in guild.members
            if not member.bot
            and is_admin(member)
        ]

        if isinstance(thread, discord.Thread):

            for staff in staff_members:

                try:
                    await thread.add_user(staff)
                except discord.HTTPException:
                    pass

        mentions = (
            " ".join(
                member.mention
                for member in staff_members
            )
            if staff_members
            else "No available members with the Admin role were found."
        )

        embed = discord.Embed(
            title="🚨 Admin Called",
            description=(
                f"{interaction.user.mention} called an admin "
                "to review this match."
            ),
            color=discord.Color.red(),
        )

        try:
            await interaction.edit_original_response(
                content=mentions,
                embed=embed,
            )
        except discord.HTTPException:
            pass


async def run_matchmaking(bot):

    if not bot.guilds:
        return

    guild = bot.guilds[0]

    queued = await db.get_queued_players()
    players = []

    for player in queued:

        member = guild.get_member(
            player["user_id"]
        )

        if member is None:
            continue

        if not can_use_ranked(member):

            try:
                member = await guild.fetch_member(
                    player["user_id"]
                )
            except discord.NotFound:

                await db.set_queue_state(
                    player["user_id"],
                    False,
                )
                continue

            if not can_use_ranked(member):

                await db.set_queue_state(
                    player["user_id"],
                    False,
                )
                continue

        rank_info = ranking.get_rank_from_member(
            member
        )

        rank_number, subrank, role_name = rank_info

        players.append(
            {
                "user_id": player["user_id"],
                "rank": rank_number,
                "subrank": subrank,
                "role_name": role_name,
                "queue_since": player.get(
                    "queue_since",
                    0,
                ),
            }
        )

    players.sort(
        key=lambda p: p["queue_since"] or 0
    )

    matched_ids = set()

    for player in players:

        if player["user_id"] in matched_ids:
            continue

        candidates = [
            other
            for other in players
            if (
                other["user_id"] not in matched_ids
                and other["user_id"] != player["user_id"]
                and abs(
                    other["rank"] - player["rank"]
                ) <= MAX_RANK_GAP
            )
        ]

        opponent = ranking.best_role_match(
            player,
            candidates,
        )

        if opponent is None:
            continue

        matched_ids.add(
            player["user_id"]
        )
        matched_ids.add(
            opponent["user_id"]
        )

        await db.set_queue_state(
            player["user_id"],
            False,
        )

        await db.set_queue_state(
            opponent["user_id"],
            False,
        )

        try:
            await create_match_thread(
                bot,
                player["user_id"],
                opponent["user_id"],
            )
        except Exception as e:
            print(
                "⚠️ Failed to create match thread for "
                f"{player['user_id']} vs "
                f"{opponent['user_id']}: "
                f"{type(e).__name__}: {e}"
            )

    await update_queue_panel(guild)


async def create_match_thread(
    bot,
    user_id1,
    user_id2,
):

    guild = bot.guilds[0]

    p1 = (
        guild.get_member(user_id1)
        or await guild.fetch_member(user_id1)
    )

    p2 = (
        guild.get_member(user_id2)
        or await guild.fetch_member(user_id2)
    )

    channel = find_channel_by_suffix(
        guild,
        RANKED_CHANNEL_NAME,
    )

    if channel is None:
        channel = guild.text_channels[0]

    thread = await channel.create_thread(
        name=(
            f"1v1: "
            f"{p1.display_name} vs "
            f"{p2.display_name}"
        ),
        type=discord.ChannelType.private_thread,
        invitable=False,
    )

    # Only the two players are added normally.
    await thread.add_user(p1)
    await thread.add_user(p2)

    match_id = await db.create_match(
        thread.id,
        p1.id,
        p2.id,
    )


    embed = discord.Embed(
        title="⚔️ Ranked 1v1 Match Found!",
        color=discord.Color.gold(),
    )

    embed.add_field(
        name="Player 1",
        value=(
            f"{p1.mention} — "
            f"{ranking.format_member_rank(p1)}"
        ),
        inline=True,
    )

    embed.add_field(
        name="Player 2",
        value=(
            f"{p2.mention} — "
            f"{ranking.format_member_rank(p2)}"
        ),
        inline=True,
    )

    embed.add_field(
        name="Instructions",
        value=(
            "Play your match, then whoever wins hits "
            "**Submit Result** below.\n\n"
            "⚠️ The winner must win by **at least 2 points**."
        ),
        inline=False,
    )

    await thread.send(
        content=f"{p1.mention} {p2.mention}",
        embed=embed,
        view=MatchThreadView(
            match_id,
            p1,
            p2,
        ),
    )



class RankEvaluateView(discord.ui.View):

    def __init__(
        self,
        target: discord.Member,
        invoker_id: int,
    ):

        super().__init__(timeout=120)

        self.target = target
        self.invoker_id = invoker_id
        self.selected_rank = None
        self.selected_subrank = None

        self.rank_select = discord.ui.Select(
            placeholder="Main rank (R1-R10)",
            options=[
                discord.SelectOption(
                    label=f"R{r}",
                    value=str(r),
                )
                for r in range(1, 11)
            ],
        )

        self.rank_select.callback = self.on_rank_select
        self.add_item(self.rank_select)

        self.subrank_select = discord.ui.Select(
            placeholder="Sub-rank (ignored for R10)",
            options=[
                discord.SelectOption(
                    label=s,
                    value=s,
                )
                for s in (
                    "Low",
                    "Mid",
                    "High",
                )
            ],
        )

        self.subrank_select.callback = self.on_subrank_select
        self.add_item(self.subrank_select)

    async def on_rank_select(self, interaction):

        if interaction.user.id != self.invoker_id:
            return await interaction.response.send_message(
                "This isn't your evaluation.",
                ephemeral=True,
            )

        self.selected_rank = int(
            self.rank_select.values[0]
        )

        await interaction.response.defer()

    async def on_subrank_select(self, interaction):

        if interaction.user.id != self.invoker_id:
            return await interaction.response.send_message(
                "This isn't your evaluation.",
                ephemeral=True,
            )

        self.selected_subrank = (
            self.subrank_select.values[0]
        )

        await interaction.response.defer()

    @discord.ui.button(
        label="Submit Evaluation",
        style=discord.ButtonStyle.green,
    )
    async def submit(self, button, interaction):

        if interaction.user.id != self.invoker_id:
            return await interaction.response.send_message(
                "This isn't your evaluation.",
                ephemeral=True,
            )

        if self.selected_rank is None:
            return await interaction.response.send_message(
                "Pick a rank first.",
                ephemeral=True,
            )

        rank = self.selected_rank

        subrank = (
            ""
            if rank == 10
            else (
                self.selected_subrank
                or "Low"
            )
        )

        role_name = (
            ranking.RANK_NAMES
            .get(rank, {})
            .get(subrank)
        )

        if role_name is None:
            return await interaction.response.send_message(
                "Couldn't resolve that rank/subrank combo.",
                ephemeral=True,
            )

        guild = interaction.guild

        new_role = discord.utils.get(
            guild.roles,
            name=role_name,
        )

        if new_role is None:
            return await interaction.response.send_message(
                f"❌ Role {role_name!r} doesn't exist in this server.",
                ephemeral=True,
            )

        all_rank_role_names = {
            name
            for ranks in ranking.RANK_NAMES.values()
            for name in ranks.values()
        }

        old_rank_roles = [
            role
            for role in self.target.roles
            if role.name in all_rank_role_names
        ]

        try:

            if old_rank_roles:
                await self.target.remove_roles(
                    *old_rank_roles,
                    reason="Re-evaluated rank",
                )

            await self.target.add_roles(
                new_role,
                reason=f"Evaluated by {interaction.user}",
                atomic=False,
            )

        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ I don't have permission to change that member's roles.",
                ephemeral=True,
            )

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content=(
                f"✅ Recorded {self.target.mention} as "
                f"{new_role.mention}."
            ),
            view=self,
        )

        logs_channel = find_channel_by_suffix(
            guild,
            RANKED_LOGS_CHANNEL_NAME,
        )

        if logs_channel is not None:
            await logs_channel.send(
                f"Successfully Recorded "
                f"{self.target.mention} as "
                f"{new_role.mention}"
            )


class Ranked(commands.Cog):

    def __init__(self, bot):

        self.bot = bot
        self.matchmaking_loop.start()

    def cog_unload(self):
        self.matchmaking_loop.cancel()



    @commands.slash_command(
        name="debugranks",
        description=(
            "[Debug] Compare configured rank role names "
            "against real Discord roles."
        ),
    )
    async def debugranks(self, ctx):

        guild = ctx.guild
        lines = []

        ranked_role = discord.utils.find(
            lambda r: (
                r.name == RANKED_ROLE_NAME
                or r.name.endswith(
                    "Ranked--------------|"
                )
            ),
            guild.roles,
        )

        lines.append(
            "Ranked role: "
            f"{'✅ FOUND' if ranked_role else '❌ NOT FOUND'} "
            f"(expected {RANKED_ROLE_NAME!r})"
        )

        lines.append("")
        lines.append(
            "Rank roles (configured vs. actual):"
        )

        for rank in range(10, 0, -1):

            for (
                subrank,
                expected_name,
            ) in ranking.RANK_NAMES[rank].items():

                found = discord.utils.get(
                    guild.roles,
                    name=expected_name,
                )

                status = "✅" if found else "❌"

                lines.append(
                    f"{status} R{rank} "
                    f"{subrank or '-'}: "
                    f"expected {expected_name!r}"
                )

        lines.append("")
        lines.append(
            "Your current roles (repr):"
        )

        for role in ctx.author.roles:

            if role.name != "@everyone":
                lines.append(
                    f"  {role.name!r}"
                )

        content = "\n".join(lines)

        if len(content) > 1900:
            content = (
                content[:1900]
                + "\n... (truncated)"
            )

        await ctx.respond(
            f"```\n{content}\n```",
            ephemeral=True,
        )


    @commands.slash_command(
        name="1v1queue",
        description=(
            "Join or leave the ranked 1v1 matchmaking queue."
        ),
    )
    async def one_v_one_queue(self, ctx):

        member = ctx.author

        setup_ok = await ensure_ranked_setup(
            member
        )

        if not setup_ok:
            return await ctx.respond(
                "❌ I couldn't assign your ranked roles — "
                "my role is probably below the Ranked/rank "
                "roles. Ask an admin to move my role up.",
                ephemeral=True,
            )

        player = await db.get_player(
            member.id
        )

        if player["in_queue"]:

            await db.set_queue_state(
                member.id,
                False,
            )

            await ctx.respond(
                "✅ You left the 1v1 queue.",
                ephemeral=True,
            )

            await update_queue_panel(
                ctx.guild
            )

        else:

            rank_name = ranking.format_member_rank(
                member
            )

            await db.set_queue_state(
                member.id,
                True,
            )

            await ctx.respond(
                f"✅ Joined the 1v1 queue as "
                f"**{rank_name}**.",
                ephemeral=True,
            )

            await run_matchmaking(
                self.bot
            )



    @commands.slash_command(
        name="rank",
        description=(
            "Check your or another player's rank."
        ),
    )
    async def rank(
        self,
        ctx,
        member: discord.Option(
            discord.Member,
            "Member to check",
            required=False,
        ),
    ):

        member = member or ctx.author

        player = await db.get_player(
            member.id
        )

        rank_name = ranking.format_member_rank(
            member
        )

        embed = discord.Embed(
            title=f"{member.display_name}'s Rank",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="Rank",
            value=rank_name,
            inline=True,
        )

        embed.add_field(
            name="Ranked",
            value=(
                "Yes"
                if ranking.is_ranked(member)
                else "No"
            ),
            inline=True,
        )

        embed.add_field(
            name="Record",
            value=(
                f"{player['wins']}W - "
                f"{player['losses']}L"
            ),
            inline=True,
        )

        await ctx.respond(
            embed=embed
        )

    @commands.slash_command(
        name="sign",
        description="Sign a member to a team role.",
    )
    @commands.has_permissions(
        moderate_members=True
    )
    async def sign(
        self,
        ctx,
        user: discord.Option(
            discord.Member,
            "Member to sign",
        ),
        team: discord.Option(
            discord.Role,
            "Team role to sign them to",
        ),
    ):

        await ctx.defer(
            ephemeral=True
        )

        try:

            await user.add_roles(
                team,
                reason=f"Signed by {ctx.author}",
                atomic=False,
            )

        except discord.Forbidden:

            return await ctx.respond(
                "❌ I don't have permission to assign "
                "that role — check my role position.",
                ephemeral=True,
            )

        signs_channel = find_channel_by_suffix(
            ctx.guild,
            SIGNS_CHANNEL_NAME,
        )

        if signs_channel is not None:

            await signs_channel.send(
                f"{user.mention} has been signed to - "
                f"{team.mention}"
            )

        await ctx.respond(
            f"✅ Signed {user.mention} to "
            f"{team.mention}.",
            ephemeral=True,
        )


    @commands.slash_command(
        name="evaluate",
        description=(
            "Evaluate a member and assign their rank."
        ),
    )
    @commands.has_permissions(
        moderate_members=True
    )
    async def evaluate(
        self,
        ctx,
        member: discord.Option(
            discord.Member,
            "Member to evaluate",
        ),
    ):

        view = RankEvaluateView(
            member,
            ctx.author.id,
        )

        await ctx.respond(
            f"Evaluating {member.mention} — "
            "pick a rank below:",
            view=view,
            ephemeral=True,
        )

    @tasks.loop(seconds=10)
    async def matchmaking_loop(self):

        await run_matchmaking(
            self.bot
        )

    @matchmaking_loop.before_loop
    async def before_matchmaking(self):

        await self.bot.wait_until_ready()

    @matchmaking_loop.error
    async def matchmaking_loop_error(
        self,
        error,
    ):

        print(
            "⚠️ matchmaking_loop crashed: "
            f"{type(error).__name__}: {error}"
        )



async def register_persistent_views(bot):

    bot.add_view(
        QueueView()
    )

    rows = await db.get_active_matches()

    guild = (
        bot.guilds[0]
        if bot.guilds
        else None
    )

    if guild is None:
        return

    for row in rows:

        try:

            p1 = (
                guild.get_member(
                    row["player1"]
                )
                or await guild.fetch_member(
                    row["player1"]
                )
            )

            p2 = (
                guild.get_member(
                    row["player2"]
                )
                or await guild.fetch_member(
                    row["player2"]
                )
            )

        except discord.NotFound:

            continue

        if row["status"] == "pending":

            bot.add_view(
                MatchThreadView(
                    row["match_id"],
                    p1,
                    p2,
                )
            )


def setup(bot):

    bot.add_cog(
        Ranked(bot)
    )
