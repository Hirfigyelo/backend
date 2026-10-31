import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from logging import getLogger
from typing import Any, Awaitable, Callable, Coroutine

_logger = getLogger(__name__)

@dataclass(slots=True)
class Cache[T]:

	@dataclass(slots=True)
	class Entry[T]:
		key: str
		obj: T
		created: datetime = field(default_factory=lambda: datetime.now(UTC))

	ON_EMPTY: Callable[[], Any] = lambda: ...
	queue: deque[Entry] = field(default_factory=lambda: deque())
	CLEANUP_AFTER: timedelta = field(default_factory=lambda: timedelta(minutes=15))
	LOCK: asyncio.Lock = field(default_factory=lambda: asyncio.Lock())
	async def cleanup(self):
		now = datetime.now(UTC)
		before_len = len(self.queue)
		async with self.LOCK:
			while len(self.queue) > 0 and (now - self.queue[0].created) > self.CLEANUP_AFTER:
				self.queue.popleft()
		if len(self.queue) == 0 and before_len != 0:
			self.ON_EMPTY()

	async def add(self, key: str, obj: T) -> None:
		async with self.LOCK:
			self.queue.append(
				self.Entry(key, obj)
			)
	async def clear(self) -> None:
		async with self.LOCK:
			self.queue.clear()

	def _find(self, key: str) -> Entry | None:
		for entry in self.queue:
			if entry.key == key:
				return entry
		return None

	async def get(self, key: str) -> Entry | None:
		await self.cleanup()
		async with self.LOCK:
			return self._find(key)

	async def get_or_compute(self, key: str, factory: Callable[[], Awaitable[T]]) -> T:
		entry = await self.get(key)
		if entry is not None:
			return entry.obj
		async with self.LOCK:
			entry = self._find(key)
			if entry is not None:
				return entry.obj
			value = await factory()
			self.queue.append(self.Entry(key, value))
			return value

LONG_RUNNING: tuple[asyncio.Task] = () # Set in main.py
CACHES: dict[str, Cache] = {

}

runtime_task: asyncio.Task = None
async def start():
	global runtime_task
	async def inner_loop():
		while True:
			try:
				tasks: list[Coroutine[Any, Any, None]] = []
				for cache in CACHES.values():
					tasks.append(cache.cleanup())
				await asyncio.gather(*tasks)
			except asyncio.CancelledError:
				return
			except Exception:
				_logger.exception("An exception occurred during cache cleanup")

			await asyncio.sleep(15*60)
	runtime_task = asyncio.create_task(inner_loop())
def get(key: str):
	return CACHES.get(key)
async def stop():
	global runtime_task, LONG_RUNNING
	for task in LONG_RUNNING:
		task.cancel()
	runtime_task.cancel()
	await asyncio.gather(runtime_task, *LONG_RUNNING, return_exceptions=True)
