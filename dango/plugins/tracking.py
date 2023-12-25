import asyncio
import collections
import copy
import itertools
import logging
import struct
import re
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from dango import dcog, Cog
import discord
from discord.ext import commands
from discord.ext.commands import command
from discord.ext.commands import group
import lru
import tabulate

from dango.plugins.database import multi_insert_str

from typing import List, NamedTuple, Union, Iterable

from .common import checks
from .common import converters
from .common import utils

log = logging.getLogger(__name__)

REDIS_NICK_NONE = (b'NoneNoneNoneNoneNoneNoneNoneNoneNoneNoneNoneNoneNoneNoneNone'
                   b'NoneNoneNoneNoneNoneNoneNoneNoneNoneNoneNoneNone')
PG_ARG_MAX = 32767


def grouper(it, n):
    return zip(*([iter(it)]*n))


class LastSeenTuple(NamedTuple):
    last_seen: datetime = datetime.fromtimestamp(0, timezone.utc)
    last_spoke: datetime = datetime.fromtimestamp(0, timezone.utc)
    server_last_spoke: datetime = datetime.fromtimestamp(0, timezone.utc)


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

# Entries with expiries
class SeenUpdate(NamedTuple):
    member_id: int
    date: datetime

MAX_SEEN_INSERTS = (PG_ARG_MAX // 2) - 1

class SpokeUpdate(NamedTuple):
    member_id: int
    server_id: int
    date: datetime

MAX_SPOKE_INSERTS = (PG_ARG_MAX // 3) - 1


def datetime_from_redis(bytes_obj):
    """Pass in timestamp in UTC, gives datetime in UTC"""
    if bytes_obj is None:
        return datetime.fromtimestamp(0, timezone.utc)
    return datetime.fromtimestamp(struct.unpack('q', bytes_obj)[0] / 1000, timezone.utc)


@dcog(depends=['Database', 'Redis'], pass_bot=True)
class Tracking(Cog):

    def __init__(self, bot, config, database, redis):
        self.bot = bot
        self.database = database
        self.database.hold()
        self.redis = redis
        self.redis.hold()

        self._recent_pins = lru.LRU(128)

        self.batch_last_spoke_updates = []
        self._batch_last_spoke_curr_updates = []
        self.batch_last_seen_updates = []
        self._batch_last_seen_curr_updates = []

        self.batch_name_updates = []
        self._batch_name_curr_updates = []
        self.batch_presence_task = utils.create_task(self.batch_presence())
        self.batch_name_task = utils.create_task(self.batch_name())

    def cog_unload(self):
        self.batch_presence_task.cancel()
        self.batch_name_task.cancel()
        self.database.unhold()
        self.redis.unhold()

    async def batch_presence(self):
        try:    
            while True:
                try:
                    await self.do_batch_presence_update()
                except Exception:
                    log.exception("Exception during presence update task!")
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            log.info("batch_presence task canceled...")
            await self.do_batch_presence_update()
            if self.batch_last_spoke_updates:
                log.error("Dropping %d presences!", len(self.batch_last_spoke_updates) / 2)
            if self.batch_last_seen_updates:
                log.error("Dropping %d presences!", len(self.batch_last_seen_updates) / 2)
    
    async def batch_name(self):
        try:
            while True:
                try:
                    await self.do_batch_names_update()
                except Exception:
                    log.exception("Exception during name update task!")
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            log.info("batch_name task canceled...")
            await self.do_batch_names_update()
            if self.batch_name_updates:
                log.error("Dropping %d name updates!", len(self.batch_name_updates))

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
                "SELECT name, idx FROM namechanges "
                "WHERE id = $1 "
            )
            params.append(str(member.id))  # TODO - convert schema to BigInt
            if since:
                query += "AND date >= $2 "
                params.append((datetime.utcnow().replace(tzinfo=timezone.utc) - since))
            query += "ORDER BY idx DESC "
            if since:
                query = (
                    "(SELECT name, idx from namechanges "
                    "WHERE id = $1 AND date < $2 "
                    "ORDER BY idx DESC limit 1) UNION (%s) "
                    "ORDER BY idx DESC" % query
                )

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
                "SELECT name, idx FROM nickchanges "
                "WHERE id = $1 AND server_id = $2 "
            )
            # TODO - convert schema to BigInt
            params.extend((str(member.id), str(member.guild.id)))
            if since:
                query += "AND date >= $3 "
                params.append((datetime.utcnow().replace(tzinfo=timezone.utc) - since))
            query += "ORDER BY idx DESC "
            if since:
                query = (
                    "(SELECT name, idx from nickchanges "
                    "WHERE id = $1 and server_id = $2 AND date < $3 "
                    "ORDER BY idx DESC limit 1) UNION (%s) "
                    "ORDER BY idx DESC" % query
                )

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
            member, datetime.utcnow().replace(tzinfo=timezone.utc)))

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
            self._batch_name_curr_updates = all_updates
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
            user_keys = [
                ("spoo:last_username:%d" % m_id, name_to_redis(m_name))
                for m_id, (m_name, _) in current_names.items()]
            name_keys = [
                ("spoo:last_nickname:%d:%d" % (m_id, m_server), name_to_redis(m_name))
                for (m_id, m_server), (m_name, _) in current_nicks.items()]
            
            all_keys = dict(user_keys + name_keys)
            await conn.mset(all_keys)

    # Presence tracking
    async def last_seen(self, member: Union[discord.User, discord.Member]) -> LastSeenTuple:
        """Lookup last_seen data."""
        async with self.database.acquire() as conn:
            last_seen = await conn.fetchval(
                "SELECT date from last_seen WHERE id = $1 LIMIT 1", member.id)
            last_spoke  = await conn.fetchval(
                "SELECT date from last_spoke WHERE id = $1 and server_id = 0 LIMIT 1", member.id)
            if hasattr(member, 'guild'):
                server_last_spoke  = await conn.fetchval(
                "SELECT date from last_spoke WHERE id = $1 and server_id = $2 LIMIT 1",
                member.id, member.guild.id)
            else:
                server_last_spoke = datetime.fromtimestamp(0, timezone.utc)

        return LastSeenTuple(
            last_seen or datetime.fromtimestamp(0, timezone.utc),
            last_spoke or datetime.fromtimestamp(0, timezone.utc),
            server_last_spoke or datetime.fromtimestamp(0, timezone.utc))

    async def bulk_last_seen(self, members: List[discord.Member]) -> List[LastSeenTuple]:
        """All members must be in the same guild.

        Returns in same order as `members`
        """
        ids = [m.id for m in members]
        guild_id = members[0].guild.id

        async with self.database.acquire() as conn:
            last_seens = {
                member_id: date for member_id, date in await conn.fetch(
                "SELECT id, date from last_seen WHERE id = ANY($1)",
                ids)
            }
            last_spokes = {
                member_id: date for member_id, date in await conn.fetch(
                "SELECT id, date from last_spoke WHERE id = ANY($1) AND server_id = 0",
                ids)
            }
            server_last_spokes = {
                member_id: date for member_id, date in await conn.fetch(
                "SELECT id, date from last_spoke WHERE id = ANY($1) AND server_id = $2",
                ids, guild_id)
            }

        return [
            LastSeenTuple(
                last_seens.get(m.id, datetime.fromtimestamp(0, timezone.utc)),
                last_spokes.get(m.id, datetime.fromtimestamp(0, timezone.utc)),
                server_last_spokes.get(m.id, datetime.fromtimestamp(0, timezone.utc)))
            for m in members
        ]

    async def update_last_update(self, member):
        self.queue_batch_last_update(member)

    async def update_last_message(self, member):
        self.queue_batch_last_spoke_update(member)
        self.queue_batch_last_update(member)

    def queue_batch_last_spoke_update(self, member, at_time:datetime = None):
        """Someone spoke!"""
        at_time = at_time or datetime.now(timezone.utc)
        self.batch_last_spoke_updates.append(
            SpokeUpdate(member.id, 0, at_time))
        if hasattr(member, "guild"):
            self.batch_last_spoke_updates.append(
              SpokeUpdate(member.id, member.guild.id, at_time))

    def queue_batch_last_update(self, member, at_time: datetime = None):
        """Someone had an event while online!"""
        at_time = at_time or datetime.now(timezone.utc)
        self.batch_last_seen_updates.append(
            SeenUpdate(member.id, at_time))

    async def do_batch_presence_update(self):
        self._batch_last_seen_curr_updates = self.batch_last_seen_updates
        self._batch_last_spoke_curr_updates = self.batch_last_spoke_updates
        self.batch_last_seen_updates = []
        self.batch_last_spoke_updates = []

        # Split due to arg limit
        while self._batch_last_seen_curr_updates or self._batch_last_spoke_curr_updates:
            curr_last_seen = self._batch_last_seen_curr_updates[:MAX_SEEN_INSERTS]
            self._batch_last_seen_curr_updates = self._batch_last_seen_curr_updates[MAX_SEEN_INSERTS:]

            curr_spoke_updates = self._batch_last_spoke_curr_updates[:MAX_SPOKE_INSERTS]
            self._batch_last_spoke_curr_updates = self._batch_last_spoke_curr_updates[MAX_SPOKE_INSERTS:]

            def dedupe_seen(last_seens):
                seen = {}
                for ls in last_seens:
                    try:
                        seen[ls.member_id] = max(seen[ls.member_id], ls, key=lambda x:x.date)
                    except KeyError:
                        seen[ls.member_id] = ls
                return list(seen.values())

            def dedupe_spoke(last_spokes):
                seen = {}
                for ls in last_spokes:
                    try:
                        seen[ls.member_id, ls.server_id] = max(seen[ls.member_id, ls.server_id], ls, key=lambda x:x.date)
                    except KeyError:
                        seen[ls.member_id, ls.server_id] = ls
                return list(seen.values())

            await self.batch_insert_presence_updates(
                dedupe_seen(curr_last_seen), dedupe_spoke(curr_spoke_updates))


    async def batch_insert_presence_updates(self, seen_updates: List[SeenUpdate], spoke_updates: List[SpokeUpdate]):
        """Push presence updates to postgres."""
        assert len(seen_updates) < (PG_ARG_MAX // 2)
        assert len(spoke_updates) < (PG_ARG_MAX // 3)
        # do multi_insert_str since it's 2x faster than executemany
        async with self.database.acquire() as conn:
            async with conn.transaction():
                # avoid deadlocks
                await conn.execute("LOCK TABLE last_seen IN EXCLUSIVE MODE")
                await conn.execute("LOCK TABLE last_spoke IN EXCLUSIVE MODE")
                if seen_updates:
                    await conn.execute(
                        "INSERT INTO last_seen (id, date) "
                        "VALUES %s ON CONFLICT (id) DO UPDATE SET date = EXCLUDED.date WHERE EXCLUDED.date > last_seen.date" % (
                            multi_insert_str(seen_updates)
                        ),
                        *itertools.chain(*seen_updates)
                    )
                if spoke_updates:
                    await conn.execute(
                        "INSERT INTO last_spoke (id, server_id, date) "
                        "VALUES %s ON CONFLICT (id, server_id) DO UPDATE SET date = EXCLUDED.date WHERE EXCLUDED.date > last_spoke.date" % (
                            multi_insert_str(spoke_updates)
                        ),
                        *itertools.chain(*spoke_updates)
                    )

    async def queue_migrate_redis(self):
        async with self.redis.acquire() as conn:
            cur = b'0'
            while cur:
                cur, keys = await conn.scan(cur, match=b"spoo:last_seen:*", count=5000)
                values = await conn.mget(*keys)

                for key, value in zip(keys, values):
                    user_id = re.match(rb"spoo:last_seen:(\d+)", key).group(1)

                    self.queue_batch_last_update(
                        discord.Object(id=int(user_id)),
                        at_time=datetime_from_redis(value))

            cur = b'0'
            while cur:
                cur, keys = await conn.scan(cur, match=b"spoo:last_spoke:*", count=5000)
                values = await conn.mget(*keys)

                for key, value in zip(keys, values):
                    user_id, guild_id = re.match(rb"spoo:last_spoke:(\d+)(?::(\d+))?", key).groups()

                    if guild_id:
                        fake_user = discord.Object(id=int(user_id))
                        fake_user.guild = discord.Object(id=int(guild_id))
                        self.queue_batch_last_spoke_update(
                            fake_user, at_time=datetime_from_redis(value))
                    else:
                        self.queue_batch_last_spoke_update(
                            discord.Object(id=int(user_id)),
                            at_time=datetime_from_redis(value))


    # Event registration

    @Cog.listener()
    async def on_ready(self):
        for g in self.bot.guilds:
            await self.on_guild_join(g)

    @Cog.listener()
    async def on_guild_join(self, guild):
        for member in copy.copy(list(guild.members)):
            self.queue_batch_names_update(member)
            if member.status is not discord.Status.offline:
                self.queue_batch_last_update(member)

    @Cog.listener()
    async def on_member_update(self, before, member):
        # only update when we change online status.
        if before.status != member.status:
            self.queue_batch_last_update(member)
        self.queue_batch_names_update(member)

    @Cog.listener()
    async def on_member_join(self, member):
        await asyncio.gather(
            self.update_last_update(member),
            self.update_name_change(member),
            self.update_nick_change(member)
        )

    @Cog.listener()
    async def on_message(self, message):
        await self.update_last_message(message.author)

    @Cog.listener()
    async def on_typing(self, channel, user, when):
        await self.update_last_update(user)

    @Cog.listener()
    async def on_raw_message_edit(self, raw_event):
        message_id, data = raw_event.message_id, raw_event.data
        if 'author' not in data:
            return  # This is a automatic discord embed edit, ignore.

        if data['author']['discriminator'] == '0000':
            return  # Ignore webhooks.

        if data.get('edited_timestamp') is None:
            return  # Ignore pins/etc. that aren't actually edits.

        # If we had a recent pin in this channel, and the edited_timestamp is
        # not within 5 seconds of the pin, or newer than the pin, ignore as this
        # is a pin.

        edit_time = discord.utils.parse_time(data['edited_timestamp'])
        last_pin_time = self._recent_pins.get(data['channel_id'])

        # If a message is edited, then pinned within 5 seconds, we will end up
        # updating incorrectly, but oh well.
        if (last_pin_time and edit_time < last_pin_time - timedelta(seconds=5)):
            return  # If we get an edit in the past, ignore it, it's a pin.
        elif(edit_time < datetime.utcnow().replace(tzinfo=timezone.utc) - timedelta(minutes=2)):
            log.info("Got edit with old timestamp, missed pin? %s", data)
            return  # This *may* be a pin, since it's old, but we didn't get a pin event.

        if data.get('guild_id'):
            guild = self.bot.get_guild(int(data['guild_id']))
            author = guild.get_member(int(data['author']['id']))
        else:
            author = self.bot.get_user(int(data['author']['id']))

        if not author:
            log.warning("Got raw_message_edit for non-existant author %s", data)
            return
        await self.update_last_message(author)

    @Cog.listener()
    async def on_guild_channel_pins_update(self, channel, last_pin):
        self._recent_pins[str(channel.id)] = datetime.utcnow().replace(tzinfo=timezone.utc)

    @Cog.listener()
    async def on_private_channel_pins_update(self, channel, last_pin):
        self._recent_pins[str(channel.id)] = datetime.utcnow().replace(tzinfo=timezone.utc)

    @Cog.listener()
    async def on_raw_reaction_add(self, raw_event):
        if raw_event.guild_id:
            guild = self.bot.get_guild(raw_event.guild_id)
            author = guild.get_member(raw_event.user_id)
        else:
            author = self.bot.get_user(raw_event.user_id)
        if not author:
            log.warning("Got raw_reaction_add for non-existant author %s, %s, %s, %s",
                        raw_event.emoji, raw_event.message_id, raw_event.channel_id, raw_event.user_id)
            return
        await self.update_last_update(author)

    # Name related commands

    @group(invoke_without_command=True)
    async def names(self, ctx, *, user: converters.UserMemberConverter=None):
        """Shows a user's previous names within the last 90 days."""
        if user is None:
            user = ctx.message.author
        names = await self.names_for(user, since=timedelta(days=90))
        names = utils.clean_formatting(", ".join(names))
        names = utils.clean_mentions(names)
        await ctx.send("Names for {} in the last 90 days\n{}".format(
            user, names))

    @names.command(name="all")
    async def allnames(self, ctx, *, user: converters.UserMemberConverter=None):
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
        """Shows a members's previous nicks within the last 90 days."""
        if user is None:
            user = ctx.message.author
        names = await self.nicks_for(user, since=timedelta(days=90))
        names = utils.clean_formatting(", ".join(names))
        names = utils.clean_mentions(names)
        await ctx.send("Nicks for {} in the last 90 days\n{}".format(
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
        await self.updatestatus.invoke(ctx)

    @command()
    @checks.is_owner()
    async def updatestatus(self, ctx):
        rows = (
            (
                len(self.batch_name_updates),
                len(self._batch_name_curr_updates),
                str(self.batch_name_task._state),
                len(self.batch_last_spoke_updates),
                len(self._batch_last_spoke_curr_updates),
                len(self.batch_last_seen_updates),
                len(self._batch_last_seen_curr_updates),
                str(self.batch_presence_task._state),
            ),
        )
        lines = tabulate.tabulate(
            rows, headers=[
                "PNU", "CNU", "NTS",
                "PSpU", "CSpU", "PSeU", "CSeU", "PTS",
            ], tablefmt="simple")
        await ctx.send("```prolog\n{}```".format(lines))

    @command()
    @checks.is_owner()
    async def migrate_presence_db(self, ctx):
        async with ctx.typing():
            await self.queue_migrate_redis()
            await self.updatestatus.invoke(ctx)

