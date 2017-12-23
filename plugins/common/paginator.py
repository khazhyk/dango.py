"""Paginated response."""

import asyncio
import discord

MAX_EMBED_DESCRIPTION_LENGTH = 2048

NEXT_PAGE = "\N{BLACK RIGHT-POINTING TRIANGLE}"
PREV_PAGE = "\N{BLACK LEFT-POINTING TRIANGLE}"
STOP_PAGE = "\N{BLACK SQUARE FOR STOP}"
DIRECT_PAGE = "\N{INPUT SYMBOL FOR NUMBERS}"
HELP_PAGE = "\N{BLACK QUESTION MARK ORNAMENT}"
FIRST_PAGE = "\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}"
LAST_PAGE = "\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}"
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
    units = iter(units)
    buf = next(units)
    for unit in units:
        if (len(buf) + len(separator) + len(unit)) <= page_length:
            buf += separator + unit
        else:
            yield buf
            buf = unit
    yield buf


class PaginatedResponse:
    """Sends an auto-paginated embed style response."""

    def __init__(self, lines, ctx, title=""):
        self.lines = lines
        self.ctx = ctx
        self.title = title

        self.pages = list(split_into_pages(lines, MAX_EMBED_DESCRIPTION_LENGTH, "\n"))
        self.idx = 0
        self.helping = False
        self.closed = False
        self._ask_task = None

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
        if self.helping:
            return PAGINATOR_HELP_EMBED
        e = discord.Embed(
            title=self.title,
            description=self.pages[self.idx])
        e.set_footer(text="Page {} of {}".format(
                self.idx + 1, len(self.pages)))
        return e

    async def clean_messages(self, msgs):
        """Helper to clean messages."""
        if self.ctx.channel.permissions_for(self.ctx.guild.me).manage_messages:
            await self.ctx.channel.delete_messages(msgs)
        else:
            for msg in msgs:
                if msg.author.id == self.ctx.bot.user.id:
                    await msg.delete()

    async def close(self):
        self.closed = True

    async def toggle_help_page(self):
        """Toggle help and update."""
        self.helping = not self.helping
        await self.update()

    async def set_page(self, idx=None):
        """Set page and update."""
        if 0 > idx or idx > len(self.pages) - 1:
            return
        self.idx = idx
        self.helping = False
        await self.update()

    async def update(self):
        await self.msg.edit(embed=self.embed())

    async def launch_ask_task(self):
        """Let user select a page by number in the background."""
        if self._ask_task:
            return  # They can just reuse the existing ask task... ?

        self._ask_task = asyncio.ensure_future(self.ask_for_page())
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

                if 0 <= idx < len(self.pages):
                    await self.set_page(idx)
                    break

                prompts.append(await self.ctx.send("That's not a valid page, try again!"))
        finally:
            await self.clean_messages(prompts)

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

        buttons = asyncio.ensure_future(self.add_buttons())

        try:
            while not self.closed:
                try:
                    reaction, user = await self.ctx.bot.wait_for(
                        'reaction_add', timeout=60,
                        check=lambda reaction, user: reaction.message.id == self.msg.id and
                                                     user.id == self.ctx.author.id)
                except asyncio.TimeoutError:
                    self.close()
                else:
                    if reaction.emoji in self.dispatch:
                        if self.ctx.channel.permissions_for(self.ctx.me).manage_messages:
                            asyncio.ensure_future(self.msg.remove_reaction(reaction, user))
                        await self.dispatch[reaction.emoji]()
        finally:
            buttons.cancel()
            if self._ask_task:
                self._ask_task.cancel()
            await self.cleanup_buttons()
