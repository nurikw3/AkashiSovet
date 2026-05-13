from aiogram.fsm.state import StatesGroup, State


class BotStates(StatesGroup):
    START_CHOICE = State()
    WAITING_MAIN_PDF = State()
    FILLING = State()
    REWORK = State()
    SU_REJECT = State()
    REGISTERING = State()
    REGISTERING_POSITION = State()
    WAITING_SIGNATURE = State()
    FREE_FORM = State()
    REVIEW = State()
