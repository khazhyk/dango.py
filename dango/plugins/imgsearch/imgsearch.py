from dango import config
from dango import dcog, Cog
from discord.ext.commands import command
from discord.ext.commands.errors import CommandError

from . import saucenao


async def _find_uploaded_image(channel, skip=0):
    """
    Searches the logs for a message with some sort of image attachment
    """
    async for message in channel.history(limit=100):
        for embed in message.embeds:
            if embed.thumbnail and embed.thumbnail.proxy_url:
                if skip <= 0:
                    return embed.thumbnail.proxy_url
                skip -= 1
        for attachment in message.attachments:
            if attachment.proxy_url:
                if skip <= 0:
                    return attachment.proxy_url
                skip -= 1


@dcog()
class ImageSearch(Cog):

    saucenao_api_key = config.ConfigEntry("saucenao_api_key")

    def __init__(self, config):
        self.saucenao_api_key = config.register("saucenao_api_key")

    @command()
    async def saucenao(self, ctx, skip: int=0):
        """
        Performs a reverse image query on the last uploaded
        or embedded image using the SauceNAO reverse image engine.

        Can specify number of images to skip when looking at logs
        (in case you want to look 3 images back, e.g.)

        Will only look at the previous 100 messages at most."""

        found_url = await _find_uploaded_image(ctx.channel, skip)

        if found_url is None:
            raise CommandError("No images in the last 100 messages.")

        try:
            with ctx.typing():
                s = saucenao.SauceNAO(self.saucenao_api_key.value)
                results = await s.search(found_url)

            if len(results) > 0 and results[0].similarity > 90:
                await ctx.send("Found result: \n{}\n{}".format(results[0].desc(), results[0].url()))
            else:
                await ctx.send("No results found")
        except saucenao.HTTPError as e:
            if e.resp == 429:
                await ctx.send("Rate limited :(")
            else:
                raise
