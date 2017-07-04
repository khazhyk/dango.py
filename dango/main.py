"""Main bot file."""
import logging
import sys

from dango import core


def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    dango = logging.getLogger("dango")
    dango.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "[%(asctime)s][%(name)s][%(levelname)s] %(message)s")

    stdouthandler = logging.StreamHandler(sys.stdout)
    stdouthandler.setLevel(logging.DEBUG)
    stdouthandler.setFormatter(formatter)
    root.addHandler(stdouthandler)


def main(config):
    setup_logging()
    bot = core.DangoAutoShardedBot('test ', shard_count=1, config=config)
    bot.watch_plugin_dir(getattr(config, 'plugins', 'plugins'))  # TODO
    bot.run(config.token)
