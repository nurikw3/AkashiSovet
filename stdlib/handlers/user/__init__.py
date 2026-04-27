from aiogram import Router

from stdlib.handlers.user.start import router as start_router
from stdlib.handlers.user.filling import router as filling_router
from stdlib.handlers.user.free_form import router as free_form_router
from stdlib.handlers.user.files import router as files_router
from stdlib.handlers.user.review import router as review_router
from stdlib.handlers.user.rework import router as rework_router
from stdlib.handlers.user.common import router as common_router

router = Router()
router.include_router(start_router)
router.include_router(common_router)
router.include_router(filling_router)
router.include_router(free_form_router)
router.include_router(files_router)
router.include_router(review_router)
router.include_router(rework_router)
