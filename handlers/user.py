import os
import hashlib
from aiogram import Router, F, types
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    WebAppInfo
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from handlers.connections import get_connection

user_router = Router()

SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "5148276461"))
SECRET_KEY = os.getenv("SECRET_KEY", "qarz-tizimi-secret-2024")
SHOP_WEB_URL = os.getenv("SHOP_WEB_URL", "")
ADMIN_WEB_URL = os.getenv("ADMIN_WEB_URL", "")


class ShopApply(StatesGroup):
    name = State()
    phone = State()
    address = State()
    confirm = State()


def gen_token(tid: int) -> str:
    return hashlib.sha256(f"{tid}{SECRET_KEY}".encode()).hexdigest()[:16]

def phone_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📱 Raqamni yuborish", request_contact=True)],
        [KeyboardButton(text="❌ Bekor qilish")]
    ], resize_keyboard=True, one_time_keyboard=True)

def location_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📍 Joylashuvni yuborish", request_location=True)],
        [KeyboardButton(text="📝 Qo'lda yozish")],
        [KeyboardButton(text="❌ Bekor qilish")]
    ], resize_keyboard=True, one_time_keyboard=True)

def cancel_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏪 Do'kon ochish", callback_data="open_shop")],
    ])

def panel_kb(owner_id, shop_name, is_admin=False):
    token = gen_token(owner_id)
    if is_admin:
        url = f"{ADMIN_WEB_URL}?token={token}&id={owner_id}"
        base = ADMIN_WEB_URL
        label = "⚙️ Admin Panelni Ochish"
    else:
        url = f"{SHOP_WEB_URL}?token={token}&id={owner_id}"
        base = SHOP_WEB_URL
        label = f"🏪 {shop_name} — Panelni Ochish"
    if base.startswith("https"):
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))
        ]])
    return None


# ============================================================
# /START — telefon so'rash
# ============================================================

@user_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    name = message.from_user.full_name

    # SUPER ADMIN
    if uid == SUPER_ADMIN_ID:
        kb = panel_kb(uid, "Admin", is_admin=True)
        if kb:
            return await message.answer(f"👑 <b>Xush kelibsiz, Boss!</b>", reply_markup=kb, parse_mode="HTML")
        return await message.answer("👑 <b>Xush kelibsiz, Boss!</b>", parse_mode="HTML")

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Do'kon egasi
        cursor.execute("SELECT id, name FROM shops WHERE owner_id=%s", (uid,))
        shop = cursor.fetchone()
        if shop:
            kb = panel_kb(uid, shop[1])
            text = f"✅ <b>Xush kelibsiz, {name}!</b>\n\n🏪 <b>{shop[1]}</b> do'koningiz tayyor."
            if kb:
                return await message.answer(text, reply_markup=kb, parse_mode="HTML")
            return await message.answer(text, parse_mode="HTML")

    finally:
        if conn: conn.close()

    # Yangi foydalanuvchi — telefon so'rash
    await message.answer(
        f"👋 <b>Assalomu alaykum, {name}!</b>\n\n"
        f"Qarzlaringizni tekshirish yoki do'kon ochish uchun "
        f"telefon raqamingizni yuboring 👇",
        reply_markup=phone_kb(), parse_mode="HTML"
    )


# ============================================================
# KONTAKT QABUL QILISH — qarzlarni tekshirish
# ============================================================

