"""The host's files: the request and status files the gateway shares with
the root-path units (cloudphone-display, cloudphone-settings) and the times
they keep, and the host's own (/proc, /sys, the emulator's cgroup and its
command line).

The core never opens a file: it gets what these functions return. Every
host file the gateway reads goes through here, so the fake emulator's shim
(tests/fake-emulator/gateway_shim.py) redirects host paths by replacing
this module's open alone.
"""

import os


def read_file(path, size=-1):
    """The file's text (at most size characters), or None."""
    try:
        with open(path, "r") as f:
            return f.read(size)
    except OSError:
        return None


def first_line(path):
    """The file's first line; raises OSError when it cannot be read."""
    with open(path, "r") as f:
        return f.readline()


def command_line(pid):
    """A process's arguments (/proc/PID/cmdline), or None."""
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            return f.read().decode(errors="replace").split("\0")
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
