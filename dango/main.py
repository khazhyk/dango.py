"""Main bot file."""
import logging
import sys

from dango import core
import discord


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


def main():
    setup_logging()
    bot = core.DangoAutoShardedBot(
        game=discord.Game(name="rewrite is the future!"))
    bot.run()
