from discord.ext import commands


def is_owner():
    return commands.check(lambda ctx: ctx.author.id == 86607397321207808)
