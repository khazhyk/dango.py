import asyncio
import collections
import copy
import itertools
import logging
import struct
from datetime import datetime
from datetime import timedelta

from dango import dcog
from dango import checks
from dango import utils
import discord
from discord.ext import commands
from discord.ext.commands import command
from discord.ext.commands import group

from plugins.database import multi_insert_str

log = logging.getLogger(__name__)

REDIS_NICK_NONE = (b'NoneNoneNoneNoneNoneNoneNoneNoneNoneNoneNoneNoneNoneNoneNone'
                   b'NoneNoneNoneNoneNoneNoneNoneNoneNoneNoneNoneNone')
PG_ARG_MAX = 32767


class LastSeenTuple(collections.namedtuple(
        'LastSeenTuple', ('last_seen', 'last_spoke', 'server_last_spoke'))):
    __slots__ = ()

    def __new__(cls, last_seen, last_spoke, server_last_spoke=None):
        return super().__new__(cls, last_seen, last_spoke, server_last_spoke)


def name_key(member):
    return "spoo:last_username:{0.id}".format(member)


def nick_key(member):
    return "spoo:last_nickname:{0.id}:{0.guild.id}".format(member)


def name_from_redis(name_or):
    if name_or == REDIS_NICK_NONE:
        return None
    return name_or.decode('utf8')


def name_to_redis(name_or):
    if name_or is None:
        return REDIS_NICK_NONE
    return name_or.encode('utf8')


def last_seen_key(member):
    return "spoo:last_seen:{0.id}".format(member)


def last_spoke_key(member):
    return "spoo:last_spoke:{0.id}".format(member)


def member_last_spoke_key(member):
    return "spoo:last_spoke:{0.id}:{0.guild.id}".format(member)


def datetime_to_redis(datetime_obj):
    return struct.pack('q', int(datetime_obj.timestamp() * 1000))


def datetime_from_redis(bytes_obj):
    if bytes_obj is None:
        return None
    return datetime.fromtimestamp(struct.unpack('q', bytes_obj)[0] / 1000)


