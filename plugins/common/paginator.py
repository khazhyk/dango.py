"""Paginated response."""

import asyncio
import discord

from . import utils

MAX_EMBED_DESCRIPTION_LENGTH = 2048

FIRST_PAGE = "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}"
PREV_PAGE = "\N{BLACK LEFT-POINTING TRIANGLE}"
STOP_PAGE = "\N{BLACK SQUARE FOR STOP}"
DIRECT_PAGE = "\N{INPUT SYMBOL FOR NUMBERS}"
NEXT_PAGE = "\N{BLACK RIGHT-POINTING TRIANGLE}"
LAST_PAGE = "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}"
HELP_PAGE = "\N{BLACK QUESTION MARK ORNAMENT}"
PAGINATOR_BUTTONS = [FIRST_PAGE, PREV_PAGE, STOP_PAGE, DIRECT_PAGE, NEXT_PAGE, LAST_PAGE, HELP_PAGE]
PAGINATOR_HELP_EMBED = discord.Embed(
    title="How to use paginator",
    description="""
{} - First page
{} - Previous page
{} - Stop (and remove buttons)
{} - Enter page number
{} - Next page
{} - Last page
{} - Toggle this help screen""".format(
    *PAGINATOR_BUTTONS))


def split_into_pages(units, page_length, separator):
    """Group the input into strings of max page_length."""
    units = iter(units)
    buf = next(units)
    for unit in units:
        if (len(buf) + len(separator) + len(unit)) <= page_length:
            buf += separator + unit
        else:
            yield buf
            buf = unit
    yield buf


def make_embed(title, description, idx, pages):
    """Make an embed with page number footer."""
    e = discord.Embed(title=title, description=description)
    e.set_footer(text="Page {} of {}".format(
        idx + 1, pages))
    return e


class EmbedPaginator:
    """Given a sequence of embed pages, provides pagination.

    Args:
      ctx: :class:`discord.Context`
      pages: Sequence[discord.Embed]
    """
    def __init__(self, ctx, pages):
        self.ctx = ctx
        self.pages = pages

        self.idx = 0
        self._helping = False
        self._closed = False
        self._ask_task = None
        self.msg = None

        self.dispatch = {
            FIRST_PAGE: lambda: self.set_page(0),
            PREV_PAGE: lambda: self.set_page(self.idx - 1),
            STOP_PAGE: lambda: self.close(),
            DIRECT_PAGE: lambda: self.launch_ask_task(),
            NEXT_PAGE: lambda: self.set_page(self.idx + 1),
            LAST_PAGE: lambda: self.set_page(len(self.pages) - 1),
            HELP_PAGE: lambda: self.toggle_help_page()
        }

    def embed(self):
        """Generate the embed we need."""
        if self._helping:
            return PAGINATOR_HELP_EMBED
        return self.pages[self.idx]

    async def clean_messages(self, msgs):
        """Helper to clean messages."""
        if self.ctx.channel.permissions_for(self.ctx.guild.me).manage_messages:
            await self.ctx.channel.delete_messages(msgs)
        else:
            for msg in msgs:
                if msg.author.id == self.ctx.bot.user.id:
                    await msg.delete()

    async def close(self):
        self._closed = True

    async def toggle_help_page(self):
        """Toggle help and update."""
        self._helping = not self._helping
        await self.update()

    async def set_page(self, idx=None):
        """Set page and update."""
        if 0 > idx or idx > len(self.pages) - 1:
            return
        self.idx = idx
        self._helping = False
        await self.update()

    async def update(self):
        await self.msg.edit(embed=self.embed())

    async def launch_ask_task(self):
        """Let user select a page by number in the background."""
        if self._ask_task:
            return  # They can just reuse the existing ask task... ?

        self._ask_task = utils.create_task(self.ask_for_page())
        self._ask_task.add_done_callback(self.clear_ask_task)

    def clear_ask_task(self, result):
        self._ask_task = None

    async def ask_for_page(self):
        """Prompt user for page until they succeed, cancel, or time out."""
        prompts = []
        prompts.append(
            await self.ctx.send(
                "Please enter a page number [1-{}] (or 'cancel' to cancel):".format(len(self.pages))))
        try:
            while True:
                try:
                    resp = await self.ctx.bot.wait_for(
                        'message', timeout=10,
                        check=lambda m: m.author.id == self.ctx.author.id and
                                        m.channel.id == self.ctx.channel.id)
                    prompts.append(resp)
                except asyncio.TimeoutError:
                    await self.ctx.send("Timed out waiting for page number.", delete_after=10)
                    break

                if resp.content.startswith("cancel"):
                    break

                try:
                    idx = int(resp.content) - 1
                except ValueError:
                    pass
                else:
                    if 0 <= idx < len(self.pages):
                        await self.set_page(idx)
                        break

                prompts.append(await self.ctx.send("That's not a valid page, try again!"))
        finally:
            try:
                await self.clean_messages(prompts)
            except discord.NotFound:  # Messages were deleted
                pass

    async def add_buttons(self):
        for button in PAGINATOR_BUTTONS:
            await self.msg.add_reaction(button)

    async def cleanup_buttons(self):
        if self.ctx.channel.permissions_for(self.ctx.me).manage_messages:
            await self.msg.clear_reactions()
        else:
            for button in PAGINATOR_BUTTONS:
                await self.msg.remove_reaction(button, self.ctx.me)

    async def send(self):
        """Send message and wait for reactions."""
        if len(self.pages) == 1:
            await self.ctx.send(embed=self.embed())
            return

        self.msg = await self.ctx.send(embed=self.embed())

        buttons = utils.create_task(self.add_buttons())

        try:
            while not self._closed:
                try:
                    reaction, user = await self.ctx.bot.wait_for(
                        'reaction_add', timeout=60,
                        check=lambda reaction, user: reaction.message.id == self.msg.id and
                                                     user.id == self.ctx.author.id)
                except asyncio.TimeoutError:
                    await self.close()
                else:
                    if reaction.emoji in self.dispatch:
                        if self.ctx.channel.permissions_for(self.ctx.me).manage_messages:
                            utils.create_task(self.msg.remove_reaction(reaction, user))
                        await self.dispatch[reaction.emoji]()
        finally:
            buttons.cancel()
            if self._ask_task:
                self._ask_task.cancel()
            try:
                await self.cleanup_buttons()
            except discord.NotFound:  # Message was deleted
                pass

    @classmethod
    def from_lines(cls, ctx, lines, title=""):
        """Construct a EmbedPaginator from the given lines to be joined by newline."""
        split_pages = list(split_into_pages(lines, MAX_EMBED_DESCRIPTION_LENGTH, "\n"))
        pages = [make_embed(title, page_content, idx, len(split_pages))
                      for idx, page_content in enumerate(split_pages)]
        return cls(ctx, pages)
