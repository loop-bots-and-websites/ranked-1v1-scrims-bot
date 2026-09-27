import discord
from discord.ext import commands
from discord import Option
from datetime import timedelta
import db


def is_staff():
    async def predicate(ctx: discord.ApplicationContext):
        return ctx.author.guild_permissions.moderate_members or ctx.author.guild_permissions.administrator
    return commands.check(predicate)


class Moderation(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.slash_command(name="kick", description="Kick a member from the server.")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: Option(discord.Member, "Member to kick"), reason: Option(str, "Reason", default="No reason provided")):
        await member.kick(reason=f"{ctx.author}: {reason}")
        await db.log_mod_action(ctx.guild.id, member.id, ctx.author.id, "kick", reason)
        embed = discord.Embed(title="👢 Member Kicked", color=discord.Color.orange())
        embed.add_field(name="User", value=f"{member.mention} ({member})", inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.respond(embed=embed)

    @commands.slash_command(name="ban", description="Ban a member from the server.")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: Option(discord.Member, "Member to ban"), reason: Option(str, "Reason", default="No reason provided")):
        await member.ban(reason=f"{ctx.author}: {reason}")
        await db.log_mod_action(ctx.guild.id, member.id, ctx.author.id, "ban", reason)
        embed = discord.Embed(title="🔨 Member Banned", color=discord.Color.red())
        embed.add_field(name="User", value=f"{member.mention} ({member})", inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.respond(embed=embed)

    @commands.slash_command(name="unban", description="Unban a user by ID or username#tag.")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: Option(str, "User ID to unban"), reason: Option(str, "Reason", default="No reason provided")):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await ctx.guild.unban(user, reason=f"{ctx.author}: {reason}")
        except (ValueError, discord.NotFound):
            return await ctx.respond("Couldn't find that user ID in the ban list.", ephemeral=True)
        await db.log_mod_action(ctx.guild.id, user.id, ctx.author.id, "unban", reason)
        embed = discord.Embed(title="✅ Member Unbanned", color=discord.Color.green())
        embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
        await ctx.respond(embed=embed)

    @commands.slash_command(name="mute", description="Timeout (mute) a member.")
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx, member: Option(discord.Member, "Member to mute"), minutes: Option(int, "Duration in minutes", min_value=1, max_value=40320, default=60), reason: Option(str, "Reason", default="No reason provided")):
        await member.timeout_for(timedelta(minutes=minutes), reason=f"{ctx.author}: {reason}")
        await db.log_mod_action(ctx.guild.id, member.id, ctx.author.id, "mute", reason)
        embed = discord.Embed(title="🔇 Member Muted", color=discord.Color.orange())
        embed.add_field(name="User", value=f"{member.mention}", inline=False)
        embed.add_field(name="Duration", value=f"{minutes} minutes", inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.respond(embed=embed)

    @commands.slash_command(name="unmute", description="Remove a member's timeout.")
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx, member: Option(discord.Member, "Member to unmute"), reason: Option(str, "Reason", default="No reason provided")):
        await member.remove_timeout(reason=f"{ctx.author}: {reason}")
        await db.log_mod_action(ctx.guild.id, member.id, ctx.author.id, "unmute", reason)
        embed = discord.Embed(title="🔊 Member Unmuted", color=discord.Color.green())
        embed.add_field(name="User", value=f"{member.mention}", inline=False)
        embed.add_field(name="Moderator", value=ctx.author.mention, inline=False)
        await ctx.respond(embed=embed)

    @commands.slash_command(name="unkick", description="Generate an invite to let a previously kicked user back in.")
    @commands.has_permissions(kick_members=True)
    async def unkick(self, ctx, user_id: Option(str, "User ID to invite back"), dm_invite: Option(bool, "DM the invite to them if possible", default=True)):
        invite = await ctx.channel.create_invite(max_uses=1, reason=f"Unkick by {ctx.author}")
        msg = f"Invite generated: {invite.url}"
        if dm_invite:
            try:
                user = await self.bot.fetch_user(int(user_id))
                await user.send(f"You've been invited back: {invite.url}")
                msg += "\nSent via DM."
            except (ValueError, discord.NotFound, discord.Forbidden):
                msg += "\nCouldn't DM them — share the link manually."
        await db.log_mod_action(ctx.guild.id, int(user_id) if user_id.isdigit() else 0, ctx.author.id, "unkick", "invite generated")
        await ctx.respond(msg, ephemeral=True)


def setup(bot):
    bot.add_cog(Moderation(bot))
