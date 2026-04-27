from aiogram import Router

from stdlib.handlers.superuser.approve import router as approve_router
from stdlib.handlers.superuser.reject import router as reject_router
from stdlib.handlers.superuser.cmds import router as cmds_router

router = Router()
router.include_router(approve_router)
router.include_router(reject_router)
router.include_router(cmds_router)
