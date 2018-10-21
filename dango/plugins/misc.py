import asyncio
import collections
import io
import json
import random
import re

import aiohttp
import dango
from dango import dcog
import discord
from discord.ext.commands import command
from discord.ext.commands import clean_content
from discord.ext.commands import errors
from discord.ext.commands import group
from numpy import random
import random as pyrandom
import unicodedata
import urllib.parse

from .common import utils
from .common import converters
from .common.utils import resolve_color
from .common.paginator import ListPaginator

FULLWIDTH_OFFSET = 65248
ZALGO_CHARS = [chr(x) for x in range(768, 879)]

EIGHT_BALL_RESPS = {
    "yes": [
        "It is certain",
        "It is decidedly so",
        "Without a doubt",
        "Yes, definitely",
        "You may rely on it",
        "As I see it, yes",
        "Most likely",
        "Outlook good",
        "Yes",
        "Signs point to yes",
        "💯",
        "👍"
    ],
    "no": [
        "Don't count on it",
        "My reply is no",
        "My sources say no",
        "Outlook not so good",
        "Very doubtful",
        "lol",
        "rofl",
        "Are you joking?",
        "👎"
    ],
    "maybe": [
        "Reply hazy try again",
        "Ask again later",
        "Better not tell you now",
        "Cannot predict now"
    ]
}

FakeEmoji = collections.namedtuple('FakeEmoji', 'name id animated')
FakeEmoji.url = discord.Emoji.url


def better_int(val):
    return int(val, 0)


def idc_emoji_or_just_string(val):
    match = re.match(r'<(?P<animated>a)?:(?P<name>[a-zA-Z0-9_]+):(?P<id>[0-9]+)>$', val)
    if match:
        return FakeEmoji(match.group("name"), match.group("id"), bool(match.group("animated")))
    return FakeEmoji(val.replace(':', ''), None, False)  # guess it's not animated

def idc_emoji(val):
    match = re.match(r'<(?P<animated>a)?:(?P<name>[a-zA-Z0-9_]+):(?P<id>[0-9]+)>$', val)
    if not match:
        return val
    return FakeEmoji(match.group("name"), match.group("id"), bool(match.group("animated")))

@dcog()
class Emoji:
    def __init__(self, config):
        pass

    @command()
    async def guild_emojis(self, ctx):
        """List emojis on this server.

        Note: will only list emoji this bot can send. Some twitch integration emoji
        (that do not require colons) cannot be sent by bots.
        """
        emojis = [
            "{0} - \{0}".format(emoji) for emoji in ctx.guild.emojis if emoji.require_colons
        ]

        if emojis:
            await ListPaginator.from_lines(ctx, emojis, "Guild Emojis").send()
        else:
            await ctx.message.add_reaction(":discordok:293495010719170560")

    @command(pass_context=True)
    async def find_emojis(self, ctx, *search_emojis: idc_emoji_or_just_string):
        """Find all emoji sharing the same name and the servers they are from.

        Note: will only list emoji this bot can send. Some twitch integration emoji
        (that do not require colons) cannot be sent by bots.
        """
        found_emojis = [
            emoji for emoji in ctx.bot.emojis for search_emoji in search_emojis
            if emoji.name.lower() == search_emoji.name.lower() and emoji.require_colons
        ]
        if found_emojis:
            by_guild = collections.defaultdict(list)
            for e in found_emojis:
                by_guild[e.guild].append(e)

            lines = ("{}: {}".format(g, "".join(map(str,emojis))) for g, emojis in by_guild.items())
            await ListPaginator.from_lines(ctx, lines, "Found Emojis").send()
        else:
            await ctx.message.add_reaction(":discordok:293495010719170560")

    @command(pass_context=True)
    async def search_emojis(self, ctx, *query_strings: str):
        """Find all emoji containing query string.

        Note: will only list emoji this bot can send. Some twitch integration emoji
        (that do not require colons) cannot be sent by bots.
        """
        found_emojis = [
            emoji for emoji in ctx.bot.emojis for query_string in query_strings
            if query_string.lower() in emoji.name.lower() and emoji.require_colons
        ]
        if found_emojis:
            by_guild = collections.defaultdict(list)
            for e in found_emojis:
                by_guild[e.guild].append(e)

            lines = ("{}: {}".format(g, "".join(map(str,emojis))) for g, emojis in by_guild.items())
            await ListPaginator.from_lines(ctx, lines, "Found Emojis").send()

        else:
            await ctx.message.add_reaction(":discordok:293495010719170560")

    @command()
    async def nitro(self, ctx, *, rest):
        """Send a random emoji with this name.

        Note: will only use emoji this bot can send. Some twitch integration emoji
        (that do not require colons) cannot be sent by bots.
        """
        rest = rest.lower()
        found_emojis = [emoji for emoji in ctx.bot.emojis
                        if emoji.name.lower() == rest and emoji.require_colons]
        if found_emojis:
            await ctx.send(str(random.choice(found_emojis)))
        else:
            await ctx.message.add_reaction(":discordok:293495010719170560")

    @command()
    async def random_emoji(self, ctx):
        """Show a random emoji this bot can use."""
        try:
            await ctx.send(str(random.choice(
                [emoji for emoji in ctx.bot.emojis if emoji.require_colons])))
        except ValueError:
            await ctx.message.add_reaction(":discordok:293495010719170560")

    @command()
    async def bigmoji(self, ctx, emoji: idc_emoji):
        """Link to the full sized image for an emoji."""
        if isinstance(emoji, FakeEmoji):
            await ctx.send(emoji.url)
        else:
            await ctx.send(utils.emoji_url(emoji))

    @command(aliases=['google', 'lmgtfy'])
    async def g(self, ctx, *, query):
        await ctx.send("{}{}".format(
            random.choice(["https://google.com/search?q=", "https://lmgtfy.com/?q="],
                p=[0.99, 0.01]),
            urllib.parse.quote_plus(query)))


