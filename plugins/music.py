import logging
import hikari
import lightbulb
import miru
import lavalink_rs

from miru.ext import nav
from constants import *
from lavalink_rs.model import events
from lavalink_rs.model.search import SearchEngines
from lavalink_rs.model.track import TrackLoadType
from lavalink_voice import LavalinkVoice

plugin = lightbulb.Plugin("music", include_datastore=True)
plugin.add_checks(lightbulb.guild_only)

class EventHandler(lavalink_rs.EventHandler):
    """Handles events from Lavalink including updating the player view."""
    
    async def ready(self, client: lavalink_rs.LavalinkClient, session_id: str, event: events.Ready) -> None:
        del client, session_id, event 
    
    async def track_start(self, client: lavalink_rs.LavalinkClient, session_id: str, event: events.TrackStart) -> None: 
        del session_id

        ids = plugin.bot.d.ids[event.guild_id.inner]

        try:
            await plugin.bot.rest.delete_message(ids[0], ids[1])
        except:
            pass

        player_view = PlayerView(timeout=None)
        res = await plugin.bot.rest.create_message(ids[0], components=player_view)
        ids[1] = res.id

        await player_view.start(res)
        await player_view.wait()

    async def track_end(self, client: lavalink_rs.LavalinkClient, session_id: str, event: events.TrackEnd) -> None: 
        del session_id

class PlayerView(miru.View):
    """A view for music controls."""

    @miru.button(emoji=EMOJI_STOP, style=hikari.ButtonStyle.DANGER)
    async def stop_button(self, button: miru.Button, ctx: miru.ViewContext) -> None:
        await ctx.bot.voice.connections.get(ctx.guild_id).disconnect()
        ids = plugin.bot.d.ids[ctx.guild_id]
        await plugin.bot.rest.delete_message(ids[0], ids[1])

    @miru.button(emoji=EMOJI_PAUSE, style=hikari.ButtonStyle.PRIMARY)
    async def pause_play_button(self, button: miru.Button, ctx: miru.ViewContext) -> None:

        voice = ctx.bot.voice.connections.get(ctx.guild_id)
        
        if str(button.emoji) == EMOJI_PAUSE:
            await voice.player.set_pause(True)
            button.emoji = EMOJI_PLAY
        else:
            await voice.player.set_pause(False)
            button.emoji = EMOJI_PAUSE

        await ctx.edit_response(components=self)

    @miru.button(emoji=EMOJI_NEXT, style=hikari.ButtonStyle.SUCCESS)
    async def next_button(self, button: miru.Button, ctx: miru.ViewContext) -> None:
        voice = ctx.bot.voice.connections.get(ctx.guild_id)
        queue = await voice.player.get_queue().get_queue()

        if len(queue) == 0:
            await ctx.respond(embed=_embed("There is nothing to skip to!"), flags=hikari.MessageFlag.EPHEMERAL)
        else:
            voice.player.skip()

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

    channel_id = None

    if not channel_id:
        voice_state = ctx.bot.cache.get_voice_state(ctx.guild_id, ctx.author.id)
        
        if not voice_state or not voice_state.channel_id:
            await ctx.respond(embed=_embed("Join a voice channel!"), flags=hikari.MessageFlag.EPHEMERAL)
            return
        
        channel_id = voice_state.channel_id

    voice = ctx.bot.voice.connections.get(ctx.guild_id)

    if not voice:
        await LavalinkVoice.connect(
            ctx.guild_id,
            channel_id,
            ctx.bot,
            ctx.bot.d.lavalink,
            (ctx.channel_id, ctx.bot.rest),
        )

    return channel_id

@plugin.listener(hikari.ShardReadyEvent)
async def start_lavalink(event: hikari.ShardReadyEvent) -> None:

    node = lavalink_rs.NodeBuilder(
        "0.0.0.0:2333",
        False,
        "youshallnotpass",
        event.my_user.id
    )

    lavalink_client = await lavalink_rs.LavalinkClient.new(
        EventHandler(),
        [node],
        lavalink_rs.NodeDistributionStrategy.sharded()
    )

    plugin.bot.d.lavalink = lavalink_client
    plugin.bot.d.ids = {}

@plugin.command()
@lightbulb.option("query", "Song query", str, required=True)
@lightbulb.command("play", "Play a song", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def play(ctx: lightbulb.SlashContext, query: str) -> None:
    voice = ctx.bot.voice.connections.get(ctx.guild_id)

    if ctx.guild_id not in plugin.bot.d.ids:
        plugin.bot.d.ids[ctx.guild_id] = [ctx.channel_id, None]

    if not voice:
        if await _join(ctx):
            voice = ctx.bot.voice.connections.get(ctx.guild_id) 

    assert isinstance(voice, LavalinkVoice)
    player_ctx = voice.player

    query = SearchEngines.soundcloud(query)

    try:
        tracks = await ctx.bot.d.lavalink.load_tracks(ctx.guild_id, query)
        loaded_tracks = tracks.data

        if tracks.load_type == TrackLoadType.Search:
            assert isinstance(loaded_tracks, list)
            player_ctx.queue(loaded_tracks[0])
            await ctx.respond(embed=_embed(f"Added [{loaded_tracks[0].info.title}]({loaded_tracks[0].info.uri}) to the queue!"), flags=hikari.MessageFlag.EPHEMERAL)
        else:
            await ctx.respond(embed=_embed("No results for this query found!"), flags=hikari.MessageFlag.EPHEMERAL)
    except Exception as e:
        logging.error(f"Error loading tracks: {e}")
        await ctx.respond("An error occurred while trying to load tracks.")

@plugin.command()
@lightbulb.command("queue", "Displays the queue")
@lightbulb.implements(lightbulb.SlashCommand)
async def queue(ctx: lightbulb.SlashContext) -> None:

    voice = ctx.bot.voice.connections.get(ctx.guild_id)

    if not voice:
        await ctx.respond(embed=_embed("Nothing is in the queue!"), flags=hikari.MessageFlag.EPHEMERAL)
        return 
    
    queue = await voice.player.get_queue().get_queue()
    player = await voice.player.get_player()
    current_data = player.track.info

    embed = _embed()
    pages = []
    embed.description += f"**Now Playing**: [{current_data.title}]({current_data.uri}) | `{_format_duration(current_data.length)}\n`"
    embed.description += "\n**Up Next:**"
    
    for i, song in enumerate(queue):

        if i % 11 == 0 and i != 0:
            pages += [embed]
            embed = _embed()

        data = song.track.info
        embed.description += f"\n`{i+1}.` [{data.title}]({data.uri}) | `{_format_duration(data.length)}`"
            
    if not pages or pages[-1] != embed:
        pages += [embed]

    buttons = [nav.PrevButton(), nav.IndicatorButton(), nav.NextButton()]
    
    navigator = nav.NavigatorView(pages=pages,buttons=buttons)
    await navigator.send(ctx.interaction, ephemeral=True)
    
def load(bot: lightbulb.BotApp) -> None:
    bot.add_plugin(plugin)