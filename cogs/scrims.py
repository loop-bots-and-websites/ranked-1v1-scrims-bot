import random
import json

import discord
from discord.ext import commands
from discord import Option

import db



SCRIM_CHANNEL_NAME = "ranked-scrims"
BOT_CMDS_CHANNEL_NAME = "cmd"

STAFF_PERMISSION = "moderate_members"



def is_staff(member: discord.Member) -> bool:
    return (
        member.guild_permissions.moderate_members
        or member.guild_permissions.administrator
    )


def get_team_size(teams: str) -> int:
    """
    4v4 -> 4
    5v5 -> 5
    """

    try:
        return int(teams.split("v")[0])
    except (ValueError, IndexError):
        return 5


def get_required_players(teams: str) -> int:
    return get_team_size(teams) * 2


def joined_list(scrim: dict) -> list:
    try:
        return db.joined_list(scrim)
    except Exception:
        return []


def build_scrim_embed(
    scrim: dict,
    host: discord.Member,
) -> discord.Embed:

    joined = joined_list(scrim)

    status = scrim.get("status", "open")

    if status == "closed":
        status_text = "🔒 Scrim Closed"

    elif status == "selected":
        status_text = (
            "✅ Players selected — scrim is ready."
        )

    else:
        status_text = (
            "React with the buttons below to join, "
            "view the scrim details, close or null this scrim.\n"
            "(Or use `/joinscrim`, `/closescrim`, `/nullscrim` "
            f"in #{BOT_CMDS_CHANNEL_NAME} with the Scrim ID below.)"
        )

    # Ranked = green
    if scrim["match_type"] == "Ranked":
        color = discord.Color.green()
    else:
        color = discord.Color.blurple()

    if status == "closed":
        color = discord.Color.dark_grey()

    embed = discord.Embed(
        title=(
            "A new Ranked scrim is live!"
            if scrim["match_type"] == "Ranked"
            else "A new Unranked scrim is live!"
        ),
        description=status_text,
        color=color,
    )

    embed.add_field(
        name="Host",
        value=host.mention,
        inline=False,
    )

  

    embed.add_field(
        name="Match Type",
        value=scrim["match_type"],
        inline=True,
    )

    embed.add_field(
        name="Format",
        value=scrim["format_type"],
        inline=True,
    )


    embed.add_field(
        name="Max Players",
        value=str(scrim["max_players"]),
        inline=True,
    )



    embed.add_field(
        name="Region",
        value=scrim["region"],
        inline=True,
    )


    embed.add_field(
        name="Teams",
        value=scrim["teams"],
        inline=True,
    )


    embed.add_field(
        name="Map",
        value=scrim["map_type"],
        inline=True,
    )


    if scrim.get("minimum_rank"):
        embed.add_field(
            name="Minimum Rank",
            value=scrim["minimum_rank"],
            inline=True,
        )

    if scrim.get("max_rank"):
        embed.add_field(
            name="Maximum Rank",
            value=scrim["max_rank"],
            inline=True,
        )


    if status == "selected":
        players_title = (
            f"Players selected "
            f"({len(joined)}/{get_required_players(scrim['teams'])})"
        )
    else:
        players_title = (
            f"Players joined "
            f"({len(joined)}/{scrim['max_players']})"
        )

    if joined:

        players_text = "\n".join(
            f"<@{user_id}>"
            for user_id in joined
        )

    else:

        players_text = "None yet"

    embed.add_field(
        name=players_title,
        value=players_text,
        inline=False,
    )


    if status == "selected" and joined:

        team_size = get_team_size(
            scrim["teams"]
        )

        team_one = joined[:team_size]
        team_two = joined[team_size:team_size * 2]

        team_one_text = "\n".join(
            f"<@{user_id}>"
            for user_id in team_one
        )

        team_two_text = "\n".join(
            f"<@{user_id}>"
            for user_id in team_two
        )

        embed.add_field(
            name="Team 1",
            value=team_one_text or "None",
            inline=True,
        )

        embed.add_field(
            name="Team 2",
            value=team_two_text or "None",
            inline=True,
        )



    if scrim.get("server_link"):

        embed.add_field(
            name="Server",
            value="Use the **Join Server** button below.",
            inline=False,
        )


    embed.set_footer(
        text=(
            f"Scrim ID: {scrim['scrim_id']}  •  "
            "Created by the host, joinable from this message "
            f"or via commands in #{BOT_CMDS_CHANNEL_NAME}."
        )
    )

    return embed



