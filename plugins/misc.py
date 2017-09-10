from dango import dcog
from dango import utils
import discord
from discord.ext.commands import command
from discord.ext.commands import errors

FULLWIDTH_OFFSET = 65248


@dcog()
class Misc:

    def __init__(self, config):
        pass

    @command(aliases=['fw', 'fullwidth', 'ａｅｓｔｈｅｔｉｃ'])
    async def aesthetic(self, ctx, *, msg="aesthetic"):
        """ａｅｓｔｈｅｔｉｃ."""
        await ctx.send("".join(map(
            lambda c: chr(ord(c) + FULLWIDTH_OFFSET) if (ord(c) >= 0x21 and ord(c) <= 0x7E) else c,
            msg)).replace(" ", chr(0x3000)))

    @command()
    async def msgsource(self, ctx, *, msg_id: int):
        try:
            msg = await ctx.get_message(msg_id)
        except discord.NotFound:
            raise errors.BadArgument("Message not found")
        else:
            await ctx.send("```{}```".format(utils.clean_triple_backtick(msg.content)))
