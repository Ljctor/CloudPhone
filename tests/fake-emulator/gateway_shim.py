"""Runs the repository's gateway, unchanged, on the fake emulator's host.

The gateway reads a few host files with no option to point it elsewhere:
the load (/proc/loadavg), the host's memory (/proc/meminfo) and the
emulator unit's cgroup (/sys/fs/cgroup/system.slice/UNIT/: its processes,
CPU and memory, and the command line of its qemu process). All of them
go through adapters/host_files.py; this shim redirects exactly those paths
in that module to the fake's files under $FAKE_ROOT/host, then runs the
gateway's own main with the command line it was given. Everything else
(systemctl and adb through PATH and --adb, the discovery file, config.ini,
the request and status files) goes through the gateway's normal options.

The gateway's web site also binds with SO_REUSEPORT: the fake holds its
port (bound, not listening) for its whole life, so that no other process
takes it between two gateways (reserve_port in fake_emulator.py).
"""
import builtins
import os
import sys

from aiohttp import web

root = os.path.join(os.environ["FAKE_ROOT"], "host")
cgroup = f"/sys/fs/cgroup/system.slice/{os.environ['FAKE_EMULATOR_UNIT']}/"
redirect = {
    "/proc/loadavg": f"{root}/proc/loadavg",
    "/proc/meminfo": f"{root}/proc/meminfo",
    f"/proc/{os.environ['FAKE_EMULATOR_PID']}/cmdline": f"{root}/proc/emulator.cmdline",
}

sys.path.insert(0, os.environ["FAKE_GATEWAY_PATH"])
from videobridge_gateway import gateway_server  # noqa: E402
from videobridge_gateway.adapters import host_files  # noqa: E402


def fake_host_open(file, *args, **kwargs):
    path = os.fspath(file) if isinstance(file, (str, os.PathLike)) else file
    if isinstance(path, str):
        if path in redirect:
            path = redirect[path]
        elif path.startswith(cgroup):
            path = f"{root}/cgroup/{path[len(cgroup):]}"
    return builtins.open(path, *args, **kwargs)


class ReusePortSite(web.TCPSite):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("reuse_port", True)
        super().__init__(*args, **kwargs)


host_files.open = fake_host_open
web.TCPSite = ReusePortSite
gateway_server.run_main()
