import json

from dango import dcog, Cog
import discord
from discord.ext.commands import command
from lru import LRU

from .common import checks
from .common import converters
from .common import utils


def _redis_key(item_type, item_id):
    return "spoo:attribute:%s:%s" % (item_type, item_id)


@dcog(depends=['Database', 'Redis'])
class AttributeStore(Cog):
    """Basically a persistent json mapping.

    3 levels of storage:
        - in memory LRU
        - redis
        - psql
    """

    def __init__(self, config, database, redis):
        self.database = database
        self.redis = redis

        self._mapping = utils.TypeMap()

        self._lru = LRU(2048)
        self._lru_types = set()

        # Member can't be LRU mapped if we have multi-process bot.
        self.register_mapping(discord.abc.User, 'member')
        self.register_mapping(discord.Guild, 'server')
        self.register_mapping(discord.TextChannel, 'channel')

    def register_mapping(self, item_type, name, lru=True):
        self._mapping.put(item_type, name)
        if lru:
            self._lru_types.add(name)

    async def _get_lru(self, item_type, item_id):
        if item_type not in self._lru_types:
            return
        return self._lru.get((item_type, item_id))

    async def _put_lru(self, item_type, item_id, value):
        if item_type in self._lru_types:
            self._lru[(item_type, item_id)] = value

    async def _get_redis(self, item_type, item_id):
        async with self.redis.acquire() as conn:
            res = await conn.get(_redis_key(item_type, item_id), encoding='utf8')
            if res:
                return json.loads(res)

    async def _put_redis(self, item_type, item_id, value):
        async with self.redis.acquire() as conn:
            await conn.set(_redis_key(item_type, item_id), json.dumps(value))

    async def _get_db(self, item_type, item_id):
        async with self.database.acquire() as conn:
            res = await conn.fetchrow(
                "SELECT * FROM attributes "
                "WHERE id = $1 AND type = $2", str(item_id), item_type)
            if res:
                return json.loads(res['data'])

    async def _put_db(self, item_type, item_id, value):
        async with self.database.acquire() as conn:
            await conn.execute(
                "INSERT INTO attributes (id, type, data)"
                "VALUES ($1, $2, $3)"
                "ON CONFLICT (id, type) DO UPDATE SET data = $3",
                str(item_id), item_type, json.dumps(value))

    async def _get(self, item_type, item_id):
        res = await self._get_lru(item_type, item_id)
        if res:
            return res

        res = await self._get_redis(item_type, item_id)
        if res:
            await self._put_lru(item_type, item_id, res)
            return res

        res = await self._get_db(item_type, item_id)
        if res:
            await self._put_redis(item_type, item_id, res)
            await self._put_lru(item_type, item_id, res)
            return res
        return {}

    async def _put(self, item_type, item_id, value):
        await self._put_db(item_type, item_id, value)
        await self._put_redis(item_type, item_id, value)
        await self._put_lru(item_type, item_id, value)

    async def _update(self, item_type, item_id, **vals):
        cur = await self._get(item_type, item_id)
        cur.update(vals)
        await self._put(item_type, item_id, cur)

    def get(self, item):
        return self._get(self._mapping.lookup(type(item)), item.id)

    def update(self, item, **vals):
        return self._update(self._mapping.lookup(type(item)), item.id, **vals)

    async def get_attribute(self, scope, name, default=None):
        return (await self.get(scope)).get(name, default)

    async def set_attributes(self, scope, **attributes):
        await self.update(scope, **attributes)

    @command()
    @checks.is_owner()
    async def attributes(self, ctx, user: converters.UserMemberConverter):
        attr = await self.get(user)
        if not attr:
            await ctx.send("No attributes")
            return

        embed = discord.Embed()
        for key, value in attr.items():
            embed.add_field(name=key, value=value)
        await ctx.send(embed=embed)