def build_details_embed(
    scrim: dict,
    host: discord.Member,
) -> discord.Embed:

    joined = joined_list(scrim)

    status = scrim.get("status", "open")

    if status == "selected":

        title = "Scrim Ready"

        color = discord.Color.green()

    elif status == "closed":

        title = "Scrim Closed"

        color = discord.Color.dark_grey()

    else:

        title = "Scrim Details"

        color = discord.Color.blurple()

    embed = discord.Embed(
        title=title,
        color=color,
    )

    embed.add_field(
        name="Host",
        value=host.mention,
        inline=False,
    )

    embed.add_field(
        name="Match Type",
        value=scrim["match_type"],
        inline=True,
    )

    embed.add_field(
        name="Format",
        value=scrim["format_type"],
        inline=True,
    )

    embed.add_field(
        name="Max Players",
        value=str(scrim["max_players"]),
        inline=True,
    )

    embed.add_field(
        name="Region",
        value=scrim["region"],
        inline=True,
    )

    embed.add_field(
        name="Teams",
        value=scrim["teams"],
        inline=True,
    )

    embed.add_field(
        name="Map",
        value=scrim["map_type"],
        inline=True,
    )

    if scrim.get("minimum_rank"):

        embed.add_field(
            name="Minimum Rank",
            value=scrim["minimum_rank"],
            inline=True,
        )

    if scrim.get("max_rank"):

        embed.add_field(
            name="Maximum Rank",
            value=scrim["max_rank"],
            inline=True,
        )


    required = get_required_players(
        scrim["teams"]
    )

    if status == "selected":

        player_title = (
            f"Players selected ({len(joined)}/{required})"
        )

    else:

        player_title = (
            f"Players joined "
            f"({len(joined)}/{scrim['max_players']})"
        )

    if joined:

        player_text = "\n".join(
            f"<@{user_id}>"
            for user_id in joined
        )

    else:

        player_text = "None yet"

    embed.add_field(
        name=player_title,
        value=player_text,
        inline=False,
    )

    if status == "selected" and joined:

        team_size = get_team_size(
            scrim["teams"]
        )

        team_one = joined[:team_size]

        team_two = joined[
            team_size:team_size * 2
        ]

        embed.add_field(
            name="Team 1",
            value="\n".join(
                f"<@{user_id}>"
                for user_id in team_one
            ),
            inline=True,
        )

        embed.add_field(
            name="Team 2",
            value="\n".join(
                f"<@{user_id}>"
                for user_id in team_two
            ),
            inline=True,
        )

    return embed



class ScrimActionResult:

    def __init__(
        self,
        ok,
        error=None,
        embed=None,
        view=None,
        scrim=None,
        announcement=None,
        joined_msg=None,
    ):

        self.ok = ok
        self.error = error
        self.embed = embed
        self.view = view
        self.scrim = scrim
        self.announcement = announcement
        self.joined_msg = joined_msg


