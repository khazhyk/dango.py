import aiohttp
import asyncio
import copy
import codecs
from datetime import datetime
import logging
import io
import os
import re
import subprocess
import sys
import unicodedata
import yarl

import discord
from discord.ext.commands import errors
from discord.iterators import HistoryIterator
from PIL import Image


log = logging.getLogger(__name__)


def snakify(name):
    """Turn CamelCase into snake_case."""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def fix_unicode():
    """Make python not crash when logging trivial statements."""
    if os.name == "nt":
        sys.stdout = sys.__stdout__ = open(
            sys.stdout.detach().fileno(), 'w', encoding=sys.stdout.encoding,
            errors="backslashreplace")
        sys.stderr = sys.__stderr__ = open(
            sys.stderr.detach().fileno(), 'w', encoding=sys.stderr.encoding,
            errors="backslashreplace")


class AsyncContextWrapper:

    def __init__(self, coro):
        self.coro = coro

    async def __aenter__(self):
        self.wrapped = await self.coro
        return await self.wrapped.__aenter__()

    async def __aexit__(self, *args, **kwargs):
        return await self.wrapped.__aexit__(*args, **kwargs)


class ContextWrapper:
    """Turns `with await` into `async with`."""

    def __init__(self, coro):
        self.coro = coro

    async def __aenter__(self):
        self.instance = await self.coro
        return self.instance.__enter__()

    async def __aexit__(self, *args, **kwargs):
        return self.instance.__exit__(*args, **kwargs)


async def run_subprocess(cmd, loop=None):
    try:
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        res = await proc.communicate()
    except NotImplementedError:
        loop = loop or asyncio.get_event_loop()
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        res = await loop.run_in_executor(None, proc.communicate)
    return [s.decode('utf8') for s in res]


class TypeMap:
    """Dict that looks up based on a class's bases.

    In the case of conflict, will return the first matching base.
    Lookup time is O(n), where n is # of bases a class has.
    """

    def __init__(self, dct=None):
        self._dict = dct or {}

    def put(self, cls, obj):
        self._dict[cls] = obj

    def lookup(self, cls):
        for base in cls.__mro__:
            try:
                return self._dict[base]
            except KeyError:
                pass


def clean_invite_embed(line):
    """Makes invites not embed"""
    return line.replace("discord.gg/", "discord.gg/\u200b")


def clean_single_backtick(line):
    """Clean string for insertion in single backtick code section.

    Clean backticks so we don't accidentally escape, and escape custom emojis
    that would be discordified.
    """
    if re.search('[^`]`[^`]', line) is not None:
        return "`%s`" % clean_double_backtick(line)
    if (line[:2] == '``'):
        line = '\u200b' + line
    if (line[-1] == '`'):
        line = line + '\u200b'
    return clean_emojis(line)


def clean_double_backtick(line):
    """Clean string for isnertion in double backtick code section.

    Clean backticks so we don't accidentally escape, and escape custom emojis
    that would be discordified.
    """
    line.replace('``', '`\u200b`')
    if (line[0] == '`'):
        line = '\u200b' + line
    if (line[-1] == '`'):
        line = line + '\u200b'

    return clean_emojis(line)


def clean_triple_backtick(line):
    """Clean string for insertion in triple backtick code section.

    Clean backticks so we don't accidentally escape, and escape custom emojis
    that would be discordified.
    """
    if not line:
        return line

    i = 0
    n = 0
    while i < len(line):
        if (line[i]) == '`':
            n += 1
        if n == 3:
            line = line[:i] + '\u200b' + line[i:]
            n = 1
            i += 1
        i += 1

    if line[-1] == '`':
        line += '\n'

    return clean_emojis(line)


