import os
import hashlib
from aiogram import Router, F, types
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardRemove, WebAppInfo
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from handlers.connections import get_connection

user_router = Router()

SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "5148276461"))
SECRET_KEY = os.getenv("SECRET_KEY", "qarz-tizimi-secret-2024")
SHOP_WEB_URL = os.getenv("SHOP_WEB_URL", "")
ADMIN_WEB_URL = os.getenv("ADMIN_WEB_URL", "")


class CheckDebt(StatesGroup):
    waiting_phone = State()

class ShopApply(StatesGroup):
    name = State()
    phone = State()
    address = State()
    confirm = State()


def gen_token(telegram_id: int) -> str:
    return hashlib.sha256(f"{telegram_id}{SECRET_KEY}".encode()).hexdigest()[:16]

def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Qarzlarimni tekshirish", callback_data="check_debt")],
        [InlineKeyboardButton(text="🏪 Maskan ochish", callback_data="open_shop")],
    ])

def cancel_kb():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

def make_panel_kb(owner_id: int, shop_name: str, is_admin=False):
    """Panel tugmasi — HTTPS bo'lsa WebApp, bo'lmasa oddiy URL"""
    token = gen_token(owner_id)
    if is_admin:
        url = f"{ADMIN_WEB_URL}?token={token}&id={owner_id}"
        base_url = ADMIN_WEB_URL
        label = "⚙️ Admin Panelni Ochish"
    else:
        url = f"{SHOP_WEB_URL}?token={token}&id={owner_id}"
        base_url = SHOP_WEB_URL
        label = f"🏪 {shop_name} — Panelni Ochish"

    if base_url.startswith("https"):
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))
        ]])
    else:
        return None


# ============================================================
# /START
# ============================================================

@user_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    name = message.from_user.full_name

    # 1. SUPER ADMIN
    if uid == SUPER_ADMIN_ID:
        kb = make_panel_kb(uid, "Admin", is_admin=True)
        text = f"👑 <b>Xush kelibsiz, Boss!</b>"
        if kb:
            return await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return await message.answer(text, parse_mode="HTML")

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 2. maskan EGASI
        cursor.execute("SELECT id, name FROM shops WHERE owner_id=%s", (uid,))
        shop = cursor.fetchone()
        if shop:
            shop_id, shop_name = shop
            kb = make_panel_kb(uid, shop_name)
            text = (
                f"✅ <b>Xush kelibsiz, {name}!</b>\n\n"
                f"🏪 <b>{shop_name}</b> maskaningiz tayyor."
            )
            if kb:
                return await message.answer(text, reply_markup=kb, parse_mode="HTML")
            return await message.answer(text, parse_mode="HTML")

        # 3. ODDIY FOYDALANUVCHI
        await message.answer(
            f"👋 <b>Assalomu alaykum, {name}!</b>\n\nQuyidagilardan birini tanlang:",
            reply_markup=main_menu_kb(), parse_mode="HTML"
        )
    finally:
        if conn: conn.close()


@user_router.message(F.text == "❌ Bekor qilish")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🚫 Bekor qilindi.", reply_markup=ReplyKeyboardRemove())
    await message.answer("Bosh menyu:", reply_markup=main_menu_kb())


# ============================================================
# QARZ TEKSHIRISH
# ============================================================

@user_router.callback_query(F.data == "check_debt")
async def check_debt_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(CheckDebt.waiting_phone)
    await callback.message.answer(
        "📞 <b>Telefon raqamingizni kiriting:</b>\nNamuna: <code>+998901234567</code>",
        reply_markup=cancel_kb(), parse_mode="HTML"
    )
    await callback.answer()

