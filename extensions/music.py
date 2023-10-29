import logging
import hikari
import lightbulb
import lavasnek_rs
import miru

from miru.ext import nav
from CONSTANTS import *

plugin = lightbulb.Plugin("music", include_datastore=True)
plugin.add_checks(lightbulb.guild_only)

class EventHandler:
    """Handles events from Lavalink including updating the player view."""

    async def track_start(self, _: lavasnek_rs.Lavalink, event: lavasnek_rs.TrackStart) -> None:
        
        ids = plugin.bot.d.ids[event.guild_id]

        try:
            await plugin.bot.rest.delete_message(id[0], id[1])
        except:
            pass

        player_view = PlayerView(timeout=None)

        res = await plugin.bot.rest.create_message(ids[0], components=player_view)
        ids[1] = res.id

        await player_view.start(res)
        await player_view.wait()
        
        logging.info("Track started: %s", event.guild_id)

    async def track_finish(self, _: lavasnek_rs.Lavalink, event: lavasnek_rs.TrackFinish) -> None:
        logging.info("Track finished on guild: %s", event.guild_id)

    async def track_exception(self, lavalink: lavasnek_rs.Lavalink, event: lavasnek_rs.TrackException) -> None:
        logging.warning("Track exception event happened on guild: %d", event.guild_id)

        skip = await lavalink.skip(event.guild_id)
        node = await lavalink.get_guild_node(event.guild_id)

        if not node:
            return

        if skip and not node.queue and not node.now_playing:
            await lavalink.stop(event.guild_id)

class PlayerView(miru.View):
    """A view for music controls."""

    @miru.button(emoji=EMOJI_STOP, style=hikari.ButtonStyle.DANGER)
    async def stop_button(self, button: miru.Button, ctx: miru.ViewContext) -> None:
        ids = plugin.bot.d.ids[ctx.guild_id]

        await plugin.bot.d.lavalink.destroy(ctx.guild_id)
        await plugin.bot.update_voice_state(ctx.guild_id, None)
        await plugin.bot.rest.delete_message(ids[0], ids[1])
        
    @miru.button(emoji=EMOJI_PAUSE, style=hikari.ButtonStyle.PRIMARY)
    async def pause_play_button(self, button: miru.Button, ctx: miru.ViewContext) -> None:
        node = await plugin.bot.d.lavalink.get_guild_node(ctx.guild_id)

        if not node.is_paused:
            await plugin.bot.d.lavalink.pause(ctx.guild_id)
            button.emoji = EMOJI_PLAY
        else:
            await plugin.bot.d.lavalink.resume(ctx.guild_id)
            button.emoji = EMOJI_PAUSE

        await ctx.edit_response(components=self)

    @miru.button(emoji=EMOJI_NEXT, style=hikari.ButtonStyle.SUCCESS)
    async def next_button(self, button: miru.Button, ctx: miru.ViewContext) -> None:
        skip = await plugin.bot.d.lavalink.skip(ctx.guild_id)
        node = await plugin.bot.d.lavalink.get_guild_node(ctx.guild_id)

        if not skip or not node.queue:
            await ctx.respond(embed=_embed("There is nothing to skip to!"), flags=hikari.MessageFlag.EPHEMERAL)

def _embed(description=""):
    return hikari.Embed(description=description, color=EMBED_COLOR)

def _format_duration(milliseconds):
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"

async def _join(ctx: lightbulb.SlashContext) -> None:
    if not (voice_state := ctx.bot.cache.get_voice_state(ctx.guild_id, ctx.author.id)):
        await ctx.respond(embed=_embed("Join a voice channel!"), flags=hikari.MessageFlag.EPHEMERAL)
        return
    
    channel_id = voice_state.channel_id
    
    await plugin.bot.update_voice_state(ctx.guild_id, channel_id)
    connection_info = await plugin.bot.d.lavalink.wait_for_full_connection_info_insert(ctx.guild_id)
    
    await plugin.bot.d.lavalink.create_session(connection_info)

