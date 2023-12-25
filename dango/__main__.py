"""Main bot file."""
import asyncio
import logging
import sys

import discord

from .core import DangoAutoShardedBot
from .utils import fix_unicode


def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    dango = logging.getLogger("dango")
    dango.setLevel(logging.DEBUG)
    plugins = logging.getLogger("plugins")
    plugins.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "[%(asctime)s][%(name)s][%(levelname)s] %(message)s")

    stdouthandler = logging.StreamHandler(sys.stdout)
    stdouthandler.setLevel(logging.DEBUG)
    stdouthandler.setFormatter(formatter)
    root.addHandler(stdouthandler)


async def real_main():
    setup_logging()
    bot = DangoAutoShardedBot(
        game=discord.Game(name="rewrite is the future!"),
        intents=discord.Intents.all())
    await bot.start()


def main():
    asyncio.run(real_main())


fix_unicode()
main()
