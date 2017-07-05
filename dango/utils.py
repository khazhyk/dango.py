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

    def __init__(self, coro, wrapped):
        self.coro = coro
        self.wrapped = wrapped

    async def __aenter__(self):
        await self.coro
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