@user_router.message(CheckDebt.waiting_phone)
async def check_debt_result(message: Message, state: FSMContext):
    await state.clear()
    phone = message.text.strip()
    if not phone.startswith('+'): phone = '+' + phone

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT d.amount, d.due_date, s.name
            FROM debts d JOIN shops s ON s.id=d.shop_id
            WHERE d.customer_phone=%s AND d.status='unpaid'
        """, (phone,))
        debts = cursor.fetchall()

        if not debts:
            await message.answer(
                "✅ <b>Yaxshi xabar!</b>\n\nBu raqamda faol qarz topilmadi.",
                reply_markup=ReplyKeyboardRemove(), parse_mode="HTML"
            )
        else:
            total = sum(float(d[0]) for d in debts)
            text = f"📋 <b>{phone} raqamidagi qarzlar:</b>\n\n"
            for amount, due_date, shop_name in debts:
                text += f"🏪 <b>{shop_name}</b>\n💰 {float(amount):,.0f} so'm\n📅 {due_date}\n────────────────\n"
            text += f"\n💵 <b>Jami: {total:,.0f} so'm</b>"
            await message.answer(text, reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")

        await message.answer("Bosh menyu:", reply_markup=main_menu_kb())
    finally:
        if conn: conn.close()


# ============================================================
# maskan OCHISH ARIZASI
# ============================================================

@user_router.callback_query(F.data == "open_shop")
async def apply_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ShopApply.name)
    await callback.message.answer(
        "🏪 <b>Maskan ochish uchun ariza</b>\n\n1️⃣ Maskaningiz nomini kiriting:",
        reply_markup=cancel_kb(), parse_mode="HTML"
    )
    await callback.answer()

@user_router.message(ShopApply.name)
async def apply_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(ShopApply.phone)
    await message.answer("2️⃣ Telefon raqamingizni kiriting:")

@user_router.message(ShopApply.phone)
async def apply_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    await state.set_state(ShopApply.address)
    await message.answer("3️⃣ Maskan joylashuvini kiriting:")

@user_router.message(ShopApply.address)
async def apply_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text.strip())
    data = await state.get_data()
    await state.set_state(ShopApply.confirm)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="apply_confirm"),
        InlineKeyboardButton(text="❌ Bekor", callback_data="apply_cancel"),
    ]])
    await message.answer(
        f"📝 <b>Ariza ma'lumotlari:</b>\n\n"
        f"🏪 Maskan: <b>{data['name']}</b>\n"
        f"📞 Tel: <b>{data['phone']}</b>\n"
        f"📍 Manzil: <b>{data['address']}</b>\n\nTo'g'rimi?",
        reply_markup=kb, parse_mode="HTML"
    )

@user_router.callback_query(ShopApply.confirm, F.data == "apply_cancel")
async def apply_cancel_cb(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Ariza bekor qilindi.")
    await callback.message.answer("Bosh menyu:", reply_markup=main_menu_kb())
    await callback.answer()

@user_router.callback_query(ShopApply.confirm, F.data == "apply_confirm")
async def apply_confirm_cb(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    uid = callback.from_user.id
    uname = callback.from_user.full_name
    await state.clear()

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_{uid}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_{uid}"),
    ]])
    await callback.bot.send_message(
        chat_id=SUPER_ADMIN_ID,
        text=(
            f"🏪 <b>YANGI MASKAN ARIZASI!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 {uname}\n🆔 <code>{uid}</code>\n"
            f"🏪 {data['name']}\n📞 {data['phone']}\n📍 {data['address']}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        ),
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.message.edit_text("✅ <b>Arizangiz yuborildi!</b> 🙏", parse_mode="HTML")
    await callback.answer()


@user_router.callback_query(F.data.startswith("approve_"))
async def approve_shop(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[1])
    lines = callback.message.text.split('\n')
    shop_data = {'name': 'Yangi Dokon', 'phone': '', 'address': ''}
    for line in lines:
        line = line.strip()
        if line.startswith("🏪") and "ARIZA" not in line:
            shop_data['name'] = line.replace("🏪","").strip()
        elif line.startswith("📞"):
            shop_data['phone'] = line.replace("📞","").strip()
        elif line.startswith("📍"):
            shop_data['address'] = line.replace("📍","").strip()

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO shops (name,owner_id,phone,address) VALUES (%s,%s,%s,%s)",
            (shop_data['name'], uid, shop_data['phone'], shop_data['address'])
        )
        conn.commit()

        kb = make_panel_kb(uid, shop_data['name'])
        await callback.bot.send_message(
            chat_id=uid,
            text=(
                f"🎉 <b>Tabriklaymiz!</b>\n\n"
                f"✅ <b>{shop_data['name']}</b> maskaningiz tasdiqlandi!\n\n"
                f"Panelni ochish uchun quyidagi tugmani bosing 👇"
            ),
            reply_markup=kb, parse_mode="HTML"
        )
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ <b>TASDIQLANDI</b>", parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"Xato: {e}", show_alert=True)
    finally:
        if conn: conn.close()
    await callback.answer()


@user_router.callback_query(F.data.startswith("reject_"))
async def reject_shop(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[1])
    await callback.bot.send_message(
        uid, "😔 maskan ochish arizangiz rad etildi.", parse_mode="HTML"
    )
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ <b>RAD ETILDI</b>", parse_mode="HTML"
    )
    await callback.answer()
