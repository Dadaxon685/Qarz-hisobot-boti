
from aiogram.filters.state import State, StatesGroup
# --- FSM (Holatlar) ---
class ShopRegistration(StatesGroup):
    name = State()
    owner_id = State()
    phone = State()
    address = State()
    confirm = State()

class BroadcastState(StatesGroup):
    message = State()



class PaymentStates(StatesGroup):
    waiting_for_phone_last4 = State()   # 4 ta raqam kutish
    waiting_for_select_debt = State()   # Qaysi qarzligini tanlash
    waiting_for_partial_amount = State() # Qisman to'lov summasini kutish

class ShopSearchStates(StatesGroup):
    waiting_for_query = State()  # Ism yoki tel kutish

class ShopBroadcast(StatesGroup):
    waiting_for_message = State()