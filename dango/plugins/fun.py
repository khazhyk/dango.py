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
import asyncio
import io
import inspect
import math
import os
import random
import time

import aiohttp
import yarl
from dango import dcog, Cog
import discord
from discord.ext.commands import command, check, errors, group
from PIL import Image, ImageFont, ImageDraw, ImageOps, ImageFilter, ImageChops
import textwrap

from .common import converters
from .common import checks
from .common.utils import AliasCmd

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
        super().__init__(self._callback, name=name)
        self.directory = directory

    async def _callback(self, cog, ctx, idx: int=None):
        files = [f for f in os.listdir(self.directory)
                 if _allowed_ext(f)]
        if idx is None or 0 > idx >= len(files):
            idx = random.randrange(0, len(files))
        f = os.path.join(self.directory, sorted(files)[idx])
        await ctx.send(file=discord.File(f, filename="{}_{}{}".format(
            self.name, idx, os.path.splitext(f)[1])))


class ImgFileCmd(discord.ext.commands.Command):
    def __init__(self, name, filename):
        super().__init__(self._callback, name=name)
        self.filename = filename
        self.upload_name = "{}{}".format(
            self.name, os.path.splitext(filename)[1])

    async def _callback(self, cog, ctx, idx: int=None):
        await ctx.send(file=discord.File(self.filename, filename=self.upload_name))


class TextCmd(discord.ext.commands.Command):
    def __init__(self, name, texts):
        super().__init__(self._callback, name=name)
        self.texts = texts

    async def _callback(self, cog, ctx):
        await ctx.send(random.sample(self.texts, 1)[0])


async def fetch_image(url):
    """Fetch the given image."""
    url = str(url)
    # Workaround https://github.com/aio-libs/aiohttp/issues/3426            
    async with aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(enable_cleanup_closed=True)) as sess:
        # proxy_url must be passed exactly - encoded=True
        # https://github.com/aio-libs/aiohttp/issues/3424#issuecomment-443760653
        async with sess.get(yarl.URL(url, encoded=True)) as resp:
            resp.raise_for_status()
            content_length = int(resp.headers.get('Content-Length', 50<<20))
            if content_length > 50<<20:
                raise errors.BadArgument("File too big")

            blocks = []
            readlen = 0
            tested_image = False
            # Read up to X bytes, raise otherwise
            while True:
                block = await resp.content.readany()
                if not block:
                    break
                blocks.append(block)
                readlen += len(block)
                if readlen >= 10<<10 and not tested_image:
                    try:
                        Image.open(io.BytesIO(b''.join(blocks)))
                    except OSError:
                        raise errors.BadArgument("This doesn't look like an image to me")
                    else:
                        tested_image = True
                if readlen > content_length:
                    raise errors.BadArgument("File too big")
            source_bytes = b''.join(blocks)
    return source_bytes


@dcog(["Database"], pass_bot=True)
class Fun(Cog):

    def __init__(self, bot, config, database):
        self.db = database
        self.image_galleries_dir = config.register("image_galleries_dir")
        self.text_posts = config.register("text_posts", {})
        self.bot = bot
        self._custom_commands = []
        self._init_image_galleries(bot, self.image_galleries_dir())
        self._init_text_posts(bot)



    @group()
    async def meme(self, ctx):
        pass

    def cog_unload(self):
        for cmd in self._custom_commands:
            self.bot.remove_command(str(cmd))

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
            cmd.cog = self
            self.meme.add_command(cmd)
            alias = AliasCmd(cmd.name, str(cmd), self)
            bot.add_command(alias)
            self._custom_commands.append(alias)

    def _init_text_posts(self, bot):
        """Load and register commands based on config text posts."""
        for name, item in self.text_posts().items():
            if isinstance(item, str):
                item = [item]
            cmd = TextCmd(name, item)
            cmd.cog = self
            self.meme.add_command(cmd)
            alias = AliasCmd(cmd.name, str(cmd), self)
            bot.add_command(alias)
            self._custom_commands.append(alias)

