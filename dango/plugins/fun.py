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
import datetime
import concurrent.futures as cf
import io
import inspect
import math
import os
import random
import subprocess
import tempfile
import time

import aiohttp
import yarl
from dango import dcog, Cog
import discord
from discord.ext.commands import command, check, errors, group, max_concurrency, BucketType
from PIL import Image, ImageFont, ImageDraw, ImageOps, ImageFilter, ImageChops
import textwrap

from .common import converters
from .common import checks
from .common import img_utils
from .common.utils import AliasCmd, fetch_image

ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'mp4'}


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
        self.process_executor = cf.ProcessPoolExecutor()

    @command()
    async def corrupt(self, ctx, *, user: converters.UserMemberConverter=None):
        """Corrupt a user's avatar."""
        user = user or ctx.message.author
        img_buff = bytearray(await fetch_image(user.avatar.replace(format="jpg")))
        for i in range(random.randint(5, 25)):
            img_buff[random.randint(0, len(img_buff))] = random.randint(1, 254)
        await ctx.send(file=discord.File(io.BytesIO(img_buff), filename="img.jpg"))

    @staticmethod
    def _gifmap(avys):
        """stolen from cute."""
        maxres = 200

        imgs = []

        for avy in avys:
            avy = Image.open(avy).resize((maxres,maxres), resample=Image.BICUBIC)
            avydata = avy.load()
            avydata = [[(x,y),avydata[x,y]] for y in range(maxres) for x in range(maxres)]
            avydata.sort(key = lambda c : get_lum(*c[1]))

            imgs.append(avydata)

        sequence = [0] + [1/(1+(2.5**-i)) for i in range(-5,6,1)] + [1]

        if len(avys) > 2:
            imgs.append(imgs[0])

        base_palette = imgs[0]
        frames = []
        for j, im in enumerate(imgs[1:]):
            for m in sequence:
                base = Image.new('RGBA', (maxres,maxres))
                basedata = base.load()
                for i, d in enumerate(imgs[j]):
                    if m == 0:
                        x, y = d[0]
                    elif m == 1:
                        x, y = im[i][0]
                    else:
                        x1, y1 = d[0]
                        x2, y2 = im[i][0]
                        x, y = round(x1 + (x2 - x1)*m), round(y1 + (y2 - y1) * m)

                    if x < 0 or x >= maxres or y < 0 or y >= maxres:
                        continue
                        
                    basedata[x, y] = base_palette[i][1]
                frames.append(base)

        if len(avys) == 2:
            frames = frames + frames[::-1]

        durations = [280] + [70] * 11 + [280]
        durations *= len(avys)

        b = io.BytesIO()
        frames[0].save(b, 'gif', save_all=True, append_images=frames[1:], loop=0, duration=durations)
        b.seek(0)
        return b

    @command()
    @checks.bot_needs(["attach_files"])
    async def colormap3(self, ctx, source: discord.Member, *dest: discord.Member):
        """Hello my name is Koishi."""
        if len(dest) == 0:
            dest = [ctx.author]

        start = time.time()
        async with ctx.typing():
            avys = await asyncio.gather(*[fetch_image(t.avatar.replace(format="png")) for t in [source] + list(dest)])
            avys = [io.BytesIO(a) for a in avys]
            img_buff = await asyncio.get_running_loop().run_in_executor(None,
                    self._gifmap, avys
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
        res = await asyncio.get_running_loop().run_in_executor(None, self.make_dot)
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
        async with ctx.typing():
            content = await fetch_image(url)
            img_buff = await asyncio.get_running_loop().run_in_executor(None, self.make_dont_image, content)

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
        async with ctx.typing():
            content = await fetch_image(url)
            img_buff = await asyncio.get_running_loop().run_in_executor(None, self.make_rip, content)
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

        async with ctx.typing():
            content = await fetch_image(url)
            img_buff = await asyncio.get_running_loop().run_in_executor(None, self.make_triggered, content)
            await ctx.send(file=discord.File(img_buff, filename="TRIGGERED.gif"))

    @command()
    @checks.bot_needs(["attach_files"])
    async def glitch(self, ctx, *, url: converters.AnyImage=converters.AuthorAvatar):
        def make_glitch(inset):
            def corrupt(img_buff):
                img_buff = bytearray(img_buff)
                for i in range(random.randint(1, 25)):
                    img_buff[random.randint(0, len(img_buff) - 1)] = random.randint(1, 254)
                return img_buff

            # First, convert to jpeg
            first_frame = Image.open(io.BytesIO(inset))
            jpeg_buff = io.BytesIO()
            if first_frame.mode == "RGBA":
                jpeg_frame = Image.new("RGBA", (first_frame.width, first_frame.height), "Black")
                jpeg_frame.paste(first_frame, (0,0), mask=first_frame)
            else:
                jpeg_frame = first_frame
            jpeg_frame = jpeg_frame.convert("RGB")
            jpeg_frame.save(jpeg_buff, "jpeg")
            jpeg_buff.seek(0)
            inset = jpeg_buff.read()

            # Then corrupt a bit...
            frames = []
            for _ in range(50):
                try:
                    frame = Image.open(io.BytesIO(corrupt(inset)))
                    frame = frame.convert("P", dither=False)
                except OSError:
                    continue
                frames.append(frame)

            buff = io.BytesIO()
            first_frame.save(buff, "gif", save_all=True, append_images=frames,
                             duration=100, loop=0xffff)
            buff.seek(0)
            return buff

        async with ctx.typing():
            content = await fetch_image(url)
            img_buff = await asyncio.get_running_loop().run_in_executor(None, make_glitch, content)
            await ctx.send(file=discord.File(img_buff, filename="glitch.gif"))

    @staticmethod
    def make_crab_rave(res_dir, text, working_dir):
        """make crab crab_rave.

        Create static text file in tempfile
        Pass base, pallete, and text to ffmpeg
        yay.

        To generate pallete (for new baselines):
        ffmpeg -i '/g/My Drive/spoopybotfiles/res/img/crab_rave_base.gif' -vf palettegen pallete.png
        To generate output:
        ffmpeg -i '/g/My Drive/spoopybotfiles/res/img/crab_rave_base.gif' -i /c/Users/khazhy/Pictures/Untitled.png -i pallete.png -filter_complex "[0:v][1:v] overlay=25:25[x]; [x] [2:v]paletteuse" -pix_fmt yuv420p output.gif
        """
        base_video = res_dir + "/img/crab_rave_200p.mkv"

        # PIL can't get size of image, so ffprobe
        canvas_size = subprocess.check_output([
            "ffprobe", "-v" , "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "default=nw=1:nk=1",
            base_video
            ], encoding="utf8")
        canvas_size = tuple(map(int, canvas_size.strip().split("\n")))

        # Simple brute force font size selection...
        font_height = 28
        line_height = font_height * 1.2
        font = ImageFont.truetype(res_dir + '/font/avnir/AvenirLTStd-Book.otf',
                                  encoding='unic',size=font_height)
        lines = img_utils.raster_font_textwrap(text, canvas_size[0], font)
        estimated_height = line_height * len(lines)
        while estimated_height > canvas_size[1] and font_height > 1:
            font_height -= 1
            line_height = font_height * 1.2
            font = ImageFont.truetype(res_dir + '/font/avnir/AvenirLTStd-Book.otf',
                                      encoding='unic',size=font_height)
            lines = img_utils.raster_font_textwrap(text, canvas_size[0], font)
            estimated_height = line_height * len(lines)

        # Draw and save to temporary file for ffmpeg to read
        text_image_file = os.path.join(working_dir, "text.png")
        im = Image.new("RGBA", canvas_size)
        draw = ImageDraw.Draw(im)

        center_x, center_y = tuple(x/2 for x in canvas_size)
        # Initial top pad to center vertically
        top_pad = -(line_height * len(lines) / 2) + (line_height - font_height)
        for line in lines:
            left, top, right, bottom = font.getbbox(line)
            text_x = right - left
            text_y = bottom - top
            text_pos = (center_x - text_x/2, center_y + top_pad)
            top_pad += line_height
            # We draw one by one because it lets me do custom centering
            img_utils.draw_text_dropshadow(
                draw, text_pos, line, "white", "#222", (1, 1), font=font)
        im.save(text_image_file)

        subprocess.check_call([
            "ffmpeg", "-i", base_video, "-i", text_image_file,
            "-filter_complex", "[0:v][1:v] overlay=0:0",
            "-pix_fmt", "yuv420p", os.path.join(working_dir, "out.mp4")
            ])

    @command(aliases=["cr"])
    @checks.bot_needs(["attach_files"])
    @max_concurrency(2, per=BucketType.guild, wait=False)
    async def crab_rave(self, ctx, *, content="DISCORD IS DEAD"):
        """DISCORD IS DEAD."""
        async with ctx.typing():
            with tempfile.TemporaryDirectory(prefix="crab_rave_nonsense") as working_dir:
                await asyncio.get_running_loop().run_in_executor(self.process_executor, self.make_crab_rave, self.res.dir(), content, working_dir)
                await ctx.send(file=discord.File(
                    os.path.join(working_dir, "out.mp4"), filename="{}.mp4".format(content)))

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
        async with ctx.typing():
            content = await fetch_image(url)
            img_buff = await asyncio.get_running_loop().run_in_executor(None, self.make_dead, content)
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
        async with ctx.typing():
            content = await fetch_image(url)
            jpeg_buff = await asyncio.get_running_loop().run_in_executor(None, self.make_more_jpeg, content)
            await ctx.send(file=discord.File(jpeg_buff, filename="more_jpeg.jpg"))

    def make_img_macro(self, base_image, *lines, format='png'):
        img = Image.open(base_image)

        for line in lines:
            # TODO: generate some fonts with unicode... ow
            text = line['text'].encode('utf8').decode('ascii', 'ignore')
            if not text:
                continue
            font = ImageFont.truetype(
                line['font'], encoding='unic', size=line['size'])
            left, bottom, color = line['left'], line['bottom'], line['color']

            draw = ImageDraw.Draw(img)

            lines_go_up = line.get('lines_go_up', False)

            text = img_utils.raster_font_textwrap(text, int(line.get("max_width", img.width)), font)

            top_pad = 0

            sublines = text
            if lines_go_up:
                sublines = reversed(sublines)

            for subtext in sublines:
                left, top, right, bottom = font.getbbox(subtext)
                w = right - left
                h_ = bottom - top

                h = h_ - top_pad * (-1 if lines_go_up else 1)
                top_pad += h_ * 1.2

                from_left = (img.width - w - left) / 2
                from_top = img.height - h - bottom

                img_utils.draw_text_outline(draw,
                    (from_left, from_top), subtext, color,
                    line.get('outline_color'), line.get('outline_width', 0),
                    font=font)

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

        img_buff = await asyncio.get_running_loop().run_in_executor(None, self.make_img_macro, self.res.dir() + '/img/antibully.jpg', dict(
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

        img_buff = await asyncio.get_running_loop().run_in_executor(None, self.make_img_macro, self.res.dir() + '/img/antiantibully.jpg', dict(
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

        img_buff = await asyncio.get_running_loop().run_in_executor(None, self.make_img_macro, self.res.dir() + '/img/hate_new2.png', dict(
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

        img_buff = await asyncio.get_running_loop().run_in_executor(None, self.make_img_macro, self.res.dir() + '/img/love.png', dict(
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

        img_buff = await asyncio.get_running_loop().run_in_executor(None, self.make_img_macro, self.res.dir() + '/img/discord_invite.png', dict(
            text=text,
            font=self.res.dir() + '/font/whitney/whitney_semibold-webfont.ttf',
            bottom=0,
            size=16,
            color='#ffffff',
            left=0
        ))

        await ctx.send(file=discord.File(img_buff, filename="dinvite.png"))

    @command()
    async def voteban(self, ctx, member: converters.UserMemberConverter):
        if ctx.author == member:
            await ctx.send(f"{ctx.author.mention} was an imposter.")
            return

        voting_ends = discord.utils.utcnow() + datetime.timedelta(seconds=30)

        helyea = discord.PartialEmoji.from_str(":helYea:236243426662678528")
        helna = discord.PartialEmoji.from_str(":helNa:239120424938504192")

        msg = await ctx.send(
            f"""{ctx.author.mention} has started a poll to ban {member.mention}!
            
            React with {helyea} to vote to ban
            React with {helna} to vote to acquit

            Voting ends {discord.utils.format_dt(voting_ends, style="R")}
            """, allowed_mentions=discord.AllowedMentions.none())
        await msg.add_reaction(helyea)
        await msg.add_reaction(helna)
        await discord.utils.sleep_until(voting_ends)

        msg_again = await ctx.fetch_message(msg.id)
        votes_for = votes_against = 0
        for reaction in msg_again.reactions:
            if reaction.emoji == helyea:
                votes_for = reaction.count
            elif reaction.emoji == helna:
                votes_against = reaction.count

        if votes_for > votes_against:
            await ctx.send(f"{member.mention} has been kicked off the island!!!!111!")
        else:
            await ctx.send(f"{ctx.author.mention} has been kicked off the island for false accusations!")

        await msg.edit(content=msg.content.replace("ends", "ended"), allowed_mentions=discord.AllowedMentions.none())