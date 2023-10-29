import lightbulb
import miru
import hikari

from hikari import Intents
from constants import *



INTENTS = Intents.ALL

bot = lightbulb.BotApp(
    BOT_TOKEN,
    intents=INTENTS,
    banner=None,
)

miru.install(bot)

bot.load_extensions_from("./extensions/")

@bot.command
@lightbulb.command("ping", "The bot's ping.", ephemeral=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def ping(ctx: lightbulb.SlashContext) -> None:
    await ctx.respond(f"> Pong! Latency: {bot.heartbeat_latency * 1000:.2f}ms.")
    await ctx.respond(embed=hikari.Embed(description=f"**Pong!**\n`Latency:` {bot.heartbeat_latency * 1000:.2f}ms.", color=EMBED_COLOR), flags=hikari.MessageFlag.EPHEMERAL)
        

if __name__ == "__main__":
    import uvloop
    uvloop.install()
    bot.run()