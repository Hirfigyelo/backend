from slowapi import Limiter as _slowapiLimiter
from slowapi.util import get_remote_address as _gra

limiter = _slowapiLimiter(
	key_func= lambda request: _gra(request)
)
