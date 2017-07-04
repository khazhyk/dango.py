import logging
from dango import plugin
from discord.ext.commands import command
from discord.ext.commands import errors
import sqlalchemy as sa

log = logging.getLogger(__name__)


BlameTable = sa.Table(
    'blame', sa.MetaData(),
    sa.Column('id', sa.BigInteger, primary_key=True),
    sa.Column('message_id', sa.BigInteger),
    sa.Column('author_id', sa.BigInteger),
    sa.Column('channel_id', sa.BigInteger),
    sa.Column('server_id', sa.BigInteger))


@plugin(depends=["Database"])
class Blame:

    def __init__(self, database):
        self.database = database

    async def on_dango_message_sent(self, msg, ctx):
        log.info("Sent message: %s from %s" % (msg, ctx))
        async with self.database.acquire() as conn:
            server_id = ctx.guild and ctx.guild.id
            await conn.execute(BlameTable.insert().values(
                    id=msg.id,
                    message_id=ctx.message.id,
                    author_id=ctx.author.id,
                    channel_id=ctx.channel.id,
                    server_id=server_id
                ))

    @command()
    async def blame(self, ctx, message_id: int):
        async with self.database.acquire() as conn:
            res = await conn.execute(BlameTable.select().where(
                BlameTable.c.id == message_id))
            row = await res.fetchone()

        if not row:
            raise errors.BadArgument("No info for that message.")

        _, message_id, author_id, channel_id, server_id = row.values()

        usr = ctx.bot.get_user(author_id)

        if usr:
            usr_string = "%s (%s)" % (str(usr), author_id)
        else:
            usr_string = author_id

        await ctx.send("Server: %s\nChannel: <#%s>\nUser: %s\nMessage: %s" %
                       (server_id, channel_id, usr_string, message_id))
