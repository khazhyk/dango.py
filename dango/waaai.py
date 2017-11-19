import aiohttp

API_BASE = "https://api.waa.ai"
SHORTEN = API_BASE + "/shorten"


async def send_to_waaai(url, api_key):
    parts = url.split('#', 2)
    if len(parts) == 2:
        server_part, client_part = parts
    else:
        server_part = parts[0]
        client_part = None
    with aiohttp.ClientSession() as session:
        async with session.post(SHORTEN, data=dict(
            url=server_part,
            key=api_key
        )) as resp:
            resp_json = await resp.json()
            assert resp_json['success']

            return resp_json['data']['url'] + ("#" + client_part) if client_part else ""
