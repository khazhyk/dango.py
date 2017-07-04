from dango import plugin
from discord.ext.commands import command


@plugin()
class Reload:

    @command()
    async def reload(self, ctx, extension):
        ctx.bot.unload_extension(extension)
        ctx.bot.load_extension(extension)
        await ctx.send("\N{THUMBS UP SIGN}")
