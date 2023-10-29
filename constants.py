import os
import dotenv

dotenv.load_dotenv()

EMOJI_STOP = "<:stop_button:1155304239309004871>"
EMOJI_PAUSE = "<:pause_button:1155304237362843668>"
EMOJI_PLAY = "<:play_button:1155299535342555217>"
EMOJI_NEXT = "<:next_button:1155306732344578111>"
EMBED_COLOR = "0x9ACD32"
BOT_TOKEN = os.environ.get("BOT_TOKEN")