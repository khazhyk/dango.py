import logging
import sys

def setup_logging():
    if hasattr(setup_logging, 'once'):
        return
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "[%(asctime)s][%(name)s][%(levelname)s] %(message)s")

    stdouthandler = logging.StreamHandler(sys.stdout)
    stdouthandler.setFormatter(formatter)
    root.addHandler(stdouthandler)
    setattr(setup_logging, 'once', None)