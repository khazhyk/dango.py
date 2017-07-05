from dango import checks
from dango import dcog
from discord.ext.commands import command


@dcog()
class Reload:

    @command()
    @checks.is_owner()
    async def reload(self, ctx, extension):
        """Reloads an extension."""
        try:
            ctx.bot.unload_extension(extension)
            ctx.bot.load_extension(extension)
        except:
            await ctx.send("\N{THUMBS DOWN SIGN}")
            raise
        else:
            await ctx.send("\N{THUMBS UP SIGN}")