async def perform_join(
    guild: discord.Guild,
    scrim_id: int,
    user_id: int,
) -> ScrimActionResult:

    scrim = await db.get_scrim(
        scrim_id
    )

    if not scrim:

        return ScrimActionResult(
            False,
            error="❌ Scrim not found.",
        )

    if scrim["status"] != "open":

        return ScrimActionResult(
            False,
            error="❌ This scrim is no longer open.",
        )

    joined = joined_list(scrim)

    if user_id in joined:

        return ScrimActionResult(
            False,
            error="❌ You're already in this scrim.",
        )

    if len(joined) >= scrim["max_players"]:

        return ScrimActionResult(
            False,
            error="❌ This scrim is full.",
        )

    joined.append(
        user_id
    )

    await db.update_scrim(
        scrim_id,
        joined_players=json.dumps(joined),
    )


    if len(joined) >= scrim["max_players"]:

        required = get_required_players(
            scrim["teams"]
        )

        selected = random.sample(
            joined,
            min(
                required,
                len(joined),
            ),
        )

        await db.update_scrim(
            scrim_id,
            joined_players=json.dumps(selected),
            status="selected",
        )

        scrim = await db.get_scrim(
            scrim_id
        )

        host = guild.get_member(
            scrim["host_id"]
        )

        embed = build_scrim_embed(
            scrim,
            host,
        )

        view = ScrimView(
            scrim_id,
            scrim.get("server_link"),
        )

        team_size = get_team_size(
            scrim["teams"]
        )

        team_one = selected[:team_size]
        team_two = selected[team_size:team_size * 2]

        team_one_mentions = " ".join(
            f"<@{uid}>"
            for uid in team_one
        )

        team_two_mentions = " ".join(
            f"<@{uid}>"
            for uid in team_two
        )

        announcement = (
            "🎲 **The scrim is full!**\n\n"
            "The players have been randomly selected.\n\n"
            f"**Team 1:**\n{team_one_mentions}\n\n"
            f"**Team 2:**\n{team_two_mentions}\n\n"
            "Good luck!"
        )

        return ScrimActionResult(
            True,
            embed=embed,
            view=view,
            scrim=scrim,
            announcement=announcement,
        )



    scrim = await db.get_scrim(
        scrim_id
    )

    host = guild.get_member(
        scrim["host_id"]
    )

    embed = build_scrim_embed(
        scrim,
        host,
    )

    view = ScrimView(
        scrim_id,
        scrim.get("server_link"),
    )

    return ScrimActionResult(
        True,
        embed=embed,
        view=view,
        scrim=scrim,
        joined_msg=f"✅ <@{user_id}> joined the scrim.",
    )


async def perform_close(
    guild: discord.Guild,
    scrim_id: int,
    user_id: int,
) -> ScrimActionResult:

    scrim = await db.get_scrim(
        scrim_id
    )

    if not scrim:

        return ScrimActionResult(
            False,
            error="❌ Scrim not found.",
        )

    member = guild.get_member(
        user_id
    )

    if (
        scrim["host_id"] != user_id
        and not (member and is_staff(member))
    ):

        return ScrimActionResult(
            False,
            error="❌ Only the host or staff can close this scrim.",
        )

    await db.update_scrim(
        scrim_id,
        status="closed",
    )

    scrim = await db.get_scrim(
        scrim_id
    )

    host = guild.get_member(
        scrim["host_id"]
    )

    embed = build_scrim_embed(
        scrim,
        host,
    )

    view = ScrimView(
        scrim_id,
        scrim.get("server_link"),
    )

    for child in view.children:

        if isinstance(
            child,
            discord.ui.Button,
        ):

            if child.style != discord.ButtonStyle.link:
                child.disabled = True

    return ScrimActionResult(
        True,
        embed=embed,
        view=view,
        scrim=scrim,
    )


async def perform_null(
    guild: discord.Guild,
    scrim_id: int,
    user_id: int,
) -> ScrimActionResult:

    scrim = await db.get_scrim(
        scrim_id
    )

    if not scrim:

        return ScrimActionResult(
            False,
            error="❌ Scrim not found.",
        )

    member = guild.get_member(
        user_id
    )

    if (
        scrim["host_id"] != user_id
        and not (member and is_staff(member))
    ):

        return ScrimActionResult(
            False,
            error="❌ Only the host or staff can null this scrim.",
        )

    await db.update_scrim(
        scrim_id,
        joined_players="[]",
        status="open",
    )

    scrim = await db.get_scrim(
        scrim_id
    )

    host = guild.get_member(
        scrim["host_id"]
    )

    embed = build_scrim_embed(
        scrim,
        host,
    )

    view = ScrimView(
        scrim_id,
        scrim.get("server_link"),
    )

    return ScrimActionResult(
        True,
        embed=embed,
        view=view,
        scrim=scrim,
    )


async def update_scrim_message(
    bot: commands.Bot,
    scrim: dict,
    embed: discord.Embed,
    view: discord.ui.View,
) -> bool:

    channel = bot.get_channel(
        scrim["channel_id"]
    )

    if channel is None:

        try:
            channel = await bot.fetch_channel(
                scrim["channel_id"]
            )
        except discord.HTTPException:
            return False

    try:

        message = await channel.fetch_message(
            scrim["message_id"]
        )

        await message.edit(
            embed=embed,
            view=view,
        )

        return True

    except discord.HTTPException:
        return False



