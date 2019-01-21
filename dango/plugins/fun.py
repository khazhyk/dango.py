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
import time

import aiohttp
from dango import dcog
import discord
from discord.ext.commands import command, check, errors, group
from PIL import Image

from .common import converters
from .common import checks

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
            cmd.instance = self
            self.meme.add_command(cmd)
            bot.add_command(cmd)

def get_lum(r,g,b,a=1):
    return (0.299*r + 0.587*g + 0.114*b) * a

@dcog()
class ImgFun:

    def __init__(self, cfg):
        pass

    @command()
    async def corrupt(self, ctx, *, user: converters.UserMemberConverter=None):
        """Corrupt a user's avatar."""
        user = user or ctx.message.author
        async with aiohttp.ClientSession() as sess:
            async with sess.get(user.avatar_url_as(format='jpg')) as resp:
                if resp.status != 200:
                    raise errors.CommandError("Your avatar is broken :(")
                img_buff = bytearray(await resp.read())
        for i in range(random.randint(5, 25)):
            img_buff[random.randint(0, len(img_buff))] = random.randint(1, 254)
        await ctx.send(file=discord.File(io.BytesIO(img_buff), filename="img.jpg"))

    @staticmethod
    def _gifmap(avy1, avy2):
        """stolen from cute."""
        maxres = 200
        avy1 = Image.open(avy1).resize((maxres,maxres), resample=Image.BICUBIC)
        avy2 = Image.open(avy2).resize((maxres,maxres), resample=Image.BICUBIC)

        avy1data = avy1.load()
        avy1data = [[(x,y),avy1data[x,y]] for x in range(maxres) for y in range(maxres)]
        avy1data.sort(key = lambda c : get_lum(*c[1]))

        avy2data = avy2.load()
        avy2data = [[(x,y),avy2data[x,y]] for x in range(maxres) for y in range(maxres)]
        avy2data.sort(key = lambda c : get_lum(*c[1]))

        frames = []
        for mult in range(-10,11,1):
            m = 1 - (1/(1+(1.7**-mult)))

            base = Image.new('RGBA', (maxres,maxres))
            basedata = base.load()
            for i, d in enumerate(avy1data):
                x1, y1 = d[0]
                x2, y2 = avy2data[i][0]
                x, y = round(x1 + (x2 - x1)*m), round(y1 + (y2 - y1) * m)
                basedata[x, y] = avy2data[i][1]
            frames.append(base)

        frames = frames + frames[::-1]

        b = io.BytesIO()
        frames[0].save(b, 'gif', save_all=True, append_images=frames[1:], loop=0, duration=60)
        b.seek(0)
        return b

    @command()
    @checks.bot_needs(["attach_files"])
    async def colormap3(self, ctx, source: discord.Member, dest: discord.Member = None):
        """Hello my name is Koishi."""
        dest = dest or ctx.author

        start = time.time()
        async with ctx.typing():
            async with aiohttp.ClientSession() as sess:
                async with sess.get(source.avatar_url_as(format="png")) as resp:
                    resp.raise_for_status()
                    source_bytes = await resp.content.read()

                async with sess.get(dest.avatar_url_as(format="png")) as resp:
                    resp.raise_for_status()
                    dest_bytes = await resp.content.read()

            img_buff = await ctx.bot.loop.run_in_executor(None,
                    self._gifmap, io.BytesIO(dest_bytes), io.BytesIO(source_bytes)
                )
        elapsed = time.time() - start
        await ctx.send("took %02fs" % elapsed,
            file=discord.File(img_buff, filename="%s_to_%s.gif" % (source, dest)))


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
    @checks.bot_needs(["attach_files"])
    async def dot(self, ctx):
        res = await ctx.bot.loop.run_in_executor(None, self.make_dot)
        await ctx.send(file=discord.File(res, filename="dot.png"))