@plugin.listener(hikari.ShardReadyEvent)
async def start_lavalink(event: hikari.ShardReadyEvent) -> None:
    builder = (lavasnek_rs.LavalinkBuilder(event.my_user.id, ""))

    builder.set_start_gateway(False)
    lava_client = await builder.build(EventHandler())

    plugin.bot.d.lavalink = lava_client

    # {guild_id: [channel_id, message_id]}
    plugin.bot.d.ids = {}

@plugin.command()
@lightbulb.option("query", "Song query", str, required=True)
@lightbulb.command("play", "Play a song", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def play(ctx: lightbulb.SlashContext, query: str) -> None:
    con = plugin.bot.d.lavalink.get_guild_gateway_connection_info(ctx.guild_id)

    if ctx.guild_id not in plugin.bot.d.ids:
        plugin.bot.d.ids[ctx.guild_id] = [None, None]
        plugin.bot.d.ids[ctx.guild_id][0] = ctx.channel_id

    if not con:
        await _join(ctx)
    
    result = await plugin.bot.d.lavalink.auto_search_tracks(query)

    if not result.tracks:
        await ctx.respond(embed=_embed("No results for this query found!"), flags=hikari.MessageFlag.EPHEMERAL)
        return
    
    try:
        await plugin.bot.d.lavalink.play(ctx.guild_id, result.tracks[0]).requester(ctx.author.id).queue()
    except lavasnek_rs.NoSessionPresent:
        return

    node = await plugin.bot.d.lavalink.get_guild_node(ctx.guild_id)
    await ctx.respond(embed=_embed(f"Added [{node.queue[-1].track.info.title}]({node.queue[-1].track.info.uri}) to the queue!"), flags=hikari.MessageFlag.EPHEMERAL)

@plugin.command()
@lightbulb.command("queue", "Displays the queue")
@lightbulb.implements(lightbulb.SlashCommand)
async def queue(ctx: lightbulb.SlashContext) -> None:
    node = await plugin.bot.d.lavalink.get_guild_node(ctx.guild_id)

    if not node or not node.queue:
        await ctx.respond(embed=_embed("Nothing is in the queue!"), flags=hikari.MessageFlag.EPHEMERAL)
        return 

    embed = _embed()
    pages = []
    
    for i in range(len(node.queue)):

        song = node.queue[i].track.info
        msg = ""

        if i == 1:
            embed.description += "\n**Up Next:**"

        if i % 11 == 0 and i != 0:
            pages += [embed]
            embed = _embed()

        if i == 0:
            msg = f"**Now Playing**: [{song.title}]({song.uri}) | `{_format_duration(song.length)}\n`"
        else:
            msg = f"\n`{i}.` [{song.title}]({song.uri}) | `{_format_duration(song.length)}`"

        embed.description += msg
            
    if not pages or pages[-1] != embed:
        pages += [embed]

    buttons = [nav.PrevButton(), nav.IndicatorButton(), nav.NextButton()]
    
    navigator = nav.NavigatorView(pages=pages,buttons=buttons)
    await navigator.send(ctx.interaction, ephemeral=True)
    
@plugin.listener(hikari.VoiceStateUpdateEvent)
async def voice_state_update(event: hikari.VoiceStateUpdateEvent) -> None:
    plugin.bot.d.lavalink.raw_handle_event_voice_state_update(
        event.state.guild_id,
        event.state.user_id,
        event.state.session_id,
        event.state.channel_id,
    )

@plugin.listener(hikari.VoiceServerUpdateEvent)
async def voice_server_update(event: hikari.VoiceServerUpdateEvent) -> None:
    await plugin.bot.d.lavalink.raw_handle_event_voice_server_update(event.guild_id, event.endpoint, event.token)
    
def load(bot: lightbulb.BotApp) -> None:
    bot.add_plugin(plugin)