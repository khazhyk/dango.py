import asyncio
import os
import re
import subprocess
import sys


def snakify(name):
    """Turn CamelCase into snake_case."""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def fix_unicode():
    """Make python not crash when logging trivial statements."""
    if os.name == "nt":
        sys.stdout = sys.__stdout__ = open(
            sys.stdout.detach().fileno(), 'w', encoding=sys.stdout.encoding,
            errors="backslashreplace")
        sys.stderr = sys.__stderr__ = open(
            sys.stderr.detach().fileno(), 'w', encoding=sys.stderr.encoding,
            errors="backslashreplace")
