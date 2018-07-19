import sys

import aiohttp

API_BASE = "https://api.waa.ai"
SHORTEN = API_BASE + "/shorten"

class AkariError(Exception): pass

async def shorten(url, api_key):
    parts = url.split('#', 2)
    if len(parts) == 2:
        server_part, client_part = parts
    else:
        server_part = parts[0]
        client_part = None

    python_version = '.'.join(map(str, sys.version_info[:3]))
    async with aiohttp.ClientSession(headers={
        'User-Agent': 'waaai.py/0.0.2 aiohttp/%s python/%s' % (aiohttp.__version__, python_version),
    }) as session:
        async with session.post(SHORTEN, data=dict(
            url=server_part,
            key=api_key
        )) as resp:
            resp_json = await resp.json()
            if not resp_json['success']:
                raise AkariError
            assert resp_json['success']

            return resp_json['data']['url'] + ("#" + client_part) if client_part else ""
