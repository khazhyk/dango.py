import io
import random

import aiohttp
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

    @command()
    async def corrupt(self, ctx, *, user: discord.User=None):
        user = user or ctx.message.author
        async with aiohttp.ClientSession() as sess:
            async with sess.get(user.avatar_url_as(format='jpg')) as resp:
                img_buff = bytearray(await resp.read())
        for i in range(random.randint(5, 25)):
            img_buff[random.randint(0, len(img_buff))] = random.randint(1, 254)
        await ctx.send(file=discord.File(io.BytesIO(img_buff), filename="img.jpg"))
