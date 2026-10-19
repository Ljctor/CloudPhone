"""The ntfy.sh service: one HTTP POST per alert (see core/alerts.py).

The URL holds the topic, which is private: it is never logged.
"""

import asyncio
import logging

import aiohttp


async def post(url, text, headers):
    """Posts one alert; True when ntfy.sh took it. Never raises."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, data=text.encode("utf-8"), headers=headers) as response:
                if response.status >= 300:
                    logging.warning(f"Alert not taken: ntfy.sh answered {response.status}")
                    return False
                return True
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
        logging.warning(f"Alert not sent: {e!r}")
        return False