def clean_newline(line):
    """Cleans string so formatting does not cross lines when joined with \\n.

    Just looks for unpaired '`' characters, other formatting characters do not
    seem to be joined across newlines.

    For reference, discord uses:
    https://github.com/Khan/simple-markdown/blob/master/simple-markdown.js
    """
    match = None
    for match1 in re.finditer(r'(`+)\s*([\s\S]*?[^`])\s*\1(?!`)', line):
        match = match1

    idx = match.end() if match else 0

    line = line[:idx] + line[idx:].replace('`', '\`')

    return line


def clean_formatting(line):
    """Escape formatting items in a string."""
    return re.sub(r"([`*_])", r"\\\1", line)


def clean_mentions(line):
    """Escape anything that could resolve to mention."""
    return line.replace("@", "@\u200b")

def clean_emojis(line):
    """Escape custom emojis."""
    return re.sub(r'<(a)?:([a-zA-Z0-9_]+):([0-9]+)>', '<\u200b\\1:\\2:\\3>', line)

def log_task(fut):
    try:
        if fut.exception():
            e = fut.exception()
            log.warn("", exc_info=(type(e), e, e.__traceback__))
    except asyncio.CancelledError as e:
        log.debug("", exc_info=(type(e), e, e.__traceback__))

def create_task(thing):
    task = asyncio.ensure_future(thing)
    task.add_done_callback(log_task)
    return task


def value_format(k, v, col_len):
    v = str(v).split("\n")

    return "{}: {}".format(k.rjust(col_len), v[0]) + "".join(
        "\n{}  {}".format(" " * col_len, subv) for subv in v[1:])

class InfoBuilder:
    def __init__(self, fields=None, description=""):
        self.description = description
        self.fields = fields or []

    def add_field(self, name, value):
        self.fields.append((name, value))

    def code_block(self):
        col_len = max(len(name) for name, _ in self.fields)

        return "```prolog\n\u200b{}```".format(
            clean_invite_embed(clean_triple_backtick(clean_mentions(
                "\n".join(value_format(k, v, col_len) for k, v in self.fields)))))

    def as_file(self):
        col_len = max(len(name) for name, _ in self.fields)

        return discord.File(io.StringIO("\n".join(value_format(k, v, col_len) for k, v in self.fields)), filename="info.prolog")

    def embed(self):
        e = discord.Embed()
        for k, v in self.fields:
            e.add_field(name=k, value=v)
        return e

def resolve_color(value):
    """Resolve a custom or pre-defined color.

    This allows html style #RRGGBB and #AARRGGBB

    Returns (r, g, b) or (a, r, g, b)
    """
    if value.startswith('#'):
        value = value[1:]  # assumes no named color starts with #

    try:
        intval = int(value, 16)
    except ValueError:
        pass
    else:
        if intval >= (1 << 32):
            raise errors.BadArgument("Invalid color {} is too big!".format(value))
        if len(value) > 6:
            color = discord.Colour(intval)
            return (color.r, color.g, color.b, color._get_byte(3))
        return discord.Colour(intval).to_rgb()
    try:
        return getattr(discord.Colour, value)().to_rgb()
    except AttributeError:
        raise errors.BadArgument("Invalid color {}".format(value))

def convert_date(argument):
    formats = (
        '%Y/%m/%d',
        '%Y-%m-%d',
    )

    for fmt in formats:
        try:
            return datetime.strptime(argument, fmt)
        except ValueError:
            continue

    raise errors.BadArgument(
        'Cannot convert to date. Expected YYYY/MM/DD or YYYY-MM-DD.')

def emoji_url(emoji):
    return "http://twemoji.maxcdn.com/2/72x72/{}.png".format(
        "-".join("{:x}".format(ord(c)) for c in emoji))


class _LoadingEmojiContext():
    def __init__(self, ctx):
        self.ctx = ctx

    async def __aenter__(self):
        await self.ctx.message.add_reaction("a:loading:393852367751086090")

    async def __aexit__(self, exc_type, exc, tb):
        await self.ctx.message.remove_reaction("a:loading:393852367751086090", self.ctx.me)
        if exc is None:
            await self.ctx.message.add_reaction(":helYea:236243426662678528")
        else:
            await self.ctx.message.add_reaction(":discordok:293495010719170560")

