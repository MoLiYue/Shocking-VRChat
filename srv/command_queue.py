"""Command priority queue for managing multiple input sources."""
import asyncio
import time
from enum import IntEnum
from dataclasses import dataclass, field


class CommandPriority(IntEnum):
    """Lower value = higher priority."""
    API = 0
    OSC_PANEL = 1
    OSC_INTERACTION = 2
    GAME = 3


@dataclass(order=True)
class Command:
    priority: int
    timestamp: float = field(compare=True)
    channel: str = field(compare=False)
    action: str = field(compare=False)  # 'wave', 'strength', 'clear'
    value: object = field(compare=False, default=None)
    source_id: str = field(compare=False, default='')

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


class CommandQueue:
    """Priority queue with per-source cooldown."""

    # Bounded so an OSC flood cannot grow memory and latency without limit.
    # At 100ms feeder ticks this is already far more backlog than is useful.
    DEFAULT_MAXSIZE = 512

    def __init__(self, maxsize: int = DEFAULT_MAXSIZE):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=maxsize)
        self._source_last_time: dict[str, float] = {}
        self._dropped = 0
        self._cooldowns: dict[CommandPriority, float] = {
            CommandPriority.API: 0,
            CommandPriority.OSC_PANEL: 0.1,
            CommandPriority.OSC_INTERACTION: 0.02,
            CommandPriority.GAME: 0.2,
        }
        self._enabled: dict[CommandPriority, bool] = {p: True for p in CommandPriority}

    @property
    def dropped(self) -> int:
        return self._dropped

    def set_cooldown(self, priority: CommandPriority, seconds: float):
        self._cooldowns[priority] = seconds

    def set_enabled(self, priority: CommandPriority, enabled: bool):
        self._enabled[priority] = enabled

    async def put(self, priority: CommandPriority, channel: str, action: str,
                  value=None, source_id: str = '') -> bool:
        """Add command if not in cooldown. Returns True if accepted."""
        if not self._enabled.get(priority, True):
            return False

        now = time.time()
        key = f"{priority.name}_{source_id}"
        cooldown = self._cooldowns.get(priority, 0)
        if key in self._source_last_time:
            if now - self._source_last_time[key] < cooldown:
                return False

        self._source_last_time[key] = now
        cmd = Command(
            priority=priority.value,
            timestamp=now,
            channel=channel,
            action=action,
            value=value,
            source_id=source_id,
        )
        try:
            self._queue.put_nowait(cmd)
        except asyncio.QueueFull:
            # Drop rather than block: awaiting here would stall the OSC
            # dispatch path and let the backlog grow unbounded.
            self._dropped += 1
            return False
        return True

    async def get(self) -> Command:
        """Get next command (blocks until available)."""
        return await self._queue.get()

    def task_done(self):
        self._queue.task_done()

    def empty(self) -> bool:
        return self._queue.empty()

    def clear(self):
        """Discard all pending commands, in place.

        Must not replace self._queue: a consumer already blocked on
        `await self._queue.get()` would keep waiting on the orphaned queue
        object forever and never see newly enqueued commands.
        """
        drained = 0
        while True:
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            self._queue.task_done()
            drained += 1
        self._source_last_time.clear()
        return drained
