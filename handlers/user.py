import os
import hashlib
from aiogram import Router, F, types
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, WebAppInfo
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from handlers.connections import get_connection

user_router = Router()

SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "5148276461"))
SECRET_KEY = os.getenv("SECRET_KEY", "qarz-tizimi-secret-2024")
SHOP_WEB_URL = os.getenv("SHOP_WEB_URL", "")
ADMIN_WEB_URL = os.getenv("ADMIN_WEB_URL", "")
USE_WEBAPP = SHOP_WEB_URL.startswith("https")


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
        [InlineKeyboardButton(text="🏪 Do'kon ochish", callback_data="open_shop")],
    ])

def phone_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Telefon raqamimni yuborish", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )

def cancel_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )


# ============================================================
# /START
# ============================================================

@user_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    name = message.from_user.full_name

    # SUPER ADMIN
    if uid == SUPER_ADMIN_ID:
        if USE_WEBAPP and ADMIN_WEB_URL.startswith("https"):
            token = gen_token(uid)
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="⚙️ Admin Panelni Ochish",
                    web_app=WebAppInfo(url=f"{ADMIN_WEB_URL}?token={token}&id={uid}")
                )
            ]])
            return await message.answer(
                f"👑 <b>Xush kelibsiz, Boss!</b>",
                reply_markup=kb, parse_mode="HTML"
            )
        return await message.answer(
            f"👑 <b>Xush kelibsiz, Boss!</b>\n\nAdmin panel tayyor.",
            parse_mode="HTML"
        )

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # MASKANCHI
        cursor.execute("SELECT id, name FROM shops WHERE owner_id = %s", (uid,))
        shop = cursor.fetchone()
        if shop:
            shop_id, shop_name = shop
            if USE_WEBAPP:
                token = gen_token(uid)
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text=f"🏪 {shop_name} — Panelni Ochish",
                        web_app=WebAppInfo(url=f"{SHOP_WEB_URL}?token={token}&id={uid}")
                    )
                ]])
            else:
                from buttons import shop_keyboard
                return await message.answer(
                    f"✅ <b>Xush kelibsiz, {name}!</b>\n🏪 <b>{shop_name}</b>",
                    reply_markup=shop_keyboard(), parse_mode="HTML"
                )
            return await message.answer(
                f"✅ <b>Xush kelibsiz, {name}!</b>\n🏪 <b>{shop_name}</b>",
                reply_markup=kb, parse_mode="HTML"
            )

        # ODDIY FOYDALANUVCHI — telefon raqami bazada bormi?
        cursor.execute("SELECT phone FROM users WHERE telegram_id = %s", (uid,))
        user_row = cursor.fetchone()

        if user_row and user_row[0]:
            # Raqam saqlangan — qarzlarni ko'rsat
            phone = user_row[0]
            await show_debts_by_phone(message, phone, conn)
        else:
            # Raqam yo'q — taklif qil
            await message.answer(
                f"👋 <b>Assalomu alaykum, {name}!</b>\n\n"
                f"Qarzlaringizni tekshirish uchun telefon raqamingizni yuboring.\n"
                f"Bu <b>bir marta</b> amalga oshiriladi — keyingi safar avtomatik ko'rsatiladi 📱",
                reply_markup=phone_kb(),
                parse_mode="HTML"
            )

    finally:
        if conn: conn.close()


# ============================================================
# TELEFON RAQAMNI QABUL QILISH VA SAQLASH
# ============================================================

@user_router.message(F.contact)
async def handle_contact(message: Message):
    uid = message.from_user.id
    phone = message.contact.phone_number
    if not phone.startswith('+'): phone = '+' + phone

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # users jadvalida saqlash/yangilash
        cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (uid,))
        existing = cursor.fetchone()

        if existing:
            cursor.execute(
                "UPDATE users SET phone = %s WHERE telegram_id = %s",
                (phone, uid)
            )
        else:
            cursor.execute(
                "INSERT INTO users (telegram_id, phone, full_name) VALUES (%s, %s, %s)",
                (uid, phone, message.from_user.full_name)
            )

        # Agar debts jadvalida shu telefon bilan yozuvlar bo'lsa — customer_id ni bog'lash
        cursor.execute(
            "UPDATE debts SET customer_id = %s WHERE customer_phone = %s AND customer_id IS NULL",
            (uid, phone)
        )
        conn.commit()

        await message.answer(
            f"✅ <b>Raqamingiz saqlandi!</b>\n\n"
            f"Endi shu raqamga qarz yozilsa, sizga avtomatik xabar keladi 📩",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML"
        )

        # Qarzlarni ko'rsatish
        await show_debts_by_phone(message, phone, conn)

    finally:
        if conn: conn.close()