def loading_emoji(ctx):
    return _LoadingEmojiContext(ctx)

def jump_url(message):
  return "<https://discord.com/channels/{0.channel.guild.id}/{0.channel.id}/{0.id}>".format(message)

class AliasCmd(discord.ext.commands.Command):
    def __init__(self, name, alias, owner, bypass=False):
        super().__init__(self._callback, name=name)
        self.alias = alias
        self.bypass = bypass
        self.cog = owner

    async def _callback(self, cog, ctx):
        fake_msg = copy.copy(ctx.message)
        fake_msg._update(dict(
            content=ctx.prefix + self.alias))
        new_ctx = await ctx.bot.get_context(fake_msg)

        if self.bypass:
            await new_ctx.command.reinvoke(new_ctx, call_hooks=True)
        elif await new_ctx.bot.can_run(new_ctx, call_once=True):
            await new_ctx.bot.invoke(new_ctx)

class CachedHistoryIterator(HistoryIterator):
    """HistoryIterator, but we hit the cache first."""

    def __init__(self, messageable, limit,
                 before=None, after=None, around=None, oldest_first=None):
        super().__init__(messageable, limit, before, after, around, oldest_first)
        self.prefill = self.reverse is False and around is None

    async def next(self):
        if self.prefill:
            await self.prefill_from_cache()
            self.prefill = False
        return await super().next()

    async def prefill_from_cache(self):
        if not hasattr(self, 'channel'):
            # do the required set up
            channel = await self.messageable._get_channel()
            self.channel = channel

        for msg in reversed(self.channel._state._messages):
            if msg.channel.id == self.channel.id and self.limit > 0 and (not self.before or msg.id < self.before.id):
                self.limit -= 1
                self.before = discord.Object(id=msg.id)
                await self.messages.put(msg)

CONTROL_CHARS = re.compile('[%s]' % re.escape(''.join(chr(i) for i in range(sys.maxunicode) if unicodedata.category(chr(i)).startswith('C'))))

def escape_invis(decode_error):
    decode_error.end = decode_error.start + 1
    if CONTROL_CHARS.match(decode_error.object[decode_error.start:decode_error.end]):
        return codecs.backslashreplace_errors(decode_error)
    return decode_error.object[decode_error.start:decode_error.end].encode('utf-8'), decode_error.end

codecs.register_error('escape-invis', escape_invis)

def escape_invis_chars(input):
    """Escape invisible/control characters."""
    return input.encode('ascii', 'escape-invis').decode('utf-8')


async def fetch_image(url):
    """Fetch the given image."""
    url = str(url)
    # Workaround https://github.com/aio-libs/aiohttp/issues/3426
    async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(enable_cleanup_closed=True)) as sess:
        # proxy_url must be passed exactly - encoded=True
        # https://github.com/aio-libs/aiohttp/issues/3424#issuecomment-443760653
        async with sess.get(yarl.URL(url, encoded=True)) as resp:
            resp.raise_for_status()
            content_length = int(resp.headers.get('Content-Length', 50<<20))
            if content_length > 50<<20:
                raise errors.BadArgument("File too big")

            blocks = []
            readlen = 0
            tested_image = False
            # Read up to X bytes, raise otherwise
            while True:
                block = await resp.content.readany()
                if not block:
                    break
                blocks.append(block)
                readlen += len(block)
                if readlen >= 10<<10 and not tested_image:
                    try:
                        Image.open(io.BytesIO(b''.join(blocks)))
                    except OSError:
                        raise errors.BadArgument("This doesn't look like an image to me")
                    else:
                        tested_image = True
                if readlen > content_length:
                    raise errors.BadArgument("File too big")
            source_bytes = b''.join(blocks)
    return source_bytes
