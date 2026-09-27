import os
import asyncio

import discord
from discord.ext import commands
from dotenv import load_dotenv

import db


load_dotenv()

TEST_GUILD_ID = 1544447674516766793

intents = discord.Intents.default()
intents.members = True
intents.message_content = True


COGS = [
    "cogs.moderation",
    "cogs.ranked",
    "cogs.scrims",
]


class ManagementBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            auto_sync_commands=False,
        )


bot = ManagementBot()


async def main():
    print("🔥 BOT.PY STARTED 🔥")

    # -------------------------
    # MongoDB
    # -------------------------
    print("Connecting to MongoDB...")
    await db.init_db()
    print("MongoDB initialization complete.")

    # -------------------------
    # Load Cogs
    # -------------------------
    print("\n=== LOADING COGS ===")

    for extension in COGS:
        try:
            bot.load_extension(extension)
            print(f"✅ Loaded: {extension}")
        except Exception as e:
            print(f"❌ FAILED TO LOAD: {extension}")
            print(f"{type(e).__name__}: {e}")
            raise
          
    print("\n=== REGISTERED APPLICATION COMMANDS ===")

    for command in bot.application_commands:
        print(f" - /{command.name}")


    token = os.getenv("DISCORD_TOKEN")

    if not token:
        raise RuntimeError(
            "DISCORD_TOKEN is missing. Put it in /home/container/.env"
        )


    print("\n=== STARTING DISCORD BOT ===")

    await bot.start(token)


@bot.event
async def on_ready():
    print(f"\nLogged in as {bot.user} ({bot.user.id})")
    print(f"Servers: {len(bot.guilds)}")

    print("\n=== SYNCING COMMANDS ===")

    try:
        await bot.sync_commands(
            guild_ids=[TEST_GUILD_ID],
            force=True,
        )

        print(
            f"✅ Commands synced to test guild: "
            f"{TEST_GUILD_ID}"
        )

    except Exception as e:
        print(
            f"❌ COMMAND SYNC ERROR: "
            f"{type(e).__name__}: {e}"
        )


    try:
        from cogs.ranked import (
            register_persistent_views as register_ranked_views
        )
        from cogs.scrims import (
            register_persistent_views as register_scrim_views
        )

        await register_ranked_views(bot)
        await register_scrim_views(bot)

        from cogs.ranked import update_queue_panel

        if bot.guilds:
            await update_queue_panel(bot.guilds[0])

        print("✅ Persistent views restored.")

    except Exception as e:
        print(
            f"⚠️ Persistent view restore warning: "
            f"{type(e).__name__}: {e}"
        )

if __name__ == "__main__":
    asyncio.run(main())
