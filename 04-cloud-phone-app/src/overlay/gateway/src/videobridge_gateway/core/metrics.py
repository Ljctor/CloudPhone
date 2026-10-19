"""Server metrics for the page's server panel and GET /api/v1/state: the
host's load, CPU and memory, the emulator unit's CPU and memory (its
cgroup), and Android's memory and frame rate.

No I/O: the texts of /proc, of the cgroup's files and of Android's adb
output come in (None: unreadable), figures come out.
"""


def parse_meminfo(text):
    """kB values of a /proc/meminfo text, by name."""
    values = {}
    for line in text.splitlines():
        name, _, rest = line.partition(":")
        if rest.split():
            try:
                values[name] = int(rest.split()[0])
            except ValueError:
                pass
    return values


def memory_summary(values):
    """MiB figures from meminfo values."""
    mib = lambda name: round(values[name] / 1024) if name in values else None
    return {
        "total": mib("MemTotal"), "available": mib("MemAvailable"),
        "swapTotal": mib("SwapTotal"),
        "swapUsed": mib("SwapTotal") - mib("SwapFree") if "SwapTotal" in values and "SwapFree" in values else None,
    }


def physical_cores(cpuinfo):
    """Physical cores in a /proc/cpuinfo text (with Hyper-Threading, two
    threads share each one), or None."""
    if cpuinfo is None:
        return None
    cores = set()
    for chunk in cpuinfo.split("\n\n"):
        fields = {}
        for line in chunk.splitlines():
            name, _, value = line.partition(":")
            fields[name.strip()] = value.strip()
        if "core id" in fields:
            cores.add((fields.get("physical id"), fields["core id"]))
    return len(cores) or None


def load(loadavg, cpus, cores):
    """{one, five, cpus, cores} from a /proc/loadavg text, or None."""
    try:
        one, five = (loadavg or "").split()[:2]
        return {"one": float(one), "five": float(five), "cpus": cpus, "cores": cores}
    except ValueError:
        return None


def cpu_jiffies(line):
    """(busy, total) jiffies of all host CPUs, from /proc/stat's first line."""
    values = [int(v) for v in line.split()[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values) - idle, sum(values)


def cpu_percent(busy, total, before):
    """The host's CPU use since before, (busy, total), in percent."""
    p_busy, p_total = before
    return round(100 * (busy - p_busy) / max(1, total - p_total))


def average_mhz(cpuinfo):
    """The mean "cpu MHz" of a /proc/cpuinfo text, or None."""
    mhz = [float(line.split(":")[1]) for line in (cpuinfo or "").splitlines() if line.startswith("cpu MHz")]
    return round(sum(mhz) / len(mhz)) if mhz else None


def cgroup_usage(stat):
    """usage_usec from a cgroup's cpu.stat text, or None."""
    usage = None
    if stat:
        usage = dict(line.split() for line in stat.splitlines() if len(line.split()) == 2).get("usage_usec")
    return int(usage) if usage else None


def core_percent(usage, p_usage, seconds):
    """CPU use in percent of one core, like top (400 = four cores busy),
    from two usage_usec readings seconds apart, or None."""
    if usage is None or p_usage is None:
        return None
    return round((usage - p_usage) / 1e4 / seconds)


def cgroup_memory_mb(current):
    """MiB from a cgroup's memory.current text, or None."""
    return round(int(current) / 1048576) if current and current.strip().isdigit() else None


def android_metrics(output):
    """Android's memory and the top layer's frame rate from the adb script's
    output: /proc/meminfo, ==TIMESTATS==, then SurfaceFlinger's timestats."""
    meminfo, _, timestats = output.partition("==TIMESTATS==")
    layer = fps = None
    for line in timestats.splitlines():
        name, _, value = line.strip().partition(" = ")
        if name == "layerName" and layer is None:
            # "<id> SurfaceView[com.example/...Activity](BLAST)#12": the package.
            layer = value.split("[", 1)[-1].split("/", 1)[0].split("]", 1)[0] if "[" in value else value
        elif name == "averageFPS" and layer is not None and fps is None:
            try:
                fps = round(float(value), 1)
            except ValueError:
                pass
    return {"memory": memory_summary(parse_meminfo(meminfo)), "app": layer, "fps": fps}
