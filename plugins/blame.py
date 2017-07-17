import logging
from dango import dcog
from discord.ext.commands import command
from discord.ext.commands import errors

log = logging.getLogger(__name__)


@dcog(depends=["Database"])
class Blame:

    def __init__(self, config, database):
        self.database = database

    async def on_dango_message_sent(self, msg, ctx):
        async with self.database.acquire() as conn:
            server_id = ctx.guild and ctx.guild.id
            await conn.execute(
                "INSERT INTO blame "
                "(id, message_id, author_id, channel_id, server_id)"
                "VALUES ($1, $2, $3, $4, $5)", msg.id, ctx.message.id,
                ctx.author.id, ctx.channel.id, server_id)

    @command()
    async def blame(self, ctx, message_id: int):
        """Show who caused a command response to show up.

        message_id must be a message said by the bot. Note you
        must enable developer mode in order to get message ids.
        See Discord's documentation here: https://waa.ai/j06h
        """
        async with self.database.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT blame.id, blame.message_id, blame.author_id, "
                "blame.channel_id, blame.server_id "
                "FROM blame where blame.id = $1", message_id)

        if not row:
            raise errors.BadArgument("No info for that message.")

        _, message_id, author_id, channel_id, server_id = row.values()

        usr = ctx.bot.get_user(author_id)
        srv = ctx.bot.get_guild(server_id)
        if usr:
            author_id = "%s (%s)" % (str(usr), author_id)
        if srv:
            server_id = "%s (%s)" % (srv, srv.id)

        await ctx.send("Server: %s\nChannel: <#%s>\nUser: %s\nMessage: %s" %
                       (server_id, channel_id, author_id, message_id))
