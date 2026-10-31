import logging
from contextlib import asynccontextmanager
from logging.handlers import TimedRotatingFileHandler
from os import getenv, path

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from uvicorn import run as uvicorn_run

import utils.cache as Cache
import utils.connection.network as Network
from api import router
from api.shared import limiter
from config import DEBUG, HOST, LOGS_DIR, PORT, PROXIED

logger = logging.getLogger()

logging.getLogger("aiosqlite").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

tags_metadata = [
	{
		"name": "sample",
		"description": "description of tag"
	}
]

@asynccontextmanager
async def lifespan(app: FastAPI):
	await Network.start()
	await Cache.start()

	try:
		yield
	finally:
		await Cache.stop()
		await Network.close()

app = FastAPI(
	title="Hirkontextus",
	description="Híraggregáló REST API",
	version="1.0.0",
	openapi_tags=tags_metadata,
	lifespan=lifespan,
	redoc_url=None,
	docs_url="/",
	debug=DEBUG
)

#region Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(
	RateLimitExceeded,
	lambda request, exc: (
		logging.warning(f"Rate limit exceeded for {get_remote_address(request)}"),
		JSONResponse({"detail": "Rate limit exceeded"}, status_code=status.HTTP_429_TOO_MANY_REQUESTS)
	)[1]
)
#endregion

app.include_router(router)
app.add_middleware(SlowAPIMiddleware)

def main():
	# region Logging

	LOGS_DIR.mkdir(mode=0o755, exist_ok=True, parents=True)

	#region Handler and Formatter
	def log_namer(default_name:str):
		dirname = path.dirname(default_name)
		filename = path.basename(default_name)
		_, _, date = filename.rpartition(".")
		return path.join(dirname, f"{date}.log")
	handler = TimedRotatingFileHandler(LOGS_DIR / "latest.log", when="midnight", interval=1, utc=True, backupCount=5)
	handler.suffix = "%Y-%m-%d"
	formatter = logging.Formatter("%(asctime)s:%(name)-30s:%(funcName)-15s:%(lineno)-3d:%(levelname)-7s:%(message)s", datefmt="%Y-%m-%d %H:%M:%S")
	handler.setFormatter(formatter)
	handler.namer = log_namer
	logger.addHandler(handler)
	logger.propagate = False

	console_handler = logging.StreamHandler()
	console_handler.setFormatter(formatter)
	logger.addHandler(console_handler)
	#endregion

	#region Log level
	loglevel = getenv("LOG_LEVEL", "INFO")
	match loglevel.upper().strip():
		case "DEBUG":
			level = logging.DEBUG
		case "INFO":
			level = logging.INFO
		case "WARN", "WARNING":
			level = logging.WARNING
		case "ERROR":
			level = logging.ERROR
		case "FATAL", "CRITICAL":
			level = logging.CRITICAL
		case _:
			logger.warning("Invalid logging level entered, defaulting to 'INFO'")
			level = logging.INFO
	logger.setLevel(level)
	#endregion
	#region Replace uvicorn logger
	for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
		uvicorn_logger = logging.getLogger(name)

		uvicorn_logger.handlers.clear()

		uvicorn_logger.addHandler(handler)
		uvicorn_logger.setLevel(level)
		uvicorn_logger.propagate = False
	#endregion
	# endregion

	try:
		uvicorn_run(app, host=HOST, port=PORT, forwarded_allow_ips="*" if PROXIED else None)
	except Exception:
		logger.exception("An uncaught error occurred during runtime")
	finally:
		logger.info("Shutting down")

if __name__ == '__main__':
	main()
