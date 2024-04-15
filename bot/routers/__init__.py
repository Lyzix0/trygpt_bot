__all__ = ("router",)

from aiogram import Router

from .callbacks import router as callbacks_router

router = Router(name=__name__)

router.include_routers(callbacks_router)
