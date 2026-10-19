"""The host's files: the request and status files the gateway shares with
the root-path units (cloudphone-display, cloudphone-settings) and the times
they keep, and read_file for the host's own (/proc, the emulator's cgroup).

The core never opens a file: it gets what these functions return. The fake
emulator's shim (tests/fake-emulator/gateway_shim.py) redirects host paths
by replacing this module's open.
"""

import os


def read_file(path, size=-1):
    """The file's text (at most size characters), or None."""
    try:
        with open(path, "r") as f:
            return f.read(size)
    except OSError:
        return None


def exists(path):
    """True when path is set and the file is there (a request not yet taken)."""
    return bool(path) and os.path.exists(path)


def mtime(path):
    """When the file was last written (Unix time), 0.0 when it is not there."""
    try:
        return os.stat(path).st_mtime
    except (OSError, TypeError):
        return 0.0


def write_request(path, line):
    """Writes a request whole, so that its unit never reads half a line."""
    temporary = f"{path}.tmp"
    with open(temporary, "w") as f:
        f.write(line)
    os.replace(temporary, path)
