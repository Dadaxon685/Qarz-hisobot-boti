import asyncio
import logging
from aiogram import Router, F, types
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
)
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import State, StatesGroup
from aiogram.filters import CommandStart
import os
import hashlib

from handlers.connections import get_connection

# ============================================================
# ROUTER VA SOZLAMALAR
# ============================================================

admin_router = Router()
SUPER_ADMIN_ID = 5148276461
SECRET_KEY = os.getenv("SECRET_KEY", "qarz-tizimi-secret-2024")
ADMIN_WEB_URL = os.getenv("ADMIN_WEB_URL", "")
USE_WEBAPP = ADMIN_WEB_URL.startswith("https")

admin_router.message.filter(F.from_user.id == SUPER_ADMIN_ID)


# ============================================================
# FSM HOLATLARI
# ============================================================

class ShopRegistration(StatesGroup):
    name = State()
    owner_id = State()
    phone = State()
    address = State()
    confirm = State()

class AdminStates(StatesGroup):
    waiting_for_ad_text = State()
    waiting_for_search_query = State()
    waiting_for_shop_id_to_delete = State()


# ============================================================
# HELPERS
# ============================================================

def gen_token(telegram_id: int) -> str:
    return hashlib.sha256(f"{telegram_id}{SECRET_KEY}".encode()).hexdigest()[:16]

def admin_keyboard():
    buttons = [
        [KeyboardButton(text="🏪 Maskan qo'shish"), KeyboardButton(text="🔍 Maskanni qidirish")],
        [KeyboardButton(text="📝 Maskanlar ro'yxati"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="📢 Reklama yuborish")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🚫 Bekor qilish")]],
        resize_keyboard=True
    )

def admin_panel_kb():
    """Admin uchun web panel tugmasi"""
    if not USE_WEBAPP:
        return None
    token = gen_token(SUPER_ADMIN_ID)
    url = f"{ADMIN_WEB_URL}?token={token}&id={SUPER_ADMIN_ID}"
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="⚙️ Admin Panelni Ochish",
            web_app=WebAppInfo(url=url)
        )
    ]])


# ============================================================
# START
# ============================================================

@admin_router.message(CommandStart())
async def admin_start(message: Message):
    kb = admin_panel_kb()
    text = (
        f"👑 <b>Xush kelibsiz, Boss!</b>\n\n"
        f"🤖 Bot faol va ishlayapti.\n"
        f"📊 Tizimni boshqarish uchun tugmalardan foydalaning."
    )
    if kb:
        await message.answer(text, reply_markup=admin_keyboard(), parse_mode="HTML")
        await message.answer("🌐 Web panel:", reply_markup=kb)
    else:
        await message.answer(text, reply_markup=admin_keyboard(), parse_mode="HTML")


@admin_router.message(F.text == "🚫 Bekor qilish")
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("📥 Jarayon bekor qilindi.", reply_markup=admin_keyboard())


# ============================================================
# MASKAN QO'SHISH (FSM)
# ============================================================

@admin_router.message(F.text == "🏪 Maskan qo'shish")
async def start_shop_reg(message: Message, state: FSMContext):
    await state.set_state(ShopRegistration.name)
    await message.answer("🏪 Maskan nomini kiriting:", reply_markup=cancel_keyboard())

@admin_router.message(ShopRegistration.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(ShopRegistration.owner_id)
    await message.answer("🆔 Maskan egasining Telegram ID raqamini yuboring:")

@admin_router.message(ShopRegistration.owner_id)
async def process_owner_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak!")
    await state.update_data(owner_id=int(message.text))
    await state.set_state(ShopRegistration.phone)
    await message.answer("📞 Telefon raqamini kiriting (+998XXXXXXXXX):")

@admin_router.message(ShopRegistration.phone)
async def process_phone(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.startswith('+'): phone = '+' + phone
    await state.update_data(phone=phone)
    await state.set_state(ShopRegistration.address)
    await message.answer("📍 Maskan manzilini kiriting:")

@admin_router.message(ShopRegistration.address)
async def shop_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    data = await state.get_data()

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_shop_yes"),
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="confirm_shop_no")
    ]])

    confirm_text = (
        f"📝 <b>Yangi Maskan ma'lumotlari:</b>\n\n"
        f"🏪 Nomi: <b>{data['name']}</b>\n"
        f"🆔 Egasi (ID): <code>{data['owner_id']}</code>\n"
        f"📞 Tel: <b>{data['phone']}</b>\n"
        f"📍 Manzil: <b>{message.text}</b>\n\n"
        f"Ma'lumotlar to'g'rimi?"
    )
    await state.set_state(ShopRegistration.confirm)
    await message.answer(confirm_text, reply_markup=kb, parse_mode="HTML")

