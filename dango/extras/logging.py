from concurrent.futures import ThreadPoolExecutor
import csv
import datetime
import json
import logging
import os
import gzip
import shutil

from dango import dcog
import discord
from discord.ext import commands

COLUMNS = (
    "human_guild_name",
    "human_channel_name",
    "human_author_name",
    "human_content",
    "embeds",
    "attachment_urls",
    "guild_id",
    "channel_id",
    "author_id",
    "message_id",
    "content",
    "created_at",
    "edited_at",
)

log = logging.getLogger(__name__)

class RotatingGzipFile:
    def __init__(self, basename, max_size=100<<20):
        self.basename = basename
        self.max_size = max_size

        self.stream = open(basename, 'a', encoding="utf8")
        self.writer = csv.writer(self.stream, lineterminator='\n')

        self._executor = ThreadPoolExecutor(max_workers=1)

    def close(self):
        self.stream.close()
        self.writer = None

    def _background_compress(self, archive_filename):
        with open(archive_filename, 'rb') as f_in:
            with gzip.open(archive_filename + ".gz", 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        os.remove(archive_filename)

    def _background_compress_log(self, fut):
        try:
            if fut.exception():
                e = fut.exception()
                log.error("", exc_info=(type(e), e, e.__traceback__))
        except asyncio.CancelledError as e:
            log.debug("", exc_info=(type(e), e, e.__traceback__))

    def rollover(self):
        try:
            self.stream.close()
            self.writer = None
            archive_filename = "{}.{:%Y%m%d%H%M%S}".format(
                self.basename, datetime.datetime.utcnow())
            os.rename(self.basename, archive_filename)

            fut = self._executor.submit(
                    self._background_compress, archive_filename)
            fut.add_done_callback(self._background_compress_log)

        finally:
            # If we fail to compress or rename, just continue appending...
            self.stream = open(self.basename, 'a', encoding="utf8")
            self.writer = csv.writer(self.stream, lineterminator='\n')

    def should_rollover(self, content):
        if self.max_size > 0 and (self.stream.tell() + len(content) + 1) > self.max_size:
            return True
        return False

    def emit(self, content):
        """Write row to file"""
        if self.should_rollover(content):
            self.rollover()

        self.writer.writerow(content)
        self.stream.flush()


@dcog(pass_bot=True)
class Logging:

    def __init__(self, bot, config):
        log_dir = config.register("log_dir").value
        log_basename = config.register("log_basename", default="discord_messages.csv").value

        if not os.path.exists(log_dir):
            os.mkdir(log_dir)

        self.bot = bot
        self.logger = RotatingGzipFile(os.path.join(log_dir, log_basename))
        self.statefile = RotatingGzipFile(os.path.join(log_dir, log_basename + ".state"))

        bot.add_listener(self.on_first_message, "on_message")
        self.last_message_id=None
    
    async def on_first_message(self, message):
        self.statefile.emit((
            "start_message",
            message.id,
            self.bot.user.id,
            COLUMNS
        ))
        self.bot.remove_listener(self.on_first_message, "on_message")

    def __unload(self):
        self.statefile.emit((
            "last_message",
            self.last_message_id,
            self.bot.user.id,
        ))
        self.statefile.close()
        self.logger.close()

    async def on_raw_message_edit(self, raw):
        if self.bot._connection._get_message(raw.message_id):
            return

        try:
            if 'author' in raw.data:
                author_name = "%s#%s" % (raw.data['author']['username'],raw.data['author']['discriminator'])
                author_id = raw.data['author']['id']
            else:
                author_name = None
                author_id = None

            self.logger.emit((
                None,
                None,
                author_name,
                None,
                json.dumps(raw.data['embeds']),
                json.dumps([d['url'] for d in raw.data.get('attachments', [])]),
                raw.data.get('guild_id'),
                raw.data['channel_id'],
                author_id,
                raw.data['id'],
                raw.data.get('content'),
                # Note: these timestamps are of a different format than
                # datetimes given by discord
                raw.data.get('timestamp'),
                raw.data.get('edited_timestamp'),
                ))
        except:
            logging.exception("Unable to log raw edit %s", raw.data)

    def _record_message(self, message):
        if isinstance(message.channel, discord.DMChannel):
            channel_name = "@%s" % message.channel.recipient.name
        else:
            channel_name = message.channel.name

        self.logger.emit((
            message.guild and message.guild.name,
            channel_name,
            "%s#%s" % (message.author.name, message.author.discriminator),
            message.clean_content,
            json.dumps([e.to_dict() for e in message.embeds]),
            json.dumps([a.url for a in message.attachments]),
            message.guild and message.guild.id,
            message.channel.id,
            message.author.id,
            message.id,
            message.system_content,
            message.created_at,
            message.edited_at
        ))

    async def on_message_edit(self, before, message):
        self._record_message(message)

    async def on_message(self, message):
        self.last_message_id = message.id
        self._record_message(message)
