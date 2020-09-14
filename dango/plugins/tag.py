"""Tags! Create, uncreate, show, hide, whatever!."""

from discord.ext.commands import group, errors

from dango.core import dcog, Cog


@dcog(depends=["Database"])
class Tags(Cog):

    def __init__(self, config, db):
        del config
        self.db = db
        super().__init__()

    async def lookup_tag(self):
        pass

    @group(invoke_without_command=True)
    async def tag(self, ctx, *, tag_name):
        await ctx.send("Tag alone")

    @tag.command()
    async def create(self, ctx, tag_name, *, content):
        await ctx.send("create")

    @tag.command()
    async def edit(self, ctx, tag_name, *, new_content):
        pass

    @tag.command()
    async def remove(self, ctx, tag_name):
        pass

    @tag.command()
    async def info(self, ctx, tag_name):
        pass
