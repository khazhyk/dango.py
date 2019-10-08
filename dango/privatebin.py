#!/usr/bin/env python3
# encoding: utf-8

"""
privatebin.py: uploads text to privatebin
using code from <https://github.com/r4sas/PBinCLI/blob/master/pbincli/actions.py>,
© 2017–2018 R4SAS <r4sas@i2pmail.org>
using code from <https://github.com/khazhyk/dango.py/blob/master/dango/zerobin.py>,
© 2017 khazhyk
modified by https://github.com/bmintz
© 2018 bmintz
"""

import asyncio
import base64
import json
import os
import sys
import zlib

import aiohttp
from sjcl import SJCL


def encrypt(text):
    key = base64.urlsafe_b64encode(os.urandom(32))
    # Encrypting text
    encrypted_data = SJCL().encrypt(compress(text.encode('utf-8')), key, mode='gcm', count=100000, dkLen=32)
    return encrypted_data, key

def compress(src: bytes):
    co = zlib.compressobj(wbits=-zlib.MAX_WBITS)
    buf = co.compress(src) + co.flush()

    return base64.b64encode(''.join(map(chr, buf)).encode('utf-8'))

"""
{"adata":[["7bgUbn07YgdqgBGwZ4yNBA==","v3ZCVYrvK6Q=",100000,256,128,"aes","gcm","rawdeflate"],"plaintext",0,0],
"meta":{"expire":"1week"},"v":2,"ct":"yJWr3EveuZZywMGgHVxI+NoXjhOjykblWK1AObCdiA4AEA=="}
"""
def make_payload(text):
    # Formatting request
    request = {
        "adata": [None, "plaintext", 0, 0],
        "meta": {"expire": "never"},
    }

    cipher, key = encrypt(text)
    # SJCL uses bytes, we want a string
    for k in ["salt", "iv", "ct"]:
        cipher[k] = cipher[k].decode()

    request["adata"] = [
        [
            cipher["iv"], cipher["salt"], cipher["iter"], cipher["ks"],
            cipher["ts"], cipher["cipher"], cipher["mode"], "zlib"],
        "plaintext", 0, 0
    ]
    request["v"] = "2"
    request["ct"] = cipher["ct"]

    return request, key

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
    return 'https://privatebin.net/?%s#%s' % (paste_id, key.decode('utf-8'))