async def show_debts_by_phone(message: Message, phone: str, conn):
    """Telefon raqam bo'yicha qarzlarni ko'rsatish"""
    from datetime import datetime
    today = datetime.now().date()

    cursor = conn.cursor()
    cursor.execute("""
        SELECT d.amount, d.due_date, d.status, s.name
        FROM debts d JOIN shops s ON s.id = d.shop_id
        WHERE d.customer_phone = %s AND d.status = 'unpaid'
        ORDER BY d.debt_date DESC
    """, (phone,))
    debts = cursor.fetchall()

    if not debts:
        await message.answer(
            "✅ <b>Yaxshi xabar!</b>\n\nHozircha faol qarzingiz yo'q! 🎉",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML"
        )
        await message.answer("Boshqa amallar:", reply_markup=main_menu_kb())
        return

    total = sum(float(d[0]) for d in debts)
    overdue = 0
    text = f"📋 <b>Sizning qarzlaringiz:</b>\n━━━━━━━━━━━━━━━━━━\n\n"

    for amount, due_date, status, shop_name in debts:
        is_late = False
        try:
            p = due_date.split('.')
            if len(p) == 3:
                dd = datetime(int(p[2]), int(p[1]), int(p[0])).date()
                is_late = dd < today
                if is_late: overdue += 1
        except: pass

        late_tag = "\n   🔴 <b>Muddati o'tgan!</b>" if is_late else ""
        text += (
            f"🏪 <b>{shop_name}</b>\n"
            f"💰 {float(amount):,.0f} so'm\n"
            f"📅 Muddat: {due_date}{late_tag}\n\n"
        )

    text += f"━━━━━━━━━━━━━━━━━━\n💵 <b>Jami: {total:,.0f} so'm</b>"

    if overdue:
        text += f"\n🚨 <b>{overdue} ta qarzingiz muddati o'tgan!</b>"

    await message.answer(text, reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
    await message.answer("Boshqa amallar:", reply_markup=main_menu_kb())


# ============================================================
# BEKOR QILISH
# ============================================================

@user_router.message(F.text == "❌ Bekor qilish")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🚫 Bekor qilindi.", reply_markup=ReplyKeyboardRemove())
    await message.answer("Bosh menyu:", reply_markup=main_menu_kb())


# ============================================================
# QARZ TEKSHIRISH (inline tugma)
# ============================================================

@user_router.callback_query(F.data == "check_debt")
async def check_debt_cb(callback: types.CallbackQuery):
    uid = callback.from_user.id
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT phone FROM users WHERE telegram_id = %s", (uid,))
        row = cursor.fetchone()

        if row and row[0]:
            await show_debts_by_phone(callback.message, row[0], conn)
        else:
            await callback.message.answer(
                "📱 <b>Telefon raqamingizni yuboring:</b>\n\n"
                "Bir marta yuborsangiz — keyingi safar avtomatik ko'rsatiladi!",
                reply_markup=phone_kb(),
                parse_mode="HTML"
            )
    finally:
        if conn: conn.close()
    await callback.answer()


# ============================================================
# DO'KON OCHISH ARIZASI
# ============================================================

@user_router.callback_query(F.data == "open_shop")
async def apply_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ShopApply.name)
    await callback.message.answer(
        "🏪 <b>Do'kon ochish uchun ariza</b>\n\n1️⃣ Do'koningiz nomini kiriting:",
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
    await message.answer("3️⃣ Do'kon manzilini kiriting (shahar, ko'cha):")

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
        f"🏪 Do'kon: <b>{data['name']}</b>\n"
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
            f"🏪 <b>YANGI DO'KON ARIZASI!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>{uname}</b>\n"
            f"🆔 <code>{uid}</code>\n"
            f"🏪 {data['name']}\n"
            f"📞 {data['phone']}\n"
            f"📍 {data['address']}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        ),
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.message.edit_text(
        "✅ <b>Arizangiz yuborildi!</b>\n\nAdmin tez orada ko'rib chiqadi. 🙏",
        parse_mode="HTML"
    )
    await callback.answer()


@user_router.callback_query(F.data.startswith("approve_"))
async def approve_shop(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[1])
    lines = callback.message.text.split('\n')
    shop_data = {}
    for line in lines:
        if "🏪" in line and "ARIZASI" not in line: shop_data['name'] = line.replace("🏪", "").strip()
        if "📞" in line: shop_data['phone'] = line.replace("📞", "").strip()
        if "📍" in line: shop_data['address'] = line.replace("📍", "").strip()

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO shops (name, owner_id, phone, address) VALUES (%s, %s, %s, %s)",
            (shop_data.get('name'), uid, shop_data.get('phone'), shop_data.get('address'))
        )
        conn.commit()

        token = gen_token(uid)
        if USE_WEBAPP:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="🚀 Maskan Panelini Ochish",
                    web_app=WebAppInfo(url=f"{SHOP_WEB_URL}?token={token}&id={uid}")
                )
            ]])
        else:
            kb = None

        await callback.bot.send_message(
            chat_id=uid,
            text=(
                f"🎉 <b>Tabriklaymiz!</b>\n\n"
                f"✅ <b>{shop_data.get('name')}</b> do'koningiz tasdiqlandi!\n\n"
                f"Maskan panelingizni ochish uchun quyidagi tugmani bosing 👇"
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
        chat_id=uid,
        text="😔 <b>Afsuski...</b>\n\nDo'kon ochish arizangiz rad etildi.",
        parse_mode="HTML"
    )
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ <b>RAD ETILDI</b>", parse_mode="HTML"
    )
    await callback.answer()