def get_lum(r,g,b,a=1):
    return (0.299*r + 0.587*g + 0.114*b) * a

@dcog(["Res"])
class ImgFun(Cog):

    def __init__(self, cfg, res):
        self.res = res

    @command()
    async def corrupt(self, ctx, *, user: converters.UserMemberConverter=None):
        """Corrupt a user's avatar."""
        user = user or ctx.message.author
        img_buff = bytearray(await fetch_image(user.avatar_url_as(format="jpg")))
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
            source_bytes = await fetch_image(source.avatar_url_as(format="png"))
            dest_bytes = await fetch_image(dest.avatar_url_as(format="png"))

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

    def make_dont_image(self, content):
        inset = Image.open(io.BytesIO(content))

        img = Image.new('RGB', (800, 600), 'White')

        img.paste(inset.resize((400, 400)), (271, 17, 671, 417))

        img.paste(inset.resize((128, 128)), (190, 387, 318, 515))

        f = ImageFont.truetype(
            font=self.res.dir() + "/font/comic sans ms/comic.ttf",
            size=26, encoding="unic")

        ayy = ImageDraw.Draw(img)

        ayy.text((340, 430), "dont talk to me or my son\never again",
                 (0, 0, 0), font=f)

        buff = io.BytesIO()
        img.save(buff, 'jpeg')

        buff.seek(0)

        return buff

    @command()
    @checks.bot_needs(["attach_files"])
    async def dont(self, ctx, *, url: converters.AnyImage=converters.AuthorAvatar):
        """dont run me or my son ever again"""
        with ctx.typing():
            content = await fetch_image(url)
            img_buff = await ctx.bot.loop.run_in_executor(None, self.make_dont_image, content)

            await ctx.send(file=discord.File(img_buff, filename="dont.jpg"))

    def make_rip(self, inset):
        inset_img = Image.open(io.BytesIO(inset))

        rip_img = Image.open(self.res.dir() + "/img/rip-tombstone.png")

        inset_contoured = ImageOps.autocontrast(inset_img.convert('L').filter(ImageFilter.CONTOUR)).filter(
            ImageFilter.SMOOTH)

        inset_layer = Image.new(
            "RGBA", (rip_img.width, rip_img.height), 'White')

        inset_layer.paste(inset_contoured.resize((225, 225)), (130, 285))

        final = ImageChops.multiply(rip_img, inset_layer)

        buff = io.BytesIO()
        final.save(buff, "png")
        buff.seek(0)
        return buff

    @command()
    @checks.bot_needs(["attach_files"])
    async def rip(self, ctx, *, url: converters.AnyImage=converters.AuthorAvatar):
        """RIP in Peace."""
        with ctx.typing():
            content = await fetch_image(url)
            img_buff = await ctx.bot.loop.run_in_executor(None, self.make_rip, content)
            await ctx.send(file=discord.File(img_buff, filename="rip.png"))

    @staticmethod
    def make_triggered(inset, scale_down=.9, max_shift=.1):
        inset_img = Image.open(io.BytesIO(inset))
        frames = []
        out_size = (math.floor(inset_img.width * scale_down),
                    math.floor(inset_img.height * scale_down))
        offset_range = (math.ceil(inset_img.width * max_shift),
                        math.ceil(inset_img.height * max_shift))

        # First frame will be centered.
        first_frame = Image.new("RGBA", out_size)
        first_frame.paste(inset_img, (-round(offset_range[0]/2),
                                      -round(offset_range[1]/2)))
        first_frame = first_frame.convert("P", dither=False)

        for i in range(10):
            frame = Image.new("RGBA", out_size)
            frame.paste(inset_img, (random.randrange(-offset_range[0], 0),
                                    random.randrange(-offset_range[1], 0)))
            frame = frame.convert("P", dither=False)
            frames.append(frame)

        buff = io.BytesIO()
        first_frame.save(buff, "gif", save_all=True, append_images=frames,
                         duration=20, loop=0xffff)
        buff.seek(0)
        return buff

    @command()
    @checks.bot_needs(["attach_files"])
    async def triggered(self, ctx, *, url: converters.AnyImage=converters.AuthorAvatar):
        """TRIGGERED."""

        with ctx.typing():
            content = await fetch_image(url)
            img_buff = await ctx.bot.loop.run_in_executor(None, self.make_triggered, content)
            await ctx.send(file=discord.File(img_buff, filename="TRIGGERED.gif"))

    def make_dead(self, inset):
        inset_img = Image.open(io.BytesIO(inset))

        rip_img = Image.open(self.res.dir() + "/img/dead-already.png")

        final = Image.new("RGB", (rip_img.width, rip_img.height))

        final.paste(inset_img.resize((1024, 1024)), (448, 4))
        final.paste(rip_img, mask=rip_img)

        buff = io.BytesIO()
        final.save(buff, "jpeg")
        buff.seek(0)
        return buff

    @command()
    @checks.bot_needs(["attach_files"])
    async def dead(self, ctx, *, url: converters.AnyImage=converters.AuthorAvatar):
        """They're dead. Deal with it already.

        @roadcrosser"""
        with ctx.typing():
            content = await fetch_image(url)
            img_buff = await ctx.bot.loop.run_in_executor(None, self.make_dead, content)
            await ctx.send(file=discord.File(img_buff, filename="dead.png"))

    def make_more_jpeg(self, before):
        img = Image.open(io.BytesIO(before))

        buff = io.BytesIO()
        img.convert("RGB").save(buff, "jpeg", quality=random.randrange(1, 10))
        buff.seek(0)

        return buff

    @command()
    @checks.bot_needs(["attach_files"])
    async def needsmorejpeg(self, ctx, url=converters.LastImage):
        with ctx.typing():
            content = await fetch_image(url)
            jpeg_buff = await ctx.bot.loop.run_in_executor(None, self.make_more_jpeg, content)
            await ctx.send(file=discord.File(jpeg_buff, filename="more_jpeg.jpg"))

    def make_img_macro(self, base_image, *lines, format='png'):
        img = Image.open(base_image)

        for line in lines:
            # TODO: generate some fonts with unicode... ow
            text = line['text'].encode('utf8').decode('ascii', 'ignore')
            if not text:
                continue
            outline_width = line.get('outline_width', 0)
            font = ImageFont.truetype(
                line['font'], encoding='unic', size=line['size'])
            left, bottom, color = line['left'], line['bottom'], line['color']

            draw = ImageDraw.Draw(img)

            lines_go_up = line.get('lines_go_up', False)

            if "\n" not in text:
                avg_width, _ = font.getsize(text)
                px_per_char = max(avg_width / len(text), 1)
                text = textwrap.wrap(text, int(line.get("max_width", img.width) / px_per_char))
            else:
                text = text.split('\n')

            top_pad = 0

            sublines = text
            if lines_go_up:
                sublines = reversed(sublines)

            for subtext in sublines:
                w, h_ = font.getsize(subtext)

                h = h_ - top_pad * (-1 if lines_go_up else 1)
                top_pad += h_ * 1.2

                if outline_width:
                    outline = line['outline_color']
                    draw.text(((img.width - w - left) / 2 + outline_width,
                               img.height - h - bottom), subtext, outline, font=font)
                    draw.text(((img.width - w - left) / 2 - outline_width,
                               img.height - h - bottom), subtext, outline, font=font)
                    draw.text(((img.width - w - left) / 2, img.height -
                               h - bottom + outline_width), subtext, outline, font=font)
                    draw.text(((img.width - w - left) / 2, img.height -
                               h - bottom - outline_width), subtext, outline, font=font)
                    draw.text(((img.width - w - left) / 2 + outline_width, img.height - h - bottom - outline_width),
                              subtext, outline, font=font)
                    draw.text(((img.width - w - left) / 2 - outline_width, img.height - h - bottom + outline_width),
                              subtext, outline, font=font)
                    draw.text(((img.width - w - left) / 2 + outline_width, img.height - h - bottom + outline_width),
                              subtext, outline, font=font)
                    draw.text(((img.width - w - left) / 2 - outline_width, img.height - h - bottom - outline_width),
                              subtext, outline, font=font)
                draw.text(((img.width - w - left) / 2, img.height -
                           h - bottom), subtext, color, font=font)

        buff = io.BytesIO()
        img.save(buff, format)

        buff.seek(0)

        return buff

    @command()
    @checks.bot_needs(["attach_files"])
    async def nobully(self, ctx):
        """Anti bully ranger comes to save the day!"""
        text = ctx.message.clean_content[ctx.view.index + 1:]
        if not text:
            text = "Transform: Anti-bully Ranger!"

        img_buff = await ctx.bot.loop.run_in_executor(None, self.make_img_macro, self.res.dir() + '/img/antibully.jpg', dict(
            text=text,
            font=self.res.dir() + '/font/Aller/Aller_Bd.ttf',
            bottom=20,
            size=50,
            color='#ffffff',
            outline_color='#14466b',
            outline_width=2,
            left=0,
            lines_go_up=True,
        ))

        await ctx.send(file=discord.File(img_buff, filename="nobully.png"))

    @command()
    @checks.bot_needs(["attach_files"])
    async def nonobully(self, ctx):
        """Anti anti bully ranger comes to save? the day!"""
        text = ctx.message.clean_content[ctx.view.index + 1:]
        if not text:
            text = "PREPARE TO BE BULLIED NERDS"

        img_buff = await ctx.bot.loop.run_in_executor(None, self.make_img_macro, self.res.dir() + '/img/antiantibully.jpg', dict(
            text=text,
            font=self.res.dir() + '/font/impact/IMPACT.ttf',
            bottom=25,
            size=70,
            color='#ff0000',
            outline_color='#ffffff',
            outline_width=2,
            left=0,
            lines_go_up=True,
        ))

        await ctx.send(file=discord.File(img_buff, filename="nonobully.png"))

    @command()
    @checks.bot_needs(["attach_files"])
    async def hate(self, ctx):
        """How could you !"""
        text = ctx.message.clean_content[ctx.view.index + 1:]
        if not text:
            text = ctx.message.author.name

        img_buff = await ctx.bot.loop.run_in_executor(None, self.make_img_macro, self.res.dir() + '/img/hate_new2.png', dict(
            text=text,
            font=self.res.dir() + '/font/anime-ace/animeace.ttf',
            bottom=146,
            size=14,
            color='#000000',
            left=145,
            max_width=110,
        ))

        await ctx.send(file=discord.File(img_buff, filename="hate.png"))

    @command()
    @checks.bot_needs(["attach_files"])
    async def love(self, ctx):
        """Akarin loves you."""
        text = ctx.message.clean_content[ctx.view.index + 1:]
        if not text:
            text = ctx.message.author.name

        img_buff = await ctx.bot.loop.run_in_executor(None, self.make_img_macro, self.res.dir() + '/img/love.png', dict(
            text=text,
            font=self.res.dir() + '/font/anime-ace/animeace.ttf',
            bottom=147,
            size=12,
            color='#000000',
            left=381,
            max_width=120,
        ))

        await ctx.send(file=discord.File(img_buff, filename="love.png"))

    @command()
    @checks.bot_needs(["attach_files"])
    async def dinvite(self, ctx):
        """Memes."""
        text = ctx.message.clean_content[ctx.view.index + 1:]
        if not text:
            text = "join general"

        img_buff = await ctx.bot.loop.run_in_executor(None, self.make_img_macro, self.res.dir() + '/img/discord_invite.png', dict(
            text=text,
            font=self.res.dir() + '/font/whitney/whitney_semibold-webfont.ttf',
            bottom=0,
            size=16,
            color='#ffffff',
            left=0
        ))

        await ctx.send(file=discord.File(img_buff, filename="dinvite.png"))