class ScrimView(
    discord.ui.View
):

    def __init__(
        self,
        scrim_id: int,
        server_link: str | None = None,
    ):

        super().__init__(
            timeout=None
        )

        self.scrim_id = scrim_id



        if server_link:

            self.add_item(
                discord.ui.Button(
                    label="Join Server",
                    style=discord.ButtonStyle.link,
                    url=server_link,
                )
            )


    @discord.ui.button(
        label="Join Scrim",
        style=discord.ButtonStyle.green,
        custom_id="scrim_join",
    )
    async def join(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction,
    ):

 
        await ctx.defer(ephemeral=True)

        await interaction.response.defer()

        result = await perform_join(
            interaction.guild,
            self.scrim_id,
            interaction.user.id,
        )

        if not result.ok:

            return await interaction.response.send_message(
                result.error,
                ephemeral=True,
            )

        await interaction.edit_original_response(
            embed=result.embed,
            view=result.view,
        )

        if result.announcement:

            await interaction.followup.send(
                content=result.announcement
            )

        elif result.joined_msg:

            await interaction.followup.send(
                result.joined_msg,
                ephemeral=True,
            )

   

    @discord.ui.button(
        label="Close Scrim",
        style=discord.ButtonStyle.red,
        custom_id="scrim_close",
    )
    async def close(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction,
    ):


        await ctx.defer(ephemeral=True)


        await interaction.response.defer()

        result = await perform_close(
            interaction.guild,
            self.scrim_id,
            interaction.user.id,
        )

        if not result.ok:

            return await interaction.response.send_message(
                result.error,
                ephemeral=True,
            )

        await interaction.edit_original_response(
            embed=result.embed,
            view=result.view,
        )


    @discord.ui.button(
        label="Null Scrim",
        style=discord.ButtonStyle.grey,
        custom_id="scrim_null",
    )
    async def null(
        self,
        button: discord.ui.Button,
        interaction: discord.Interaction,
    ):

        await ctx.defer(ephemeral=True)

        await interaction.response.defer()

        result = await perform_null(
            interaction.guild,
            self.scrim_id,
            interaction.user.id,
        )

        if not result.ok:

            return await interaction.response.send_message(
                result.error,
                ephemeral=True,
            )

        await interaction.edit_original_response(
            embed=result.embed,
            view=result.view,
        )