@dcog()
class Misc:

    def __init__(self, config):
        self.eightballqs = {}

    @command()
    async def hunger_games(self, ctx, *members: converters.UserMemberConverter):
        """json to use with http://orteil.dashnet.org/murdergames/."""
        perks = ["no perk", "leader", "peaceful", "sociopath", "kind", "unstable", "bulky",
                 "meek", "naive", "devious", "seductive", "suicidal", "cute", "annoying",
                 "scrappy", "survivalist", "rich", "inventor", "goth", "lunatic",]
        weapons = ["no item", "big stick", "pitchfork", "sword", "axe", "handgun", "shotgun",
                   "grenade", "slingshot", "bow", "flamethrower", "lasergun", "magic wand",
                   "ancient scepter", "pet wolf", "pet tiger", "pet turtle", "wish ring",]
        teams = []
        players = []

        if not members:
            t = ctx.bot.get_cog("Tracking")
            if t:
                ms = ctx.guild.members.copy()
                last_seen = await t.bulk_last_seen(ms)
                members = [
                    m for
                    m, _ in
                    sorted(
                        zip(ms, last_seen),
                        key=lambda x: x[1].server_last_spoke
                    )[-100:]]
            else:
                members = ctx.guild.members[-100:]

        for idx, m in enumerate(members):
          teams.append({"name": m.display_name})
          players.append({
            "name": m.display_name,
            "g": pyrandom.choice([0,1,2]),
            "pic": m.avatar_url,
            "team": m.display_name,
            "perks": [pyrandom.choice(perks), pyrandom.choice(perks), pyrandom.choice(weapons)],
          })

        pbin_url = await dango.privatebin.upload(json.dumps({
            "teams": teams,
            "chars": players,
        }))
        waaai_url = await dango.waaai.shorten(
                        pbin_url, ctx.bot.waaai_api_key())
        await ctx.send("Use {} at http://orteil.dashnet.org/murdergames/".format(
            waaai_url))


    @command(aliases=['fw', 'fullwidth', 'ａｅｓｔｈｅｔｉｃ'])
    async def aesthetic(self, ctx, *, msg="aesthetic"):
        """ａｅｓｔｈｅｔｉｃ."""
        await ctx.send("".join(map(
            lambda c: chr(ord(c) + FULLWIDTH_OFFSET) if (ord(c) >= 0x21 and ord(c) <= 0x7E) else c,
            msg)).replace(" ", chr(0x3000)))

    @command(pass_context=True, aliases=["\N{CLAPPING HANDS SIGN}"])
    async def clap(self, ctx, *, msg: clean_content()):
        """\N{CLAPPING HANDS SIGN}"""
        await ctx.send(" \N{CLAPPING HANDS SIGN} ".join(msg.split()))

    @command(pass_context=True)
    async def say(self, ctx, *, msg: clean_content()):
        """Make the bot say something.

        Prevents bot triggering and mentioning other users.
        """
        await ctx.send("\u200b" + msg)

    @command()
    async def star(self, ctx, *, msg):
        """Create a star out of a string 1-25 characters long."""
        if (len(msg) > 25):
            raise errors.BadArgument("String must be less than 26 characters")
        elif (len(msg) == 0):
            raise errors.BadArgument("String must be at least 1 character")

        str = '```\n'

        mid = len(msg) - 1

        for i in range(len(msg) * 2 - 1):
            if (mid == i):
                str += msg[::-1] + msg[1:] + "\n"
            else:
                let = abs(mid - i)
                str += " " * (mid - let)
                str += msg[let]
                str += " " * (let - 1)
                str += msg[let]
                str += " " * (let - 1)
                str += msg[let]
                str += "\n"

        str += "```"
        await ctx.send(str)

    @command()
    async def roll(self, ctx, *, num: int=100):
        """Random number from 0 to num."""
        if num <= 0:
            raise errors.BadArgument("Try a number greater than 0.")
        await ctx.send("{0}".format(pyrandom.randint(0, num)))
    
    @group(invoke_without_command=True)
    async def charinfo(self, ctx, *, chars: str):
        """Show information about a unicode character."""
        await self._charinfo(ctx, *[ord(char) for char in chars])

    @charinfo.command(name="num", require_var_positional=True)
    async def charinfo_num(self, ctx, *chars: better_int):
        """Show information about unicode characters by number lookup."""
        await self._charinfo(ctx, *chars)

    async def _charinfo(self, ctx, *chars):
        await ctx.send("\n".join("`{}`: {} - {} - <{}>".format(
            hex(cpt), unicodedata.name(chr(cpt), "unknown"), chr(cpt),
            "http://www.fileformat.info/info/unicode/char/" + hex(cpt)[2:]) for cpt in chars))

    @command()
    async def mcavatar(self, ctx, minecraftusername: str):
        """Display a minecraft avatar."""
        await ctx.send("https://visage.surgeplay.com/full/512/{}.png".format(minecraftusername))

    @staticmethod
    def make_pil_color_preview(*colors: int):
        from PIL import Image, ImageDraw
        from io import BytesIO

        imgwidth = 128 * len(colors)

        img = Image.new('RGBA', (imgwidth, 128), colors[0])
        draw = ImageDraw.Draw(img)

        for i in range(1, len(colors)):
            draw.rectangle((128 * i, 0, 128 * (i + 1), 128), colors[i])

        buff = BytesIO()

        img.save(buff, 'png')

        buff.seek(0)

        return buff

    @command(aliases=['showcolour'], require_var_positional=True)
    async def showcolor(self, ctx, *color: resolve_color):
        """Show a color."""
        color_image = await ctx.bot.loop.run_in_executor(None, self.make_pil_color_preview, *color)

        await ctx.send(file=discord.File(color_image, filename="showcolor.png"))

    @command(name="8ball")
    async def eightball(self, ctx, *, question: str):
        """Ask the magic 8 ball your questions."""
        question = re.sub(r'[.,\/#!$%\^?&\*;:{}=\-_`~()]',
                          "", question.lower())
        if question in self.eightballqs:
            result = self.eightballqs[question]
        else:
            # Traditional Magic 8 ball chances.
            result = str(random.choice(
                ["yes", "no", "maybe"], p=[.5, .25, .25]))
            if result != "maybe":
                self.eightballqs[question] = result

        await ctx.send(random.choice(EIGHT_BALL_RESPS[result]))

    @command(require_var_positional=True)
    async def choose(self, ctx, *values: clean_content()):
        """Randomly chooses one of the options."""
        await ctx.send(random.choice(values))

    @command()
    async def zalgo(self, ctx, *, text):
        """I̤̠̬T̢̐͟ Ì̦̮Sͣͣ͠ C̋͢͠Ơ̸̂M̥̟̂I̟̾̐N̊̔Ǵ͞
        F͉̃ͅO̠̳ͭR̾̄̉ Y͚̜͡O̮̮̩Ù͚͎."""
        await ctx.send("".join(
            c + "".join(
                random.choice(ZALGO_CHARS) for _
                in range(pyrandom.randint(2, 7) * c.isalnum()))
            for c in text
        ))

    @command()
    async def msgsource(self, ctx, *, msg_id: int):
        """Show source for a message."""
        try:
            msg = await ctx.get_message(msg_id)
        except discord.NotFound:
            raise errors.BadArgument("Message not found")
        else:
            await ctx.send("```{}```".format(utils.clean_triple_backtick(msg.content)))

    @command()
    async def msgraw(self, ctx, *, msg_id: int):
        """Show raw JSON for a message."""
        raw = await ctx.bot.http.get_message(ctx.channel.id, msg_id)

        await ctx.send("```json\n{}```".format(
            utils.clean_triple_backtick(json.dumps(raw, indent=2, ensure_ascii=False))))

    @command()
    async def nostalgia(self, ctx, channel: discord.TextChannel=None, date: utils.convert_date=None):
        """Jump to a specific date.

        The format of the date must be either YYYY-MM-DD or YYYY/MM/DD.

        If no date is provided, jumps to the first message in this channel.
        """
        if channel is None:
            channel = ctx.message.channel

        if date is None:
            date = channel

        async for m in channel.history(after=date, limit=1):
            await ctx.send(utils.jump_url(m))
