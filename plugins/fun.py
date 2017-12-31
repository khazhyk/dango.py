"""Tags!

Tag types:
 - Image gallery tags
   - Folder on disk, with images in it. "imgmemes"
 - Image macro tags
   - Image base, font, justifcation, border, maxwidth, etc.
   - Love, hate, etc.
 - Text tags
   - "textmemes"
   - Use creatable.
 - Custom tags
   - Python custom image generation (everything else).
"""
import io
import os
import random

import aiohttp
from dango import dcog
import discord
from discord.ext.commands import command, group
from PIL import Image

ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'gif', 'webp'}


def _allowed_ext(filename):
    return os.path.splitext(filename)[1][1:] in ALLOWED_EXT


class TagCommand:
    """Base class for server opt-in commands."""


class CommandAlias:
    """Register a command as an alias under a different namespace."""

    async def callback(self, ctx, *args, **kwargs):
        pass


class ImgDirCmd(discord.ext.commands.Command):
    def __init__(self, name, directory):
        super().__init__(name, self.callback)
        self.directory = directory

    async def callback(self, ctx, idx: int=None):
        files = [f for f in os.listdir(self.directory)
                 if _allowed_ext(f)]
        if idx is None or 0 > idx >= len(files):
            idx = random.randrange(0, len(files))
        f = os.path.join(self.directory, sorted(files)[idx])
        await ctx.send(file=discord.File(f, filename="{}_{}{}".format(
            self.name, idx, os.path.splitext(f)[1])))


class ImgFileCmd(discord.ext.commands.Command):
    def __init__(self, name, filename):
        super().__init__(name, self.callback)
        self.filename = filename
        self.upload_name = "{}{}".format(
            self.name, os.path.splitext(filename)[1])

    async def callback(self, ctx, idx: int=None):
        await ctx.send(file=discord.File(self.filename, filename=self.upload_name))


@dcog(["Database"], pass_bot=True)
class Fun:

    def __init__(self, bot, config, database):
        self.db = database
        self.image_galleries_dir = config.register("image_galleries_dir")
        self._init_image_galleries(bot, self.image_galleries_dir())

    @group()
    async def meme(self, ctx):
        pass

    def _init_image_galleries(self, bot, imgdir):
        """Load and register commands based on on-disk image gallery dir."""
        for item in os.listdir(imgdir):
            fullpath = os.path.join(imgdir, item)
            if os.path.isdir(fullpath):
                cmd = ImgDirCmd(item, fullpath)
            elif os.path.isfile(fullpath):
                if not _allowed_ext(item):
                    continue
                cmd = ImgFileCmd(os.path.splitext(item)[0], fullpath)
            self.meme.add_command(cmd)
            bot.add_command(cmd)

@dcog()
class ImgFun:

    def __init__(self, cfg):
        pass

    @command()
    async def corrupt(self, ctx, *, user: discord.User=None):
        """Corrupt a user's avatar."""
        user = user or ctx.message.author
        async with aiohttp.ClientSession() as sess:
            async with sess.get(user.avatar_url_as(format='jpg')) as resp:
                img_buff = bytearray(await resp.read())
        for i in range(random.randint(5, 25)):
            img_buff[random.randint(0, len(img_buff))] = random.randint(1, 254)
        await ctx.send(file=discord.File(io.BytesIO(img_buff), filename="img.jpg"))


    @staticmethod
    def make_dot():
        width = 512
        img = Image.new('RGBA', (width, 1))
        img.putpixel((random.randrange(0, width), 0), 0xff0000ff)
        buff = io.BytesIO()
        img.save(buff, 'png')
        buff.seek(0)
        return buff


    @command()
    async def dot(self, ctx):
        res = await ctx.bot.loop.run_in_executor(None, self.make_dot)
        await ctx.send(file=discord.File(res, filename="dot.png"))
