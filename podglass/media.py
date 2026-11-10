"""Pause/resume media players and duck the volume. Commands run through an injectable runner.

pause/resume: `playerctl`, only the players that were playing. duck/restore: `wpctl` on the
default sink (off unless `ca_duck = true` in config.toml).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

log = logging.getLogger(__name__)

Runner = Callable[[list[str]], Awaitable[tuple[int, str]]]
SINK = "@DEFAULT_AUDIO_SINK@"


async def run(args: list[str]) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.DEVNULL)
    except FileNotFoundError:
        log.warning("media: %s not installed", args[0])
        return 127, ""
    out, _ = await proc.communicate()
    return proc.returncode, out.decode(errors="replace")


class Media:
    def __init__(self, runner: Runner = run):
        self.run = runner
        self.paused: list[str] = []  # players we paused, to resume only those
        self.saved_volume: float | None = None

    async def pause(self) -> None:
        code, out = await self.run(["playerctl", "-l"])
        if code != 0:
            return
        for player in out.split():
            code, status = await self.run(["playerctl", "-p", player, "status"])
            if code == 0 and status.strip() == "Playing":
                await self.run(["playerctl", "-p", player, "pause"])
                if player not in self.paused:
                    self.paused.append(player)

    async def resume(self) -> None:
        players, self.paused = self.paused, []
        for player in players:
            await self.run(["playerctl", "-p", player, "play"])

    async def duck(self, volume: float) -> None:
        if self.saved_volume is not None:
            return
        code, out = await self.run(["wpctl", "get-volume", SINK])
        try:
            current = float(out.split()[1]) if code == 0 else None  # "Volume: 0.40 [MUTED]"
        except (IndexError, ValueError):
            current = None
        if current is None or current <= volume:
            return
        self.saved_volume = current
        await self.run(["wpctl", "set-volume", SINK, f"{volume:.2f}"])

    async def restore(self) -> None:
        if self.saved_volume is None:
            return
        volume, self.saved_volume = self.saved_volume, None
        await self.run(["wpctl", "set-volume", SINK, f"{volume:.2f}"])