@dcog(depends=['Database', 'Redis'], pass_bot=True)
class Tracking:

    def __init__(self, bot, database, redis):
        self.bot = bot
        self.database = database
        self.redis = redis

        self.batch_presence_updates = []
        self.batch_name_updates = []
        self.batch_presence_task = asyncio.ensure_future(self.batch_presence())
        self.batch_name_task = asyncio.ensure_future(self.batch_name())

    def __unload(self):
        self.batch_presence_task.cancel()
        self.batch_name_task.cancel()

    async def batch_presence(self):
        try:
            while True:
                await self.do_batch_presence_update()
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            await self.do_batch_presence_update()
            if self.batch_presence_updates:
                log.error("Dropping %d presences!", len(self.batch_presence_updates) / 2)
        except:
            log.exception("Exception during presence update task!")
            raise

    async def batch_name(self):
        try:
            while True:
                await self.do_batch_names_update()
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            await self.do_batch_names_update()
            if self.batch_name_updates:
                log.error("Dropping %d name updates!", len(self.batch_name_updates))
        except:
            log.exception("Exception during name update task!")
            raise

    # Name tracking

    async def _last_username(self, member):
        """Fetch last username.

        Remember misses in redis.
        """
        async with self.redis.acquire() as conn:
            last_name = await conn.get(name_key(member))
        if last_name:
            return name_from_redis(last_name)

        async with self.database.acquire() as conn:
            row = await conn.fetchval(
                "SELECT name from namechanges WHERE id = $1 "
                "ORDER BY idx DESC LIMIT 1", str(member.id))
            last_name = row and row.decode('utf8')
        async with self.redis.acquire() as conn:
            await conn.set(name_key(member), name_to_redis(last_name))
        return last_name

    async def _last_nickname(self, member):
        """Fetch last nickname.

        Remember misses in redis. We will not store None as the first nickname
        entry for a user in the database, but should remember it in redis if
        not set.
        """
        async with self.redis.acquire() as conn:
            last_name = await conn.get(nick_key(member))
        if last_name:
            return name_from_redis(last_name)

        async with self.database.acquire() as conn:
            row = await conn.fetchval(
                "SELECT name from nickchanges WHERE id = $1 "
                "AND server_id = $2 ORDER BY idx DESC LIMIT 1",
                str(member.id), str(member.guild.id))
            last_name = row and row.decode('utf8')
        async with self.redis.acquire() as conn:
            await conn.set(nick_key(member), name_to_redis(last_name))
        return last_name

    async def names_for(self, member, since: timedelta=None):
        async with self.database.acquire() as conn:
            params = []
            query = (
                "SELECT name FROM namechanges "
                "WHERE id = $1 "
                )
            params.append(str(member.id))  # TODO - convert schema to BigInt
            if since:
                query += "AND date >= $2 "
                params.append((datetime.utcnow() - since))
            query += "ORDER BY idx DESC"

            rows = await conn.fetch(query, *params)

            if rows:
                return [item[0].decode('utf8') for item in rows]
            last_name = await self._last_username(member)
            if last_name:
                return [last_name]
            return []

    async def nicks_for(self, member, since: timedelta=None):
        async with self.database.acquire() as conn:
            params = []
            query = (
                "SELECT name FROM nickchanges "
                "WHERE id = $1 AND server_id = $2"
                )
            # TODO - convert schema to BigInt
            params.extend((str(member.id), str(member.guild.id)))
            if since:
                query += "AND date >= $3 "
                params.append((datetime.utcnow() - since))
            query += "ORDER BY idx DESC"

            rows = await conn.fetch(query, *params)

            if rows:
                return [item[0].decode('utf8') for item in rows if item[0]]
            last_name = await self._last_nickname(member)
            if last_name:
                return [last_name]
            return []

    async def update_name_change(self, member):
        last_name = await self._last_username(member)
        if last_name == member.name:
            return

        async with self.database.acquire() as conn:
            name, idx = await conn.fetchrow(
                "SELECT name, idx FROM namechanges WHERE id = $1"
                "ORDER BY idx DESC LIMIT 1", str(member.id)
                ) or (None, 0)
            # TODO - look at asyncpg custom type conversions
            if name is not None:
                name = name.decode('utf8')
            if name != member.name:
                await conn.execute(
                    "INSERT INTO namechanges (id, name, idx) "
                    "VALUES ($1, $2, $3) ON CONFLICT (id, idx) DO NOTHING",
                    str(member.id), member.name.encode('utf8'), idx + 1)
        async with self.redis.acquire() as conn:
            await conn.set(name_key(member), name_to_redis(member.name))

    async def update_nick_change(self, member):
        last_nick = await self._last_nickname(member)
        if last_nick == member.nick:
            return

        async with self.database.acquire() as conn:
            name, idx = await conn.fetchrow(
                "SELECT name, idx FROM nickchanges WHERE id = $1 "
                "AND server_id = $2 ORDER BY idx DESC LIMIT 1",
                str(member.id), str(member.guild.id)
                ) or (None, 0)
            if name is not None:
                name = name.decode('utf8')

            if name != member.nick:
                await conn.execute(
                    "INSERT INTO nickchanges (id, server_id, name, idx) "
                    "VALUES ($1, $2, $3, $4) "
                    "ON CONFLICT (id, server_id, idx) DO NOTHING",
                    str(member.id), str(member.guild.id),
                    member.nick and member.nick.encode('utf8'), idx + 1)
        async with self.redis.acquire() as conn:
            await conn.set(nick_key(member), name_to_redis(member.nick))

    def queue_batch_names_update(self, member):
        self.batch_name_updates.append((
            member, datetime.utcnow()))

    async def do_batch_names_update(self):
        """Batch update member names and nicks.

        - Fetch everything on redis.
        - Anything that isn't on redis, or mismatched on redis, fetch from DB.
        - Insert into DB all new nicks and names (in order)
        - Update all redis-mismatched entries on redis.
        """
        # We process a maximum of 32767/5 elements at once to resepct psql arg limit
        all_updates = self.batch_name_updates
        self.batch_name_updates = []

        while all_updates:
            updates = all_updates[:6553]
            all_updates = all_updates[6553:]
            # TODO - make the redis lookup similar to the iteration update for calculating inserts
            pending_name_updates, pending_nick_updates = await self.batch_get_redis_mismatch(updates)

            current_names, current_nicks = await self.batch_get_current_names(
                pending_name_updates, pending_nick_updates)

            name_inserts, nick_inserts, current_names, current_nicks = await self.calculate_needed_inserts(
                    pending_name_updates, pending_nick_updates, current_names, current_nicks)

            await self.batch_insert_name_updates(name_inserts, nick_inserts)
            await self.batch_set_redis_names(current_names, current_nicks)

    async def batch_get_redis_mismatch(self, updates):
        assert 0 < len(updates) <= 50000  # Limit mget to 100k keys.
        count = len(updates)

        name_redis_keys = (name_key(m) for m, _ in updates)
        nick_redis_keys = (nick_key(m) for m, _ in updates)

        async with self.redis.acquire() as conn:
            res = await conn.mget(*name_redis_keys, *nick_redis_keys)

        names = res[:count]
        nicks = res[count:]

        pending_name_updates = []
        pending_nick_updates = []

        for idx in range(count):
            member, timestamp = updates[idx]
            name = names[idx]
            nick = nicks[idx]

            if not name or name_from_redis(name) != member.name:
                pending_name_updates.append((member, timestamp))
            if not nick or name_from_redis(nick) != member.nick:
                pending_nick_updates.append((member, timestamp))

        return pending_name_updates, pending_nick_updates

    async def batch_get_current_names(self, pending_name_updates, pending_nick_updates):
        async with self.database.acquire() as conn:
            name_rows = await conn.fetch(
                "SELECT id, name, idx FROM namechanges "
                "WHERE id = ANY($1) ORDER BY idx ASC",
                [str(m.id) for m, _ in pending_name_updates])
            nick_rows = await conn.fetch(
                "SELECT id, server_id, name, idx FROM nickchanges "
                "WHERE id = ANY($1) AND server_id = ANY($2) ORDER BY idx ASC",
                [str(m.id) for m, _ in pending_nick_updates],
                [str(m.guild.id) for m, _ in pending_nick_updates])

        current_names = {
            int(m_id): (m_name and m_name.decode('utf8'), m_idx)
            for m_id, m_name, m_idx in name_rows
        }

        current_nicks = {
            (int(m_id), int(m_server)): (m_name and m_name.decode('utf8'), m_idx)
            for m_id, m_server, m_name, m_idx in nick_rows
        }

        return current_names, current_nicks

    async def calculate_needed_inserts(
            self, pending_name_updates, pending_nick_updates, curr_names, curr_nicks):
        name_inserts = []
        nick_inserts = []

        for member, timestamp in pending_name_updates:
            curr_name, curr_idx = curr_names.get(member.id) or (None, 0)

            if curr_name != member.name:
                curr_idx += 1
                name_inserts.append(
                    (str(member.id), member.name.encode('utf8'), curr_idx, timestamp))
            # Update current_names in order, we will send to redis.
            curr_names[member.id] = (member.name, curr_idx)

        for member, timestamp in pending_nick_updates:
            curr_name, curr_idx = curr_nicks.get((member.id, member.guild.id)) or (None, 0)

            if curr_name != member.nick:
                curr_idx += 1
                nick_inserts.append(
                    (str(member.id), str(member.guild.id),
                     member.nick and member.nick.encode('utf8'), curr_idx, timestamp))
            # Update current_nicks in order, we will send to redis.
            curr_nicks[member.id, member.guild.id] = (member.nick, curr_idx)
        return name_inserts, nick_inserts, curr_names, curr_nicks

    async def batch_insert_name_updates(self, name_inserts, nick_inserts):
        assert len(name_inserts) < (PG_ARG_MAX // 4)
        assert len(nick_inserts) < (PG_ARG_MAX // 5)
        async with self.database.acquire() as conn:
            if name_inserts:
                await conn.execute(
                    "INSERT INTO namechanges (id, name, idx, date) "
                    "VALUES %s ON CONFLICT (id, idx) DO NOTHING" % (
                            multi_insert_str(name_inserts)
                        ),
                    *itertools.chain(*name_inserts)
                    )
            if nick_inserts:
                await conn.execute(
                    "INSERT INTO nickchanges (id, server_id, name, idx, date) "
                    "VALUES %s ON CONFLICT (id, server_id, idx) DO NOTHING" % (
                            multi_insert_str(nick_inserts)
                        ),
                    *itertools.chain(*nick_inserts)
                    )

    async def batch_set_redis_names(self, current_names, current_nicks):
        assert len(current_names) <= 50000
        assert len(current_nicks) <= 50000
        if not current_names and not current_nicks:
            return

        async with self.redis.acquire() as conn:
            user_keys = (
                ("spoo:last_username:%d" % m_id, name_to_redis(m_name))
                for m_id, (m_name, _) in current_names.items())
            name_keys = (
                ("spoo:last_nickname:%d:%d" % (m_id, m_server), name_to_redis(m_name))
                for (m_id, m_server), (m_name, _) in current_nicks.items())
            await conn.mset(*itertools.chain(
                *user_keys, *name_keys))

    # Presence tracking

    async def last_seen(self, member):
        keys = [
            last_seen_key(member),
            last_spoke_key(member)
        ]
        if hasattr(member, 'guild'):
            keys.append(member_last_spoke_key(member))

        async with self.redis.acquire() as conn:
            results = map(datetime_from_redis, await conn.mget(*keys))

        return LastSeenTuple(*results)

    async def update_last_update(self, member):
        async with self.redis.acquire() as conn:
            await conn.set(
                last_seen_key(member), datetime_to_redis(datetime.utcnow()))

    async def update_last_message(self, member):
        update_time = datetime_to_redis(datetime.utcnow())
        pairs = [
            last_seen_key(member), update_time,
            last_spoke_key(member), update_time
        ]
        if hasattr(member, 'guild'):
            pairs.extend((member_last_spoke_key(member), update_time))
        async with self.redis.acquire() as conn:
            await conn.mset(*pairs)

    def queue_batch_last_update(self, member):
        self.batch_presence_updates.extend((
            last_seen_key(member),
            datetime_to_redis(datetime.utcnow())))

    async def do_batch_presence_update(self):
        updates = self.batch_presence_updates
        self.batch_presence_updates = []
        if not updates:
            return
        async with self.redis.acquire() as conn:
            while updates:
                await conn.mset(*updates[:50000])
                updates = updates[50000:]

    # Event registration

    async def on_guild_join(self, guild):
        for member in copy.copy(list(guild.members)):
            self.queue_batch_names_update(member)
            if member.status is not discord.Status.offline:
                self.queue_batch_last_update(member)

    async def on_member_update(self, before, member):
        self.queue_batch_last_update(member)
        self.queue_batch_names_update(member)

    async def on_member_join(self, member):
        await asyncio.gather(
            self.update_last_update(member),
            self.update_name_change(member),
            self.update_nick_change(member)
        )

    async def on_message(self, message):
        await self.update_last_message(message.author)

    async def on_typing(self, channel, user, when):
        await self.update_last_update(user)

    async def on_raw_message_edit(self, message_id, data):
        if 'author' not in data:
            return  # This is a automatic discord embed edit, ignore.

        if data['author']['discriminator'] == '0000':
            return  # Ignore webhooks.

        channel = self.bot.get_channel(int(data['channel_id']))
        if isinstance(channel, discord.abc.GuildChannel):
            author = channel.guild.get_member(int(data['author']['id']))
        else:
            author = self.bot.get_user(int(data['author']['id']))
        await self.update_last_message(author)

    async def on_raw_reaction_add(self, emoji, message_id, channel_id, user_id):
        channel = self.bot.get_channel(channel_id)
        if isinstance(channel, discord.abc.GuildChannel):
            author = channel.guild.get_member(user_id)
        else:
            author = self.bot.get_user(user_id)
        await self.update_last_update(author)

    # Name related commands

    @group(invoke_without_command=True)
    async def names(self, ctx, *, user: discord.Member=None):
        """Shows a user's previous names within the last 30 days."""
        if user is None:
            user = ctx.message.author
        names = await self.names_for(user, since=timedelta(days=30))
        names = utils.clean_formatting(", ".join(names))
        names = utils.clean_mentions(names)
        await ctx.send("Names for {} in the last 30 days\n{}".format(
            user, names))

    @names.command(name="all")
    async def allnames(self, ctx, *, user: discord.Member=None):
        """Shows a all of a user's previous names."""
        if user is None:
            user = ctx.message.author
        names = await self.names_for(user)
        names = utils.clean_formatting(", ".join(names))
        names = utils.clean_mentions(names)
        await ctx.send("Names for {}\n{}".format(user, names))

    @group(invoke_without_command=True)
    @commands.guild_only()
    async def nicks(self, ctx, *, user: discord.Member=None):
        """Shows a members's previous nicks within the last 30 days."""
        if user is None:
            user = ctx.message.author
        names = await self.nicks_for(user, since=timedelta(days=30))
        names = utils.clean_formatting(", ".join(names))
        names = utils.clean_mentions(names)
        await ctx.send("Nicks for {} in the last 30 days\n{}".format(
            user, names))

    @nicks.command(name="all")
    @commands.guild_only()
    async def allnicks(self, ctx, *, user: discord.Member=None):
        """Shows a all of a member's previous nicks."""
        if user is None:
            user = ctx.message.author
        names = await self.nicks_for(user)
        names = utils.clean_formatting(", ".join(names))
        names = utils.clean_mentions(names)
        await ctx.send("Nicks for {}\n{}".format(
            user, names))

    @command()
    @checks.is_owner()
    async def updateall(self, ctx):
        for g in ctx.bot.guilds:
            await self.on_guild_join(g)

    @command()
    @checks.is_owner()
    async def updatestatus(self, ctx):
        await ctx.send("name updates: %s %s\n presence updates: %s %s" % (
            len(self.batch_name_updates), self.batch_name_task,
            len(self.batch_presence_updates), self.batch_presence_task))