@admin_router.callback_query(ShopRegistration.confirm, F.data.startswith("confirm_shop_"))
async def shop_confirm_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "confirm_shop_no":
        await state.clear()
        await callback.message.edit_text("❌ Maskan qo'shish bekor qilindi.")
        return await callback.answer()

    data = await state.get_data()
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO shops (name, owner_id, phone, address) VALUES (%s, %s, %s, %s)",
            (data['name'], data['owner_id'], data['phone'], data['address'])
        )
        conn.commit()
        await callback.message.edit_text(
            f"✅ <b>{data['name']}</b> Maskani qo'shildi!",
            parse_mode="HTML"
        )

        # Maskanchi uchun web panel tugmasi
        token = gen_token(data['owner_id'])
        shop_url = os.getenv("SHOP_WEB_URL", "")

        if USE_WEBAPP and shop_url.startswith("https"):
            url = f"{shop_url}?token={token}&id={data['owner_id']}"
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="🚀 Maskan Panelini Ochish",
                    web_app=WebAppInfo(url=url)
                )
            ]])
        else:
            kb = None

        try:
            await callback.bot.send_message(
                chat_id=data['owner_id'],
                text=(
                    f"🎉 <b>Tabriklaymiz!</b>\n\n"
                    f"✅ <b>{data['name']}</b> do'koningiz tizimga qo'shildi!\n\n"
                    f"Botdan foydalanish uchun /start bosing."
                ),
                reply_markup=kb,
                parse_mode="HTML"
            )
        except:
            await callback.message.answer(
                "⚠️ Maskanchiga xabar yetib bormadi (Botni bloklagan bo'lishi mumkin)."
            )

    except Exception as e:
        logging.error(f"Baza xatosi: {e}")
        await callback.message.answer(f"❌ Xatolik: {e}")
    finally:
        if conn: conn.close()
        await state.clear()
        await callback.answer()


# ============================================================
# MASKANLAR RO'YXATI VA O'CHIRISH
# ============================================================

