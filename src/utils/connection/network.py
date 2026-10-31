from asyncio import Event, Lock
from contextlib import AbstractAsyncContextManager
from enum import IntEnum, auto
from json import loads
from typing import Any, Awaitable, Callable, Literal, overload

from aiohttp import ClientResponse, ClientSession
from aiohttp.cookiejar import DummyCookieJar
from fastapi import HTTPException
from fastapi.concurrency import asynccontextmanager


class NetworkError(HTTPException):
	pass

class ReturnType(IntEnum):
	JSON = auto()
	TEXT = auto()
	BIN = auto()

__session: ClientSession | None = None
__closing = False
__active_ops = 0
__active_ops_done = Event()
__active_ops_done.set()
__lock = Lock()

type ResponseProvider = Callable[[Any], Awaitable[dict[str, Any]]]

#region POST
@overload
def post(url:str, return_type: Literal[ReturnType.JSON] = ReturnType.JSON, /, *, response_provider: ResponseProvider | None = None, resp_state: str | None = None, **kwargs: Any) -> AbstractAsyncContextManager[dict[str, Any]]: ...
@overload
def post(url:str, return_type: Literal[ReturnType.TEXT], /, *, response_provider: ResponseProvider | None = None, resp_state: str | None = None, **kwargs: Any) -> AbstractAsyncContextManager[str]: ...
@overload
def post(url:str, return_type: Literal[ReturnType.BIN], /, *, response_provider: ResponseProvider | None = None, resp_state: str | None = None, **kwargs: Any) -> AbstractAsyncContextManager[bytes]: ...
@asynccontextmanager
async def post(url:str, return_type: ReturnType = ReturnType.JSON, /, *, response_provider: ResponseProvider | None = None, resp_state: str | None = None, **kwargs):
	async with request("POST", url, return_type, response_provider=response_provider, resp_state=resp_state, **kwargs) as resp:
		yield resp
#endregion
#region GET
@overload
def get(url:str, return_type: Literal[ReturnType.JSON] = ReturnType.JSON, /, *, response_provider: ResponseProvider | None = None, resp_state: str | None = None, **kwargs: Any) -> AbstractAsyncContextManager[dict[str, Any]]: ...
@overload
def get(url:str, return_type: Literal[ReturnType.TEXT], /, *, response_provider: ResponseProvider | None = None, resp_state: str | None = None, **kwargs: Any) -> AbstractAsyncContextManager[str]: ...
@overload
def get(url:str, return_type: Literal[ReturnType.BIN], /, *, response_provider: ResponseProvider | None = None, resp_state: str | None = None, **kwargs: Any) -> AbstractAsyncContextManager[bytes]: ...
@asynccontextmanager
async def get(url:str, return_type: ReturnType = ReturnType.JSON, /, *, response_provider: ResponseProvider | None = None, resp_state: str | None = None, **kwargs):
	async with request("GET", url, return_type, response_provider=response_provider, resp_state=resp_state, **kwargs) as resp:
		yield resp
#endregion
#region Request
@overload
def request(method: str, url:str, return_type: Literal[ReturnType.JSON] = ReturnType.JSON, /, *, response_provider: ResponseProvider | None = None, resp_state: str | None = None, **kwargs: Any) -> AbstractAsyncContextManager[dict[str, Any]]: ...
@overload
def request(method: str, url:str, return_type: Literal[ReturnType.TEXT], /, *, response_provider: ResponseProvider | None = None, resp_state: str | None = None, **kwargs: Any) -> AbstractAsyncContextManager[str]: ...
@overload
def request(method: str, url:str, return_type: Literal[ReturnType.BIN], /, *, response_provider: ResponseProvider | None = None, resp_state: str | None = None, **kwargs: Any) -> AbstractAsyncContextManager[bytes]: ...
@asynccontextmanager
async def request(method:str, url:str, return_type: ReturnType = ReturnType.JSON, /, *, response_provider: ResponseProvider | None = None, resp_state: str | None = None, **kwargs):
	async with operation() as session:
		if response_provider is not None:
			yield await response_provider(resp_state)
		else:
			async with session.request(method, url, **kwargs) as resp:
				resp.raise_for_status()
				yield await handle_response(resp=resp, convert=return_type)
#endregion
@asynccontextmanager
async def operation():
	session = await _enter_op()
	try:
		yield session
	finally:
		await _exit_op()

async def start():
	global __session, __closing
	async with __lock:
		if __session is not None and not __session.closed:
			return
		__closing = False
		__session = ClientSession(headers={"User-Agent": "ThunderAPI/1.0"}, cookie_jar=DummyCookieJar())

async def close():
	global __closing, __session
	async with __lock:
		__closing = True

	await __active_ops_done.wait()

	async with __lock:
		if __session is not None and not __session.closed:
			await __session.close()
		__session = None

#region handle_response
@overload
async def handle_response(resp: ClientResponse, convert: Literal[ReturnType.JSON]) -> dict[str, Any]: ...
@overload
async def handle_response(resp: ClientResponse, convert: Literal[ReturnType.BIN]) -> bytes: ...
@overload
async def handle_response(resp: ClientResponse, convert: Literal[ReturnType.TEXT]) -> str: ...
async def handle_response(resp:ClientResponse, convert:ReturnType) -> dict[str, Any]|bytes|str:
	content = await resp.read()

	match convert:
		case ReturnType.TEXT:
			return content.decode("utf-8")
		case ReturnType.JSON:
			return loads(content)
		case ReturnType.BIN:
			return content
	raise ValueError(f"Invalid ReturnType '{convert}'")
#endregion

async def _enter_op():
	global __active_ops
	async with __lock:
		if __closing:
			raise RuntimeError("NetworkManager is shutting down")

		if __session is None or __session.closed:
			raise RuntimeError("NetworkManager is not started")

		__active_ops += 1
		__active_ops_done.clear()

		return __session

async def _exit_op():
	global __active_ops
	async with __lock:
		__active_ops -= 1

		if __active_ops <= 0:
			__active_ops = 0
			__active_ops_done.set()
