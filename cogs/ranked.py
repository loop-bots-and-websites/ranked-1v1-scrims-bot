import discord
from discord.ext import commands, tasks

import db
import ranking


RANKED_CHANNEL_NAME = "ranked-1v1"
RANKED_ROLE_NAME = "|--------------Ranked--------------|"


def find_channel_by_suffix(guild, suffix):
    return discord.utils.find(
        lambda c: c.name.lower().endswith(suffix),
        guild.text_channels,
    )



async def ensure_ranked_setup(member):
    guild = member.guild

    role_names = {
        role.name
        for role in member.roles
    }

    roles_to_add = []

    if RANKED_ROLE_NAME not in role_names:
        ranked_role = discord.utils.get(
            guild.roles,
            name=RANKED_ROLE_NAME,
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

    if RANKED_ROLE_NAME not in role_names:
        return False

    return ranking.get_rank_from_member(member) is not None



async def build_queue_embed(guild):
    queued = await db.get_queued_players()

    players = []

    for player in queued:
        member = guild.get_member(
            player["user_id"]
        )

        if member is None:
            continue

        rank_name = ranking.format_member_rank(
            member
        )

        players.append(
            f"{member.mention} — **{rank_name}**"
        )

    if players:
        queue_text = "\n".join(players)
    else:
        queue_text = "No players are currently waiting."

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
        super().__init__(
            timeout=None
        )


    @discord.ui.button(
        label="Join Queue",
        style=discord.ButtonStyle.green,
        custom_id="ranked_join_queue",
    )
    async def join_queue(
        self,
        button,
        interaction,
    ):
        member = interaction.user

        if not isinstance(
            member,
            discord.Member,
        ):
            return await interaction.response.send_message(
                "This can only be used inside the server.",
                ephemeral=True,
            )

        setup_ok = await ensure_ranked_setup(member)

        if not setup_ok:
            return await interaction.response.send_message(
                "❌ I couldn't assign your ranked roles — "
                "my role is probably below the Ranked/rank "
                "roles. Ask an admin to move my role up.",
                ephemeral=True,
            )

        player = await db.get_player(
            member.id
        )

        if player["in_queue"]:
            return await interaction.response.send_message(
                "❌ You're already in the 1v1 queue.",
                ephemeral=True,
            )

        rank_name = ranking.format_member_rank(
            member
        )

        await db.set_queue_state(
            member.id,
            True,
        )

        await interaction.response.send_message(
            f"✅ Joined the 1v1 queue as **{rank_name}**.",
            ephemeral=True,
        )

        await update_queue_panel(
            interaction.guild
        )


    @discord.ui.button(
        label="Leave Queue",
        style=discord.ButtonStyle.red,
        custom_id="ranked_leave_queue",
    )
    async def leave_queue(
        self,
        button,
        interaction,
    ):
        player = await db.get_player(
            interaction.user.id
        )

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

        await update_queue_panel(
            interaction.guild
        )



async def update_queue_panel(guild):
    channel = find_channel_by_suffix(
        guild,
        RANKED_CHANNEL_NAME,
    )

    if channel is None:
        return

    embed = await build_queue_embed(
        guild
    )

    # Find our existing queue panel.
    async for message in channel.history(
        limit=100
    ):
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

    # If no panel exists, create one.
    try:
        await channel.send(
            embed=embed,
            view=QueueView(),
        )
    except discord.HTTPException:
        pass



class ScoreConfirmView(discord.ui.View):

    def __init__(
        self,
        match_id,
        submitter_id,
        opponent_id,
    ):
        super().__init__(
            timeout=None
        )

        self.match_id = match_id
        self.submitter_id = submitter_id
        self.opponent_id = opponent_id

    @discord.ui.button(
        label="Confirm Result",
        style=discord.ButtonStyle.green,
        custom_id="confirm_result",
    )
    async def confirm(
        self,
        button,
        interaction,
    ):
        if interaction.user.id != self.opponent_id:
            return await interaction.response.send_message(
                "Only the other player can confirm this.",
                ephemeral=True,
            )

        match = await db.get_match(
            self.match_id
        )

        if not match:
            return await interaction.response.send_message(
                "Match not found.",
                ephemeral=True,
            )

        if match["status"] != "awaiting_confirm":
            return await interaction.response.send_message(
                "This result was already resolved.",
                ephemeral=True,
            )

        await interaction.response.defer()

        winner_player = await db.get_player(
            match["winner"]
        )

        loser_player = await db.get_player(
            match["loser"]
        )

        await db.update_player(
            match["winner"],
            wins=winner_player["wins"] + 1,
        )

        await db.update_player(
            match["loser"],
            losses=loser_player["losses"] + 1,
        )

        await db.update_match(
            self.match_id,
            status="confirmed",
        )

        for child in self.children:
            if isinstance(
                child,
                discord.ui.Button,
            ):
                child.disabled = True

        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()

        status_index = next(
            (
                i
                for i, field in enumerate(
                    embed.fields
                )
                if field.name == "Status"
            ),
            None,
        )

        if status_index is not None:
            embed.set_field_at(
                status_index,
                name="Status",
                value="✅ Both players confirmed. Result recorded.",
                inline=False,
            )

        await interaction.edit_original_response(
            embed=embed,
            view=self,
        )

        try:
            thread = interaction.channel

            if isinstance(
                thread,
                discord.Thread,
            ):
                await thread.edit(
                    archived=True,
                    locked=True,
                )
        except discord.HTTPException:
            pass

    @discord.ui.button(
        label="Deny Result",
        style=discord.ButtonStyle.red,
        custom_id="deny_result",
    )
    async def deny(
        self,
        button,
        interaction,
    ):
        if interaction.user.id != self.opponent_id:
            return await interaction.response.send_message(
                "Only the other player can deny this.",
                ephemeral=True,
            )

        await interaction.response.defer()

        await db.update_match(
            self.match_id,
            status="denied",
        )

        for child in self.children:
            if isinstance(
                child,
                discord.ui.Button,
            ):
                child.disabled = True

        await interaction.edit_original_response(
            view=self,
        )

        await interaction.followup.send(
            "❌ Result denied. A staff member should review this match."
        )

    @discord.ui.button(
        label="Call Admin",
        style=discord.ButtonStyle.grey,
        custom_id="call_admin",
    )
    async def call_admin(
        self,
        button,
        interaction,
    ):
        await interaction.response.send_message(
            "🚨 Staff have been notified to review this match."
        )


class SubmitScoreModal(discord.ui.Modal):

    def __init__(
        self,
        match_id,
        player1,
        player2,
    ):
        super().__init__(
            title="Submit 1v1 Result"
        )

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
            placeholder="e.g. 5",
        )

        self.add_item(
            self.winner_input
        )

        self.add_item(
            self.winner_points
        )

        self.add_item(
            self.loser_points
        )

    async def callback(
        self,
        interaction,
    ):
        print(f"DEBUG: Modal callback started for match {self.match_id} by {interaction.user}")

        try:
            await interaction.response.defer()

            name = (
                self.winner_input.value
                .strip()
                .lower()
            )

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
                return await interaction.followup.send(
                    "Couldn't match that name to either player.",
                    ephemeral=True,
                )

            try:
                winner_points = int(
                    self.winner_points.value
                )

                loser_points = int(
                    self.loser_points.value
                )

            except ValueError:
                return await interaction.followup.send(
                    "Points must be numbers.",
                    ephemeral=True,
                )

            if winner_points < 0 or loser_points < 0:
                return await interaction.followup.send(
                    "Points cannot be negative.",
                    ephemeral=True,
                )

            if interaction.user.id not in (
                self.player1.id,
                self.player2.id,
            ):
                return await interaction.followup.send(
                    "Only the two players in this match can submit a result.",
                    ephemeral=True,
                )

            print("DEBUG: Updating match in DB...")
            await db.update_match(
                self.match_id,
                winner=winner.id,
                loser=loser.id,
                winner_points=winner_points,
                loser_points=loser_points,
                submitted_by=interaction.user.id,
                status="awaiting_confirm",
            )

            opponent = (
                loser
                if interaction.user.id == winner.id
                else winner
            )

            embed = discord.Embed(
                title="📝 1v1 Score Submitted",
                color=discord.Color.blurple(),
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
                name="Winner Points",
                value=str(winner_points),
                inline=True,
            )

            embed.add_field(
                name="Loser Points",
                value=str(loser_points),
                inline=True,
            )

            embed.add_field(
                name="Submitted By",
                value=interaction.user.mention,
                inline=False,
            )

            embed.add_field(
                name="Status",
                value="Waiting for the other player to confirm.",
                inline=False,
            )

            print("DEBUG: Sending followup embed...")
            await interaction.followup.send(
                embed=embed,
                view=ScoreConfirmView(
                    self.match_id,
                    interaction.user.id,
                    opponent.id,
                ),
            )
            print("DEBUG: Modal submission finished successfully.")

        except Exception as e:
            print(f"❌ ERROR in SubmitScoreModal callback: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            try:
                await interaction.followup.send(
                    f"❌ An error occurred while processing the result: `{e}`",
                    ephemeral=True
                )
            except Exception:
                pass



class MatchThreadView(discord.ui.View):

    def __init__(
        self,
        match_id,
        player1,
        player2,
    ):
        super().__init__(
            timeout=None
        )

        self.match_id = match_id
        self.player1 = player1
        self.player2 = player2

    @discord.ui.button(
        label="Submit Result",
        style=discord.ButtonStyle.blurple,
        custom_id="submit_result",
    )
    async def submit(
        self,
        button,
        interaction,
    ):
        if interaction.user.id not in (
            self.player1.id,
            self.player2.id,
        ):
            return await interaction.response.send_message(
                "Only the two players in this match can do that.",
                ephemeral=True,
            )

        match = await db.get_match(self.match_id)
        if match and match.get("status") != "pending":
            return await interaction.response.send_message(
                "A result has already been submitted or resolved for this match.",
                ephemeral=True,
            )

        await interaction.response.send_modal(
            SubmitScoreModal(
                self.match_id,
                self.player1,
                self.player2,
            )
        )



class Ranked(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.matchmaking_loop.start()

    def cog_unload(self):
        self.matchmaking_loop.cancel()


    @commands.slash_command(
        name="debugranks",
        description="[Debug] Compare configured rank role names against real Discord roles.",
    )
    async def debugranks(
        self,
        ctx,
    ):
        guild = ctx.guild
        lines = []

        ranked_role = discord.utils.get(
            guild.roles,
            name=RANKED_ROLE_NAME,
        )

        lines.append(
            f"Ranked role: "
            f"{'✅ FOUND' if ranked_role else '❌ NOT FOUND'} "
            f"(expected {RANKED_ROLE_NAME!r})"
        )

        lines.append("")
        lines.append("Rank roles (configured vs. actual):")

        for rank in range(10, 0, -1):
            for subrank, expected_name in ranking.RANK_NAMES[rank].items():
                found = discord.utils.get(
                    guild.roles,
                    name=expected_name,
                )
                status = "✅" if found else "❌"
                lines.append(
                    f"{status} R{rank} {subrank or '-'}: "
                    f"expected {expected_name!r}"
                )

        lines.append("")
        lines.append("Your current roles (repr, to catch hidden character mismatches):")

        for role in ctx.author.roles:
            if role.name != "@everyone":
                lines.append(
                    f"  {role.name!r}"
                )

        content = "\n".join(lines)

        if len(content) > 1900:
            content = content[:1900] + "\n... (truncated)"

        await ctx.respond(
            f"```\n{content}\n```",
            ephemeral=True,
        )


    @commands.slash_command(
        name="1v1queue",
        description="Join or leave the ranked 1v1 matchmaking queue.",
    )
    async def one_v_one_queue(
        self,
        ctx,
    ):
        member = ctx.author

        setup_ok = await ensure_ranked_setup(member)

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

        else:
            rank_name = ranking.format_member_rank(
                member
            )

            await db.set_queue_state(
                member.id,
                True,
            )

            await ctx.respond(
                f"✅ Joined the 1v1 queue as **{rank_name}**.",
                ephemeral=True,
            )

        await update_queue_panel(
            ctx.guild
        )


    @commands.slash_command(
        name="rank",
        description="Check your or another player's rank.",
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



    @tasks.loop(seconds=10)
    async def matchmaking_loop(self):
        queued = await db.get_queued_players()

        guild = self.bot.guilds[0]

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

            players.append({
                "user_id": player["user_id"],
                "rank": rank_number,
                "subrank": subrank,
                "role_name": role_name,
                "queue_since": player.get(
                    "queue_since",
                    0,
                ),
            })

        players.sort(
            key=lambda p:
            p["queue_since"] or 0
        )

        matched_ids = set()

        for player in players:
            if player["user_id"] in matched_ids:
                continue

            candidates = [
                other
                for other in players
                if other["user_id"]
                not in matched_ids
                and other["user_id"]
                != player["user_id"]
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
                await self.create_match_thread(
                    player["user_id"],
                    opponent["user_id"],
                )
            except Exception as e:
                print(
                    "⚠️ Failed to create match thread for "
                    f"{player['user_id']} vs {opponent['user_id']}: "
                    f"{type(e).__name__}: {e}"
                )

        await update_queue_panel(
            guild
        )

    @matchmaking_loop.before_loop
    async def before_matchmaking(
        self,
    ):
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


    async def create_match_thread(
        self,
        user_id1,
        user_id2,
    ):
        guild = self.bot.guilds[0]

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
                "Play your match, then whoever "
                "finishes first hits **Submit Result** "
                "below. The other player confirms it."
            ),
            inline=False,
        )

        await thread.send(
            content=(
                f"{p1.mention} {p2.mention}"
            ),
            embed=embed,
            view=MatchThreadView(
                match_id,
                p1,
                p2,
            ),
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

        elif row["status"] == "awaiting_confirm":
            winner = row["winner"]

            opponent_id = (
                row["loser"]
                if winner == row["submitted_by"]
                else row["winner"]
            )

            bot.add_view(
                ScoreConfirmView(
                    row["match_id"],
                    row["submitted_by"],
                    opponent_id,
                )
            )


def setup(bot):
    bot.add_cog(
        Ranked(bot)
    )
