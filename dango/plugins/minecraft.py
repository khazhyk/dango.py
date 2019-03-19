import base64
import io
import collections
import os
import socket

import aiohttp
from dango import dcog, Cog
import discord
from discord.ext.commands import command
from discord.ext.commands import errors
import mcstatus
from lru import LRU

MC_COLOR_CODE = "§"
MCColor = collections.namedtuple(
    "MCColor", "code name id foreground background")
COLORS = [
    MCColor("0", "Black", "black", "000000", "000000",),
    MCColor("1", "Dark Blue", "dark_blue", "0000AA", "00002A",),
    MCColor("2", "Dark Green", "dark_green", "00AA00", "002A00",),
    MCColor("3", "Dark Aqua", "dark_aqua", "00AAAA", "002A2A",),
    MCColor("4", "Dark Red", "dark_red", "AA0000", "2A0000",),
    MCColor("5", "Dark Purple", "dark_purple", "AA00AA", "2A002A",),
    MCColor("6", "Gold", "gold", "FFAA00", "2A2A00",),
    MCColor("7", "Gray", "gray", "AAAAAA", "2A2A2A",),
    MCColor("8", "Dark Gray", "dark_gray", "555555", "151515",),
    MCColor("9", "Blue", "blue", "5555FF", "15153F",),
    MCColor("a", "Green", "green", "55FF55", "153F15",),
    MCColor("b", "Aqua", "aqua", "55FFFF", "153F3F",),
    MCColor("c", "Red", "red", "FF5555", "3F1515",),
    MCColor("d", "Light Purple", "light_purple", "FF55FF", "3F153F",),
    MCColor("e", "Yellow", "yellow", "FFFF55", "3F3F15",),
    MCColor("f", "White", "white", "FFFFFF", "3F3F3F",),
]
COLOR_CODES = {c.code: c for c in COLORS}
CONTROL_CODES = {
    "l": "bold",
    "m": "strikethrough",
    "n": "underline",
    "o": "italic",
    "r": "reset",
}


class StringView:
    def __init__(self, buffer):
        self.index = 0
        self.buffer = buffer
        self.end = len(buffer)

    def take_until(self, char, eat=True):
        start = self.index
        while not self.eof():
            if self.buffer[self.index] == char:
                break
            self.index += 1
        res = self.buffer[start:self.index]
        if eat:
            self.index += 1
        return res

    def eof(self):
        return self.index >= self.end


class MCSegment:
    __slots__ = ("color", "text", "bold", "strikethrough", "underline", "italic")

    def __init__(self, text,
            color=None, bold=False, strikethrough=False, underline=False, italic=False):
        self.text = text
        self.color = color
        self.bold = bold
        self.italic = italic
        self.strikethrough = strikethrough
        self.underline = underline

    def render_discord(self):
        if self.text == "":
            return ""
        fmt = "{}"
        if self.bold:
            fmt = "**%s**" % fmt
        if self.italic:
            fmt = "*%s*" % fmt
        if self.strikethrough:
            fmt = "~~%s~~" % fmt
        if self.underline:
            fmt = "__%s__" % fmt
        return fmt.format(self.text)

    def __repr__(self):
        return "<MCSegment " + \
            " ".join("%s=%r" % (attr, getattr(self, attr)) for attr in self.__slots__) + ">"


class MCDescription:
    def __init__(self, segments):
        self.segments = segments

    @classmethod
    def from_text(cls, txt):
        segments = str_to_segments(txt)
        return cls(segments)

    @classmethod
    def from_dict(cls, dct_or_str):
        if isinstance(dct_or_str, str):
            return cls.from_text(dct_or_str)
        elif "extra" in dct_or_str:
            assert dct_or_str["text"] == "", dct_or_str
            return cls([MCSegment(**s) for s in dct_or_str["extra"]])
        return cls.from_text(dct_or_str['text'])

    @property
    def plain_text(self):
        return "".join(s.text for s in self.segments)

    @property
    def discord_text(self):
        # TODO: this is kind of a lazy impl, but it works
        return "\u200b".join(s.render_discord() for s in self.segments)


def str_to_segments(buf):
    view = StringView(buf)

    status = {}
    first_segment = view.take_until(MC_COLOR_CODE)
    yield MCSegment(text=first_segment)

    while not view.eof():
        seg_raw = view.take_until(MC_COLOR_CODE)
        code, text = seg_raw[0], seg_raw[1:]
        if code in COLOR_CODES:
            status["color"] = COLOR_CODES[code].id
            yield MCSegment(text=text, **status)
        elif code in CONTROL_CODES:
            if code == "r":
                status = {}
            else:
                status[CONTROL_CODES[code]] = True
            yield MCSegment(text=text, **status)


def lookup_and_status(server):
    try:
        mcs = mcstatus.MinecraftServer.lookup(server)
    except ValueError as e:
        raise errors.BadArgument(e.args[0])

    try:
        return mcs.status()
    except (ConnectionError, socket.timeout):
        raise errors.CommandError("Could not connect to %s" % server)
    except socket.gaierror:
        raise errors.BadArgument("The domain name %s doesn't exit" % server)


@dcog(["Res"])
class Minecraft(Cog):
    def __init__(self, config, res):
        self.res = res
        self._mc_uuid_cache = LRU(256)

    def mcstatus_message(self, status):
        status.description = MCDescription.from_dict(status.description)

        e = discord.Embed()

        e.set_thumbnail(url="attachment://favicon.png")
        if status.favicon:
            _, b64 = status.favicon.split(',')

            fil = discord.File(
                io.BytesIO(base64.b64decode(b64)),
                filename="favicon.png")
        else:
            fil = discord.File(
                os.path.join(self.res.dir(), "img", "unknown_server.png"),
                filename="favicon.png")

        e.description = "\u200b" + status.description.discord_text

        e.add_field(
            name="version",
            value="{0.version.name} (proto {0.version.protocol})    \u200b".format(status))
        e.add_field(name="ping", value=status.latency)
        players_string = "{0.players.online}/{0.players.max}    \u200b".format(status)
        if status.players.sample:
            players_string += "".join(
                "\n[%s](%s)" % (p.name, p.id) for p in status.players.sample)
        e.add_field(name="players", value=players_string)


        return dict(embed=e, file=fil)

    @command()
    async def mcstatus(self, ctx, *, server):
        with ctx.typing():
            status = await ctx.bot.loop.run_in_executor(None, lookup_and_status, server)

        await ctx.send(**self.mcstatus_message(status))

    async def _uuid_lookup(self, minecraftusername):
        try:
            return self._mc_uuid_cache[minecraftusername]
        except KeyError:
            async with aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(enable_cleanup_closed=True)) as s:
                async with s.get("https://api.mojang.com/users/profiles/minecraft/{}".format(minecraftusername)) as resp:
                    resp.raise_for_status()
                    if resp.status == 204:
                        uuid = None
                    else:
                        data = await resp.json()
                        if 'error' in data:
                            raise Exception(data['error'], data['errorMessage'])
                        else:
                            uuid = data['id']
            self._mc_uuid_cache[minecraftusername] = uuid
            return uuid

    @command()
    async def mcavatar(self, ctx, minecraftusername: str):
        """Display a minecraft avatar."""
        uuid = await self._uuid_lookup(minecraftusername)
        if not uuid:
            raise errors.BadArgument("No such user {}".format(minecraftusername))
        await ctx.send("https://visage.surgeplay.com/full/512/{}.png".format(uuid))
