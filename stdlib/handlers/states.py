from aiogram.fsm.state import StatesGroup, State


class BotStates(StatesGroup):
    FILLING = State()
    REWORK = State()
    SU_REJECT = State()
    REGISTERING = State()
    REGISTERING_POSITION = State()
    WAITING_SIGNATURE = State()
    FREE_FORM = State()
    REVIEW = State()
