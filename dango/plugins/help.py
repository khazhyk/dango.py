import discord

def setup(bot):
    bot.help_command = discord.ext.commands.DefaultHelpCommand(dm_help=None)
