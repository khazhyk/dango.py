import json

from dango import checks
from dango import dcog
import discord
from discord.ext.commands import command
from lru import LRU


def _redis_key(type, id):
    return "spoo:attribute:%s:%s" % (type, id)


@dcog(depends=['Database', 'Redis'])
class AttributeStore:
    """Basically a persistent json mapping.

    3 levels of storage:
        - in memory LRU
        - redis
        - psql
    """

    def __init__(self, database, redis):
        self.database = database
        self.redis = redis

        self._mapping = {}

        self._lru = LRU(2048)
        self._lru_types = set()

        self.register_mapping(discord.Member, 'member')
        self.register_mapping(discord.User, 'member')
        self.register_mapping(discord.ClientUser, 'member')
        self.register_mapping(discord.Guild, 'server')
        self.register_mapping(discord.TextChannel, 'channel')

    def register_mapping(self, type, name, lru=True):
        self._mapping[type] = name
        if lru:
            self._lru_types.add(name)

    async def _get_lru(self, type, id):
        if type not in self._lru_types:
            return
        return self._lru.get((type, id))

    async def _put_lru(self, type, id, value):
        if type in self._lru_types:
            self._lru[(type, id)] = value

    async def _get_redis(self, type, id):
        async with self.redis.acquire() as conn:
            res = await conn.get(_redis_key(type, id), encoding='utf8')
            if res:
                return json.loads(res)

    async def _put_redis(self, type, id, value):
        async with self.redis.acquire() as conn:
            await conn.set(_redis_key(type, id), json.dumps(value))

    async def _get_db(self, type, id):
        async with self.database.acquire() as conn:
            res = await conn.fetchrow(
                "SELECT * FROM attributes "
                "WHERE id = $1 AND type = $2", str(id), type)
            if res:
                return json.loads(res['data'])

    async def _put_db(self, type, id, value):
        async with self.database.acquire() as conn:
            await conn.execute(
                "INSERT INTO attributes (id, type, data)"
                "VALUES ($1, $2, $3)"
                "ON CONFLICT (id, type) DO UPDATE SET data = $3",
                str(id), type, json.dumps(value))

    async def _get(self, type, id):
        res = await self._get_lru(type, id)
        if res:
            return res

        res = await self._get_redis(type, id)
        if res:
            await self._put_lru(type, id, res)
            return res

        res = await self._get_db(type, id)
        if res:
            await self._put_redis(type, id, res)
            await self._put_lru(type, id, res)
            return res
        return {}

    async def _put(self, type, id, value):
        await self._put_db(type, id, value)
        await self._put_redis(type, id, value)
        await self._put_lru(type, id, value)

    async def _update(self, type, id, **vals):
        cur = await self._get(type, id)
        cur.update(vals)
        await self._put(type, id, cur)

    def get(self, item):
        return self._get(self._mapping[type(item)], item.id)

    def update(self, item, **vals):
        return self._update(self._mapping[type(item)], item.id, **vals)

    async def get_attribute(self, scope, name, default=None):
        return (await self.get(scope)).get(name, default)

    async def set_attributes(self, scope, **attributes):
        await self.update(scope, **attributes)

    @command()
    @checks.is_owner()
    async def attributes(self, ctx, user: discord.User):
        attr = await self.get(user)
        if not attr:
            await ctx.send("No attributes")
            return

        embed = discord.Embed()
        for k, v in attr.items():
            embed.add_field(name=k, value=v)
        await ctx.send(embed=embed)
