"""Paginated response."""

import asyncio
from collections import OrderedDict
import functools
import itertools

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
DOWNLOAD_PAGE = ":update:264184209617321984"


def split_into_pages(units, page_length, separator, maxlines=2000):
    """Group the input into strings of max page_length."""
    units = iter(units)
    buf = next(units)
    lines = 1
    for unit in units:
        if (len(buf) + len(separator) + len(unit)) <= page_length and lines <= maxlines:
            buf += separator + unit
            lines += 1
        else:
            yield buf
            buf = unit
            lines = 1
    yield buf


def make_embed(title, description, idx, pages):
    """Make an embed with page number footer."""
    e = discord.Embed(title=title, description=description)
    e.set_footer(text="Page {} of {}".format(
        idx + 1, pages))
    return e

def norm_emoji(emoji):
    """Output reaction style emoji."""
    if isinstance(emoji, str):
        return emoji
    if not emoji.id:
        return emoji.name
    return ":%s:%d" % (emoji.name, emoji.id)

def render_emoji(emoji):
    """Given norm_emoji, output text style emoji."""
    if emoji[0] == ":":
        return "<%s>" % emoji
    return emoji



class EmbedPaginator:
    """Given a sequence of embed pages, provides pagination.

    Provides a help page that is always last.

    Args:
      ctx: :class:`discord.Context`
      pages: Sequence[discord.Embed]
      buttons: Main action buttons
    """
    def __init__(self, ctx, pages, buttons):
        self.ctx = ctx
        self.pages = pages

        self.idx = 0
        self._helping = False
        self._closed = False
        self.msg = None

        self.dispatch = {}
        self.actions = []


        for button in buttons:
            self.register_action(*button)
        self.register_action(HELP_PAGE, lambda: self.toggle_help_page(), "Toggle this help screen")

    def register_action(self, emoji, callback, help_):
        self.dispatch[emoji] = callback
        self.actions.append((emoji, help_))

    def embed(self):
        """Generate the embed we need."""
        if self._helping:
            return discord.Embed(
                title="How to use paginator",
                description="\n".join(
                    "{} - {}".format(render_emoji(emoji), help_) for
                    emoji, help_ in self.actions))
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

    async def add_buttons(self):
        for button, _ in self.actions:
            await self.msg.add_reaction(button)

    async def cleanup_buttons(self):
        if self.ctx.channel.permissions_for(self.ctx.me).manage_messages:
            await self.msg.clear_reactions()
        else:
            for button, _ in self.actions:
                await self.msg.remove_reaction(button, self.ctx.me)

    async def cleanup(self):
        self._buttons_task.cancel()
        try:
            await self.cleanup_buttons()
        except discord.NotFound:  # Message was deleted
            pass

    async def send(self):
        """Send message and wait for reactions."""
        if len(self.pages) == 1:
            await self.ctx.send(embed=self.embed())
            return

        self.msg = await self.ctx.send(embed=self.embed())

        self._buttons_task = utils.create_task(self.add_buttons())

        try:
            while not self._closed:
                try:
                    reaction, user = await self.ctx.bot.wait_for(
                        'reaction_add', timeout=60,
                        check=lambda reaction, user: reaction.message.id == self.msg.id and
                                                     user.id == self.ctx.author.id)
                    emoji = norm_emoji(reaction.emoji)
                except asyncio.TimeoutError:
                    await self.close()
                else:
                    if emoji in self.dispatch:
                        if self.ctx.channel.permissions_for(self.ctx.me).manage_messages:
                            utils.create_task(self.msg.remove_reaction(reaction, user))
                        await self.dispatch[emoji]()
        finally:
            await self.cleanup()

class ListPaginator(EmbedPaginator):
    """List with prev/next etc.

    extra_buttons: extra buttons that come before help.
    """

    def __init__(self, ctx, pages, extra_buttons=None):
        extra_buttons = extra_buttons or []
        self._ask_task = None

        super().__init__(ctx, pages, itertools.chain((
                (FIRST_PAGE, lambda: self.set_page(0), "First page"),
                (PREV_PAGE, lambda: self.set_page(self.idx - 1), "Previous page"),
                (STOP_PAGE, self.close, "Stop (and remove buttons)"),
                (DIRECT_PAGE, self.launch_ask_task, "Enter page number"),
                (NEXT_PAGE, lambda: self.set_page(self.idx + 1), "Next page"),
                (LAST_PAGE, lambda: self.set_page(len(self.pages) - 1), "Last page")),
            extra_buttons))

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

    async def cleanup(self):
        if self._ask_task:
            self._ask_task.cancel()
            self._ask_task = None
        await super().cleanup()

    @classmethod
    def from_lines(cls, ctx, lines, title="", maxlines=2000):
        """Construct a EmbedPaginator from the given lines to be joined by newline."""
        split_pages = list(split_into_pages(lines, MAX_EMBED_DESCRIPTION_LENGTH, "\n", maxlines))
        pages = [make_embed(title, page_content, idx, len(split_pages))
                      for idx, page_content in enumerate(split_pages)]

        full_content = "\n".join(lines)
        return cls(ctx, pages)

class GroupLinesPaginator(ListPaginator):
    """EmbedPaginator from given lines joined by newline.

    Also provides a download button for the full content.
    """
    def __init__(self, ctx, lines, title="", maxlines=2000):
        split_pages = list(split_into_pages(lines, MAX_EMBED_DESCRIPTION_LENGTH, "\n", maxlines))
        pages = [make_embed(title, page_content, idx, len(split_pages))
                      for idx, page_content in enumerate(split_pages)]

        self.full_content = "\n".join(lines)

        super().__init__(ctx, pages, [
            (DOWNLOAD_PAGE, self.send_full_content, "Send this as a single message instead.")])

    async def send_full_content(self):
        """Delete our paginator and send the content instead."""
        await self.ctx.send(self.full_content)
        if self.msg:
            await self.msg.delete()
        await self.close()