@user_router.message(F.contact)
async def handle_contact(message: Message, state: FSMContext):
    current = await state.get_state()

    # Do'kon arizasida telefon
    if current == ShopApply.phone:
        phone = message.contact.phone_number
        if not phone.startswith('+'): phone = '+' + phone
        await state.update_data(phone=phone)
        await state.set_state(ShopApply.address)
        await message.answer(
            "3️⃣ <b>Do'kon joylashuvini yuboring</b> yoki qo'lda yozing:",
            reply_markup=location_kb(), parse_mode="HTML"
        )
        return

    # Qarz tekshirish
    phone = message.contact.phone_number
    if not phone.startswith('+'): phone = '+' + phone
    uid = message.from_user.id

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Telegram ID ni phone bilan bog'lash
        cursor.execute("UPDATE debts SET customer_id=%s WHERE customer_phone=%s AND customer_id IS NULL", (uid, phone))
        conn.commit()

        # Qarzlarni ko'rish
        cursor.execute("""
            SELECT d.amount, d.due_date, s.name
            FROM debts d JOIN shops s ON s.id=d.shop_id
            WHERE d.customer_phone=%s AND d.status='unpaid'
        """, (phone,))
        debts = cursor.fetchall()

        # Do'kon egasimi?
        cursor.execute("SELECT id, name FROM shops WHERE owner_id=%s", (uid,))
        shop = cursor.fetchone()

        if not debts and not shop:
            await message.answer(
                "✅ <b>Yaxshi xabar!</b>\n\nBu raqamda faol qarz topilmadi.",
                reply_markup=ReplyKeyboardRemove(), parse_mode="HTML"
            )
            await message.answer(
                "Do'kon ochmoqchimisiz?",
                reply_markup=main_menu_kb()
            )
            return

        if debts:
            total = sum(float(d[0]) for d in debts)
            text = f"📋 <b>{phone} raqamidagi qarzlar:</b>\n\n"
            for amount, due_date, shop_name in debts:
                text += f"🏪 <b>{shop_name}</b>\n💰 {float(amount):,.0f} so'm\n📅 {due_date}\n────────────────\n"
            text += f"\n💵 <b>Jami: {total:,.0f} so'm</b>"
            await message.answer(text, reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")

        if shop:
            kb = panel_kb(uid, shop[1])
            if kb:
                await message.answer(f"🏪 <b>{shop[1]}</b> panelingiz:", reply_markup=kb, parse_mode="HTML")
        else:
            await message.answer("🏪 Do'kon ochmoqchimisiz?", reply_markup=main_menu_kb())

    finally:
        if conn: conn.close()


# ============================================================
# BEKOR QILISH
# ============================================================

@user_router.message(F.text == "❌ Bekor qilish")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🚫 Bekor qilindi.", reply_markup=ReplyKeyboardRemove())


# ============================================================
# DO'KON OCHISH ARIZASI
# ============================================================

@user_router.callback_query(F.data == "open_shop")
async def apply_start(callback: types.CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM shops WHERE owner_id=%s", (uid,))
        if cursor.fetchone():
            await callback.answer("Sizda allaqachon do'kon bor!", show_alert=True)
            return
    finally:
        if conn: conn.close()

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
    await message.answer(
        "2️⃣ <b>Telefon raqamingizni yuboring:</b>",
        reply_markup=phone_kb(), parse_mode="HTML"
    )

@user_router.message(ShopApply.phone, F.text)
async def apply_phone_text(message: Message, state: FSMContext):
    # Qo'lda yozilgan raqam
    phone = message.text.strip()
    if not phone.startswith('+'): phone = '+' + phone
    await state.update_data(phone=phone)
    await state.set_state(ShopApply.address)
    await message.answer(
        "3️⃣ <b>Do'kon joylashuvini yuboring:</b>",
        reply_markup=location_kb(), parse_mode="HTML"
    )

@user_router.message(ShopApply.address, F.location)
async def apply_address_location(message: Message, state: FSMContext):
    lat = message.location.latitude
    lon = message.location.longitude
    address = f"📍 {lat:.4f}, {lon:.4f}"
    await state.update_data(address=address)
    await show_confirm(message, state)

@user_router.message(ShopApply.address, F.text == "📝 Qo'lda yozish")
async def apply_address_manual_prompt(message: Message, state: FSMContext):
    await message.answer("Manzilni yozing:", reply_markup=cancel_kb())

@user_router.message(ShopApply.address, F.text)
async def apply_address_text(message: Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("🚫 Bekor qilindi.", reply_markup=ReplyKeyboardRemove())
        return
    await state.update_data(address=message.text.strip())
    await show_confirm(message, state)

async def show_confirm(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.set_state(ShopApply.confirm)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Yuborish", callback_data="apply_confirm"),
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
            f"👤 {uname}\n🆔 <code>{uid}</code>\n"
            f"🏪 {data['name']}\n📞 {data['phone']}\n📍 {data['address']}\n"
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
    d = {'name': 'Yangi Dokon', 'phone': '', 'address': ''}
    for line in lines:
        line = line.strip()
        if line.startswith("🏪") and "ARIZA" not in line: d['name'] = line.replace("🏪","").strip()
        elif line.startswith("📞"): d['phone'] = line.replace("📞","").strip()
        elif line.startswith("📍"): d['address'] = line.replace("📍","").strip()

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO shops (name,owner_id,phone,address) VALUES (%s,%s,%s,%s)",
            (d['name'], uid, d['phone'], d['address']))
        conn.commit()

        kb = panel_kb(uid, d['name'])
        await callback.bot.send_message(
            chat_id=uid,
            text=(
                f"🎉 <b>Tabriklaymiz!</b>\n\n"
                f"✅ <b>{d['name']}</b> do'koningiz tasdiqlandi!\n\n"
                f"Panelni ochish uchun quyidagi tugmani bosing 👇"
            ),
            reply_markup=kb, parse_mode="HTML"
        )
        await callback.message.edit_text(callback.message.text + "\n\n✅ <b>TASDIQLANDI</b>", parse_mode="HTML")
    except Exception as e:
        await callback.answer(f"Xato: {e}", show_alert=True)
    finally:
        if conn: conn.close()
    await callback.answer()


@user_router.callback_query(F.data.startswith("reject_"))
async def reject_shop(callback: types.CallbackQuery):
    uid = int(callback.data.split("_")[1])
    await callback.bot.send_message(uid, "😔 Do'kon ochish arizangiz rad etildi.")
    await callback.message.edit_text(callback.message.text + "\n\n❌ <b>RAD ETILDI</b>", parse_mode="HTML")
    await callback.answer()
