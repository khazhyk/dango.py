import asyncio
import os
import re
import subprocess
import sys


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
    """Clean string for insertion in single backtick code section."""
    if re.search('[^`]`[^`]', line) is not None:
        raise ValueError("Cannot be cleaned")
    if (line[:2] == '``'):
        line = '\u200b' + line
    if (line[-1] == '`'):
        line = line + '\u200b'
    return line


def clean_double_backtick(line):
    """Clean string for isnertion in double backtick code section."""
    line.replace('``', '`\u200b`')
    if (line[0] == '`'):
        line = '\u200b' + line
    if (line[-1] == '`'):
        line = line + '\u200b'
    return line


def clean_triple_backtick(line):
    """Clean string for insertion in triple backtick code section."""
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
        line += '\u200b'

    return line


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
