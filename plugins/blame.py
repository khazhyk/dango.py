import logging
from dango import plugin
from discord.ext.commands import command

log = logging.getLogger(__name__)


@plugin(depends=["Database"])
class Blame:

    def __init__(self, database):
        self.database = database

    async def on_dango_message_sent(self, msg, ctx):
        log.info("Sent message: %s from %s" % (msg, ctx))

    @command()
    async def blame(self, ctx, message_id: int):
        pass