@admin_router.message(F.text == "📝 Maskanlar ro'yxati")
async def list_shops_admin(message: Message, state: FSMContext):
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, s.name, s.owner_id,
                   COUNT(d.id) as debt_count,
                   COALESCE(SUM(d.amount), 0) as total
            FROM shops s
            LEFT JOIN debts d ON d.shop_id = s.id AND d.status = 'unpaid'
            GROUP BY s.id ORDER BY s.id
        """)
        shops = cursor.fetchall()

        if not shops:
            return await message.answer("Hozircha Maskanlar yo'q.")

        text = "🏬 <b>Tizimdagi Maskanlar:</b>\n\n"
        for s in shops:
            total = float(s[4])
            text += (
                f"🆔 <code>{s[0]}</code> | 🏪 <b>{s[1]}</b>\n"
                f"   👤 {s[2]} | 💰 {s[3]} qarz | {total:,.0f} so'm\n\n"
            )

        text += "❌ O'chirish uchun <b>ID</b> yuboring yoki 'bekor' deb yozing:"
        await state.set_state(AdminStates.waiting_for_shop_id_to_delete)
        await message.answer(text, parse_mode="HTML")
    finally:
        if conn: conn.close()

@admin_router.message(AdminStates.waiting_for_shop_id_to_delete)
async def process_shop_delete(message: Message, state: FSMContext):
    if message.text.lower() == 'bekor':
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=admin_keyboard())

    if not message.text.isdigit():
        return await message.answer("Iltimos, ID raqamini yuboring!")

    shop_id = int(message.text)
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, owner_id FROM shops WHERE id = %s", (shop_id,))
        shop = cursor.fetchone()

        if shop:
            cursor.execute("DELETE FROM shops WHERE id = %s", (shop_id,))
            conn.commit()
            await message.answer(
                f"✅ <b>{shop[0]}</b> Maskani o'chirildi.",
                parse_mode="HTML"
            )
            try:
                await message.bot.send_message(
                    chat_id=shop[1],
                    text="⚠️ Sizning maskaningiz tizimdan o'chirildi."
                )
            except: pass
        else:
            await message.answer("⚠️ Bunday ID topilmadi.")
    finally:
        if conn: conn.close()
        await state.clear()


# ============================================================
# REKLAMA YUBORISH
# ============================================================

@admin_router.message(F.text == "📢 Reklama yuborish")
async def start_broadcast(message: Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_ad_text)
    await message.answer(
        "📢 <b>Reklama yuborish</b>\n\nXabar matnini kiriting.\n"
        "Barcha do'konchilar va qarzdorlarga yuboriladi:",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )

@admin_router.message(AdminStates.waiting_for_ad_text)
async def process_broadcast(message: Message, state: FSMContext):
    ad_text = message.text
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT owner_id FROM shops")
        owners = [row[0] for row in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT customer_id FROM debts WHERE customer_id IS NOT NULL")
        customers = [row[0] for row in cursor.fetchall()]

        all_users = list(set(owners + customers))

        await message.answer(f"🚀 {len(all_users)} kishiga yuborilmoqda...")

        sent_count = 0
        for user_id in all_users:
            try:
                await message.bot.send_message(
                    user_id,
                    f"📣 <b>XABAR</b>\n\n{ad_text}",
                    parse_mode="HTML"
                )
                sent_count += 1
                await asyncio.sleep(0.05)
            except: continue

        await message.answer(
            f"✅ <b>{sent_count}</b> kishiga muvaffaqiyatli yuborildi.\n"
            f"❌ {len(all_users) - sent_count} kishiga yetib bormadi.",
            reply_markup=admin_keyboard(),
            parse_mode="HTML"
        )
    finally:
        if conn: conn.close()
        await state.clear()


# ============================================================
# STATISTIKA
# ============================================================

@admin_router.message(F.text == "📊 Statistika")
async def show_stats(message: Message):
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM shops")
        shops = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM debts WHERE status='unpaid'")
        d = cursor.fetchone()

        cursor.execute("SELECT COUNT(DISTINCT customer_phone) FROM debts")
        customers = cursor.fetchone()[0]

        # Kechikkan qarzlar
        cursor.execute("SELECT COUNT(*) FROM debts WHERE status='unpaid'")
        all_debts = cursor.fetchone()[0]

        text = (
            f"📈 <b>Tizim Statistikasi:</b>\n\n"
            f"🏪 Maskanlar: <b>{shops} ta</b>\n"
            f"👥 Mijozlar: <b>{customers} ta</b>\n"
            f"💰 Faol qarzlar: <b>{d[0]} ta</b>\n"
            f"💵 Jami qarz: <b>{float(d[1]):,.0f} so'm</b>"
        )
        await message.answer(text, parse_mode="HTML")
    finally:
        if conn: conn.close()


# ============================================================
# MASKAN QIDIRISH
# ============================================================

@admin_router.message(F.text == "🔍 Maskanni qidirish")
async def search_shop_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_search_query)
    await message.answer("🔍 Qidiruv so'zini kiriting:", reply_markup=cancel_keyboard())

@admin_router.message(AdminStates.waiting_for_search_query)
async def process_shop_search(message: Message, state: FSMContext):
    query = f"%{message.text}%"
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, s.name, s.phone, s.owner_id,
                   COUNT(d.id), COALESCE(SUM(d.amount),0)
            FROM shops s
            LEFT JOIN debts d ON d.shop_id=s.id AND d.status='unpaid'
            WHERE s.name ILIKE %s
            GROUP BY s.id
        """, (query,))
        shops = cursor.fetchall()

        if not shops:
            await state.clear()
            return await message.answer("❌ Topilmadi.", reply_markup=admin_keyboard())

        for s in shops:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del_shop_{s[0]}"),
                InlineKeyboardButton(text="📩 Xabar", callback_data=f"msg_shop_{s[3]}")
            ]])
            await message.answer(
                f"🏪 <b>{s[1]}</b>\n"
                f"📞 {s[2]}\n"
                f"🆔 Owner: <code>{s[3]}</code>\n"
                f"💰 {s[4]} qarz | {float(s[5]):,.0f} so'm",
                reply_markup=kb,
                parse_mode="HTML"
            )
    finally:
        if conn: conn.close()
        await state.clear()

@admin_router.callback_query(F.data.startswith("del_shop_"))
async def delete_shop_callback(callback: types.CallbackQuery):
    shop_id = int(callback.data.split("_")[2])
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT name, owner_id FROM shops WHERE id=%s", (shop_id,))
        shop = cursor.fetchone()
        if shop:
            cursor.execute("DELETE FROM shops WHERE id=%s", (shop_id,))
            conn.commit()
            await callback.message.delete()
            await callback.answer(f"✅ {shop[0]} o'chirildi!", show_alert=True)
            try:
                await callback.bot.send_message(
                    shop[1],
                    "⚠️ Sizning maskaningiz tizimdan o'chirildi."
                )
            except: pass
        else:
            await callback.answer("Topilmadi!", show_alert=True)
    finally:
        if conn: conn.close()

@admin_router.callback_query(F.data.startswith("msg_shop_"))
async def msg_shop_callback(callback: types.CallbackQuery, state: FSMContext):
    """Do'konchiga xabar yuborish"""
    owner_id = int(callback.data.split("_")[2])
    await state.update_data(msg_owner_id=owner_id)
    await callback.message.answer(
        f"📩 <code>{owner_id}</code> ga yubormoqchi bo'lgan xabarni kiriting:",
        parse_mode="HTML"
    )
    await callback.answer()