class Scrims(
    commands.Cog
):

    def __init__(
        self,
        bot,
    ):

        self.bot = bot


    @commands.slash_command(
        name="hostscrim",
        description="Host a ranked or unranked scrim.",
    )
    async def hostscrim(
        self,
        ctx,

        format_type: Option(
            str,
            "Scrim format",
            choices=[
                "FT11 WB2",
                "FT11 WB1",
            ],
        ),

        region: Option(
            str,
            "Server region",
            choices=[
                "NA",
                "EU",
                "OCE",
                "Idk",
            ],
        ),

        teams: Option(
            str,
            "Team format",
            choices=[
                "4v4",
                "5v5",
            ],
        ),

        map_type: Option(
            str,
            "Map type",
            choices=[
                "Glass",
                "No glass",
            ],
        ),

        match_type: Option(
            str,
            "Match type",
            choices=[
                "Ranked",
                "Unranked",
            ],
        ),

        server_link: Option(
            str,
            "Server join link",
        ),

        max_players: Option(
            int,
            "Maximum signup players",
            min_value=2,
            max_value=100,
            default=14,
        ),

        minimum_rank: Option(
            str,
            "Minimum rank",
            required=False,
            default="",
        ),

        max_rank: Option(
            str,
            "Maximum rank",
            required=False,
            default="",
        ),
    ):


        if not ctx.channel.name.lower().endswith(
            SCRIM_CHANNEL_NAME
        ):

            return await ctx.respond(
                f"❌ Use `/hostscrim` in "
                f"#{SCRIM_CHANNEL_NAME}.",
                ephemeral=True,
            )

        # Acknowledge immediately. MongoDB + message creation
        # below can take longer than Discord's interaction window.
        await ctx.defer(ephemeral=True)


        scrim_id = await db.create_scrim(
            host_id=ctx.author.id,
            message_id=0,
            thread_id=None,
            channel_id=ctx.channel.id,
            format_type=format_type,
            region=region,
            teams=teams,
            map_type=map_type,
            match_type=match_type,
            server_link=server_link,
            minimum_rank=minimum_rank,
            max_rank=max_rank,
            max_players=max_players,
            joined_players="[]",
            status="open",
        )


        scrim = await db.get_scrim(
            scrim_id
        )



        embed = build_scrim_embed(
            scrim,
            ctx.author,
        )

        view = ScrimView(
            scrim_id,
            server_link,
        )


        message = await ctx.channel.send(
            embed=embed,
            view=view,
        )


        await db.update_scrim(
            scrim_id,
            message_id=message.id,
        )


        try:
            await ctx.respond(
                f"✅ Scrim created (ID: {scrim_id}).",
                ephemeral=True,
            )
        except discord.HTTPException:
            pass


    @commands.slash_command(
        name="joinscrim",
        description="Join a scrim by its ID.",
    )
    async def joinscrim(
        self,
        ctx,
        scrim_id: Option(
            int,
            "The Scrim ID shown in the scrim post's footer",
        ),
    ):

        if not ctx.channel.name.lower().endswith(
            BOT_CMDS_CHANNEL_NAME
        ):

            return await ctx.respond(
                f"❌ Use `/joinscrim` in "
                f"#{BOT_CMDS_CHANNEL_NAME}.",
                ephemeral=True,
            )

        result = await perform_join(
            ctx.guild,
            scrim_id,
            ctx.author.id,
        )

        if not result.ok:

            return await ctx.respond(
                result.error,
                ephemeral=True,
            )

        await update_scrim_message(
            self.bot,
            result.scrim,
            result.embed,
            result.view,
        )

        if result.announcement:

            scrim_channel = self.bot.get_channel(
                result.scrim["channel_id"]
            )

            if scrim_channel is not None:

                await scrim_channel.send(
                    content=result.announcement
                )

            await ctx.respond(
                "✅ You joined — the scrim just filled up, "
                "check the scrim post!",
                ephemeral=True,
            )

        else:

            await ctx.respond(
                result.joined_msg or "✅ Joined the scrim.",
                ephemeral=True,
            )

    @commands.slash_command(
        name="closescrim",
        description="Close a scrim by its ID.",
    )
    async def closescrim(
        self,
        ctx,
        scrim_id: Option(
            int,
            "The Scrim ID shown in the scrim post's footer",
        ),
    ):

        if not ctx.channel.name.lower().endswith(
            BOT_CMDS_CHANNEL_NAME
        ):

            return await ctx.respond(
                f"❌ Use `/closescrim` in "
                f"#{BOT_CMDS_CHANNEL_NAME}.",
                ephemeral=True,
            )

        result = await perform_close(
            ctx.guild,
            scrim_id,
            ctx.author.id,
        )

        if not result.ok:

            return await ctx.respond(
                result.error,
                ephemeral=True,
            )

        await update_scrim_message(
            self.bot,
            result.scrim,
            result.embed,
            result.view,
        )

        await ctx.respond(
            "✅ Scrim closed.",
            ephemeral=True,
        )


    @commands.slash_command(
        name="nullscrim",
        description="Null (reset) a scrim by its ID.",
    )
    async def nullscrim(
        self,
        ctx,
        scrim_id: Option(
            int,
            "The Scrim ID shown in the scrim post's footer",
        ),
    ):

        if not ctx.channel.name.lower().endswith(
            BOT_CMDS_CHANNEL_NAME
        ):

            return await ctx.respond(
                f"❌ Use `/nullscrim` in "
                f"#{BOT_CMDS_CHANNEL_NAME}.",
                ephemeral=True,
            )

        result = await perform_null(
            ctx.guild,
            scrim_id,
            ctx.author.id,
        )

        if not result.ok:

            return await ctx.respond(
                result.error,
                ephemeral=True,
            )

        await update_scrim_message(
            self.bot,
            result.scrim,
            result.embed,
            result.view,
        )

        await ctx.respond(
            "✅ Scrim nulled — reset to open.",
            ephemeral=True,
        )



async def register_persistent_views(
    bot,
):

    rows = await db.get_open_scrims()

    for row in rows:

        try:

            bot.add_view(
                ScrimView(
                    row["scrim_id"],
                    row.get("server_link"),
                )
            )

        except Exception as e:

            print(
                "⚠️ Failed to restore scrim "
                f"{row['scrim_id']}: "
                f"{type(e).__name__}: {e}"
            )


def setup(bot):

    bot.add_cog(
        Scrims(bot)
    )
