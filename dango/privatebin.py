#!/usr/bin/env python3
# encoding: utf-8

"""
privatebin.py: uploads text to privatebin
© 2017 khazhyk
© 2019 Io Mintz https://github.com/iomintz
"""

import asyncio
import os
import sys

import aiohttp
from pbincli.format import Paste


def make_payload(text):
    paste = Paste()
    paste.setVersion(2)
    paste.setText(text)
    paste.encrypt(formatter='plaintext', burnafterreading=0, discussion=0, expiration='never')
    return paste.getJSON(), paste.getHash()

UPLOAD_LOCK = asyncio.Lock()

class PrivateBinException(Exception):
    """Ran out of tries uploading to privatebin, or got unrecoverable error."""

async def upload(text, loop=None):
    loop = loop or asyncio.get_event_loop()

    async with UPLOAD_LOCK:
        result = None
        payload, key = await loop.run_in_executor(None, make_payload, text)
        python_version = '.'.join(map(str, sys.version_info[:3]))
        async with aiohttp.ClientSession(headers={
                'User-Agent': 'privatebin.py/0.0.2 aiohttp/%s python/%s' %
                              (aiohttp.__version__, python_version),
                'X-Requested-With': 'JSONHttpRequest'
        }) as session:
            for tries in range(2):
                async with session.post('https://privatebin.net/', data=payload) as resp:
                    if resp.status >= 400:
                        raise PrivateBinException(resp, await resp.text())
                    resp_json = await resp.json()
                    if resp_json['status'] == 0:
                        result = url(resp_json['id'], key)
                        break
                    if resp_json['status'] == 1:  # rate limited
                        await asyncio.sleep(10)

    if result is None:
        raise PrivateBinException('Failed to upload to privatebin')
    return result

def url(paste_id, key):
    return 'https://privatebin.net/?{}#{}'.format(paste_id, key)


async def main():
	print(await upload(sys.stdin.read()))

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())
