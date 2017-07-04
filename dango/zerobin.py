import asyncio
import base64
import json
import logging
import os
import zlib

import aiohttp
import sjcl

log = logging.getLogger(__name__)


def get_surrogate(cpt):
    num = cpt - 0x010000
    return ((num & (0x03ff << 10)) >> 10) + 0xd800, (num & 0x03ff) + 0xdc00


def get_surrogates(cpts):
    for cpt in cpts:
        if cpt < 0x10000:
            yield cpt
        else:
            yield from get_surrogate(cpt)


def mangle_string(thing):
    """Mimics base64.js "convertUTF16ArrayToUTF8Array" """
    wew = get_surrogates(map(ord, thing))
    result = []
    for n in wew:
        if n < 0x80:
            result.append(n)
        elif n < 0x800:
            result.append(0xc0 | (n >> 6))
            result.append(0x80 | (n & 0x3f))
        else:
            result.append(0xe0 | ((n >> 12) & 0x0f))
            result.append(0x80 | ((n >> 6) & 0x3f))
            result.append(0x80 | (n & 0x3f))
    return result


global_zerobin_lock = asyncio.Lock()

async def upload_zerobin(string_content, loop=None):
    async with global_zerobin_lock:
        if not loop:
            loop = asyncio.get_event_loop()
        encrypted_data, encoded_key = await loop.run_in_executor(
            None, make_zerobin_payload, string_content)
        payload = json.dumps(
            encrypted_data, default=lambda x: x.decode('utf8'))

        if len(payload) > 512000:
            raise ValueError("Content too big")

        tries = 0
        with aiohttp.ClientSession() as c:
            while tries < 2:
                async with c.post("https://zerobin.net/", data=dict(
                        data=payload,
                        expire="never",
                        burnafterreading="0",
                        opendiscussion="0",
                        syntaxcoloring="0")) as resp:
                    resp_content = await resp.text()
                    try:
                        resp_json = json.loads(resp_content)
                    except json.JSONDecodeError:
                        log.error(resp_content)
                    else:
                        if resp_json['status'] == 0:
                            log.info("To delete: %s" %
                                     make_zerobin_delete_url(resp_json))
                            return make_zerobin_url(resp_json, encoded_key)
                        elif resp_json['status'] == 1:  # Rate limited
                            await asyncio.sleep(10)


def make_zerobin_payload(string_content):
    compress = zlib.compressobj(
        0, zlib.DEFLATED, -zlib.MAX_WBITS, zlib.DEF_MEM_LEVEL, 4)
    compressed_data = compress.compress(bytes(mangle_string(string_content)))
    compressed_data += compress.flush()
    encoded_data = base64.b64encode(compressed_data)
    key = os.urandom(32)
    encoded_key = base64.urlsafe_b64encode(key)
    encrypted_data = sjcl.SJCL().encrypt(encoded_data, encoded_key)
    return encrypted_data, encoded_key


def decrypt_zerobin_payload(encrypted_data, encoded_key):
    b64_deflated = sjcl.SJCL().decrypt(encrypted_data, encoded_key)
    deflated = base64.urlsafe_b64decode(b64_deflated)
    inflater = zlib.decompressobj(-zlib.MAX_WBITS)
    data = inflater.decompress(deflated)
    return data


def make_zerobin_url(response_json, encoded_key):
    return "https://zerobin.net?%s#%s" % (
        response_json['id'], encoded_key.decode('utf8'))


def make_zerobin_delete_url(response_json):
    return "https://zerobin.net?pasteid=%s&deletetoken=%s" % (
        response_json['id'], response_json['deletetoken'])


if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    print(loop.run_until_complete(upload_zerobin('hello \N{DANGO}')))
