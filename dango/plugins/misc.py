import asyncio
import collections
import io
import json
import random
import re
import typing

import aiohttp
import dango
from dango import dcog, Cog
import discord
from discord import PartialEmoji
from discord.ext.commands import command
from discord.ext.commands import clean_content
from discord.ext.commands import errors
from discord.ext.commands import group
from numpy import random
import random as pyrandom
import unicodedata
import urllib.parse
import yarl

from .common import utils
from .common import converters
from .common.utils import resolve_color
from .common.paginator import ListPaginator

FULLWIDTH_OFFSET = 65248
FLAG_OFFSET = 127397
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

def better_int(val):
    return int(val, 0)

def number_emoji(num):
    if 0 <= num <= 9:
        return "%d\N{COMBINING ENCLOSING KEYCAP}" % num
    return "\N{KEYCAP TEN}"


def emoji_number(string):
    if string[0].isdigit():
        return int(string[0])
    return 10


def is_number_emoji(string):
    return string[0].isdigit() or string == "\N{KEYCAP TEN}"


def joinand(arr):
    if len(arr) == 2:
        return "%s and %s" % (arr[0], arr[1])
    return "%s, and %s" % (
        ", ".join(arr[:-1]), arr[-1])


def message_embed(msg):
    embed = discord.Embed(timestamp=msg.created_at)
    if msg.author.nick:
        author_name = "{} • {}".format(msg.author.display_name, msg.author)
    else:
        author_name = msg.author
    embed.set_author(name=author_name, icon_url=msg.author.avatar)
    embed.set_footer(text="#{} in {}".format(msg.channel, msg.guild))
    embed.color = hash(str(msg.author.id)) % (1 << 24)
    return embed


@dcog()
class Misc(Cog):

    def __init__(self, config):
        self.eightballqs = {}

    @command(require_var_positional=True)
    async def poll(self, ctx, *options: clean_content):
        """Run a poll with up to 11 options.

        Poll ends 30 seconds after the last response.
        """
        if len(options) > 11:
            raise errors.BadArgument("No more than 11 options")

        e = discord.Embed(title="Vote now!", description="\n".join(
                "%s %s" % (number_emoji(idx), text)
                for idx, text in enumerate(options)
            ))
        e.set_footer(text="Voting ends 30 seconds after the last response!")

        msg = await ctx.send(embed=e)
        for i in range(len(options)):
            await msg.add_reaction(number_emoji(i))

        while True:
            try:
                resp = await ctx.bot.wait_for(
                    "raw_reaction_add", timeout=30,
                    check=lambda r: r.message_id == msg.id and
                                    is_number_emoji(r.emoji.name))
            except asyncio.TimeoutError:
                break

        msg = await ctx.fetch_message(msg.id)

        max_val = 0
        results = []
        for reaction in msg.reactions:
            if isinstance(reaction.emoji, str) and is_number_emoji(reaction.emoji):
                idx = emoji_number(reaction.emoji)
                if idx >= len(options):
                    continue
                if reaction.count > max_val:
                    max_val = reaction.count
                    results = [idx]
                elif reaction.count == max_val:
                    results.append(idx)

        if max_val == 1:
            await ctx.send("No one voted...")
        elif len(results) > 1:
            final = "all" if len(results) > 2 else "both"
            await ctx.send("Tie! %s %s won!" % (
                joinand([options[idx] for idx in results]),
                final))
        else:
            await ctx.send("The best choice is clearly %s" % options[results[0]])

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
            "pic": str(m.avatar),
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

    @command(aliases=["🇫 🇱 🇦 🇬 🇮 🇫 🇾", "fl"])
    async def flagify(self, ctx, *, msg="flagify"):
        """🇫 🇱 🇦 🇬 🇮 🇫 🇾."""
        await ctx.send("".join(
            map(
                lambda c: number_emoji(int(c)) if (ord(c) >= 0x30 and ord(c) <= 0x39) else c,
                "".join(map(
                    lambda c: chr(ord(c) + FLAG_OFFSET) + ("\u200b" if len(msg) >= 28 else " ") if (ord(c) >= 0x41 and ord(c) <= 0x5a) else c,
                    msg.upper().replace(" ", "  "))))))

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
        color_image = await asyncio.get_running_loop().run_in_executor(None, self.make_pil_color_preview, *color)

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

    @command(aliases=["msgquote"])
    async def quote(self, ctx, msg: converters.MessageConverter):
        """Quote a message.

        message can be given in jump url format, as message id,
        or as channel-message
        """
        embed = message_embed(msg)
        description = msg.content
        if msg.attachments:
            description += "\n" + "".join(
                "\n[{0.filename}]({0.url})".format(a) for a in msg.attachments
                )
        description += "\n\n[Jump to message]({})".format(msg.jump_url)
        if msg.embeds:
            description += " • Message has an embed"
        embed.description = description
        await ctx.send(embed=embed)

    @command(aliases=['msgsrc', 'msgtext'])
    async def msgsource(self, ctx, msg: converters.MessageConverter):
        """Show source for a message.

        message can be given in jump url format, as message id,
        or as channel-message
        """
        embed = message_embed(msg)
        embed.description = "```{}```".format(
            utils.clean_triple_backtick(utils.escape_invis_chars(msg.content)))
        await ctx.send(embed=embed)

    @command(aliases=['msgjson'])
    async def msgraw(self, ctx, msg: converters.MessageIdConverter):
        """Show raw JSON for a message.

        message can be given in jump url format, as message id,
        or as channel-message"""
        channel, msg_id = msg
        try:
            raw = await ctx.bot.http.get_message(channel.id, msg_id)
        except discord.NotFound:
            raise errors.BadArgument("Message {0} not found in channel {1.mention}".format(msg_id, channel))

        await ctx.send("```json\n{}```".format(
            utils.clean_triple_backtick(utils.escape_invis_chars(json.dumps(
                raw, indent=2, ensure_ascii=False, sort_keys=True)))))

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

    @command(aliases=['google', 'lmgtfy'])
    async def g(self, ctx, *, query):
        await ctx.send("{}{}".format(
            random.choice(["https://google.com/search?q=", "https://lmgtfy.com/?q="],
                p=[0.99, 0.01]),
            urllib.parse.quote_plus(query)))

    @command(aliases=['udict'])
    async def ud(self, ctx, *, query):
        await ctx.send(yarl.URL("https://www.urbandictionary.com/define.php?term={}".format(query)))

    @command()
    async def countdown(self, ctx, seconds: int=3):
        """3... 2... 1... Go!"""
        if seconds > 10:
            raise errors.BadArgument("No more than 10 seconds, thanks")
        if seconds < 0:
            raise errors.BadArgument("No negative numbers, thanks")
        while seconds:
            await ctx.send("%d..." % seconds)
            await asyncio.sleep(1)
            seconds -= 1
        await ctx.send("Go!")
