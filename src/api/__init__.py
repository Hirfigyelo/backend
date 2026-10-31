from fastapi import APIRouter, status

from api.v1 import router as v1Router

router = APIRouter(
	prefix="",
	tags=[],
	responses={status.HTTP_404_NOT_FOUND: {"description": "Not found"}}
)
router.include_router(v1Router)
