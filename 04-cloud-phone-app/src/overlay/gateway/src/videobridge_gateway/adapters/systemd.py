"""systemd, read with "systemctl show" (no privilege needed)."""

import asyncio


async def show(unit, properties):
    """The text of "systemctl show UNIT --property=..." for these
    properties, or None when systemctl did not answer within 3 s."""
    try:
        process = await asyncio.create_subprocess_exec(
            "systemctl", "show", unit, f"--property={','.join(properties)}",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        output, _ = await asyncio.wait_for(process.communicate(), timeout=3)
    except (OSError, asyncio.TimeoutError):
        return None
    return output.decode(errors="replace")
