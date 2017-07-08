import asyncio
import os
import subprocess
import sys


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
