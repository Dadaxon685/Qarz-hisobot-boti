import asyncio
import logging
from aiogram import Router, F, types
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import State, StatesGroup
from aiogram.filters import CommandStart

from handlers.connections import get_connection

# ============================================================
# ROUTER VA ADMIN ID
# ============================================================

admin_router = Router()
SUPER_ADMIN_ID = 5148276461

# Faqat super admin uchun filtr
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
# KLAVIATURALAR
# ============================================================

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


# ============================================================
# START VA BEKOR QILISH
# ============================================================

@admin_router.message(CommandStart())
async def admin_start(message: Message):
    await message.answer("Xush kelibsiz, Boss!", reply_markup=admin_keyboard())

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
    await message.answer("Maskan egasining Telegram ID raqamini yuboring:")

@admin_router.message(ShopRegistration.owner_id)
async def process_owner_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("ID faqat raqamlardan iborat bo'lishi kerak!")
    await state.update_data(owner_id=int(message.text))
    await state.set_state(ShopRegistration.phone)
    await message.answer("Maskanchi telefon raqamini kiriting:")

@admin_router.message(ShopRegistration.phone)
async def process_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(ShopRegistration.address)
    await message.answer("Maskan manzilini kiriting:")

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

        try:
            await callback.bot.send_message(
                chat_id=data['owner_id'],
                text=f"🎉 Tabriklaymiz! {data['name']} Maskani tizimga qo'shildi.\nBotdan foydalanish uchun /start bosing."
            )
        except:
            await callback.message.answer("⚠️ Maskanchiga xabar yetib bormadi (Botni bloklagan bo'lishi mumkin).")

    except Exception as e:
        logging.error(f"Baza xatosi: {e}")
        await callback.message.answer(f"❌ Xatolik: {e}")
    finally:
        if conn:
            conn.close()
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
        cursor.execute("SELECT id, name, owner_id FROM shops ORDER BY id")
        shops = cursor.fetchall()

        if not shops:
            return await message.answer("Hozircha Maskanlar yo'q.")

        text = "🏬 <b>Tizimdagi Maskanlar:</b>\n\n"
        for s in shops:
            text += f"🆔 <code>{s[0]}</code> | 🏪 {s[1]} | Admin: {s[2]}\n"

        text += "\n❌ O'chirish uchun <b>ID raqamni</b> yuboring yoki 'bekor' deb yozing:"
        await state.set_state(AdminStates.waiting_for_shop_id_to_delete)
        await message.answer(text, parse_mode="HTML")
    finally:
        if conn:
            conn.close()

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
        cursor.execute("SELECT name FROM shops WHERE id = %s", (shop_id,))
        shop = cursor.fetchone()

        if shop:
            cursor.execute("DELETE FROM shops WHERE id = %s", (shop_id,))
            conn.commit()
            await message.answer(f"✅ '<b>{shop[0]}</b>' Maskani o'chirildi.", parse_mode="HTML")
        else:
            await message.answer("⚠️ Bunday ID topilmadi.")
    finally:
        if conn:
            conn.close()
        await state.clear()


# ============================================================
# REKLAMA YUBORISH
# ============================================================

@admin_router.message(F.text == "📢 Reklama yuborish")
async def start_broadcast(message: Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_ad_text)
    await message.answer("Reklama matnini kiriting:", reply_markup=cancel_keyboard())

@admin_router.message(AdminStates.waiting_for_ad_text)
async def process_broadcast(message: Message, state: FSMContext):
    ad_text = message.text
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT owner_id FROM shops")
        owners = [row[0] for row in cursor.fetchall()]

        cursor.execute("SELECT customer_id FROM debts WHERE customer_id IS NOT NULL")
        customers = [row[0] for row in cursor.fetchall()]

        all_users = list(set(owners + customers))

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
            except:
                continue

        await message.answer(f"✅ {sent_count} kishiga yuborildi.", reply_markup=admin_keyboard())
    finally:
        if conn:
            conn.close()
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
        s_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*), SUM(amount) FROM debts WHERE status = 'unpaid'")
        d_data = cursor.fetchone()

        text = (
            f"📈 <b>Statistika:</b>\n\n"
            f"🏪 Maskanlar: <b>{s_count} ta</b>\n"
            f"💰 Qarzlar soni: <b>{d_data[0]} ta</b>\n"
            f"💵 Jami qarz: <b>{d_data[1] or 0:,.0f} so'm</b>"
        )
        await message.answer(text, parse_mode="HTML")
    finally:
        if conn:
            conn.close()


# ============================================================
# MASKAN QIDIRISH
# ============================================================

@admin_router.message(F.text == "🔍 Maskanni qidirish")
async def search_shop_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_search_query)
    await message.answer("Qidiruv so'zini kiriting:", reply_markup=cancel_keyboard())

@admin_router.message(AdminStates.waiting_for_search_query)
async def process_shop_search(message: Message, state: FSMContext):
    query = f"%{message.text}%"
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # PostgreSQL da ILIKE - katta kichik harfga sezgir emas
        cursor.execute(
            "SELECT id, name, phone, owner_id FROM shops WHERE name ILIKE %s",
            (query,)
        )
        shops = cursor.fetchall()

        if not shops:
            return await message.answer("Topilmadi.", reply_markup=admin_keyboard())

        for s in shops:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"del_shop_{s[0]}")
            ]])
            await message.answer(
                f"🏪 <b>{s[1]}</b>\n📞 {s[2]}\n🆔 Owner ID: <code>{s[3]}</code>",
                reply_markup=kb,
                parse_mode="HTML"
            )
    finally:
        if conn:
            conn.close()
        await state.clear()

@admin_router.callback_query(F.data.startswith("del_shop_"))
async def delete_shop_callback(callback: types.CallbackQuery):
    shop_id = int(callback.data.split("_")[2])
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM shops WHERE id = %s", (shop_id,))
        conn.commit()
        await callback.message.delete()
        await callback.answer("O'chirildi!", show_alert=True)
    finally:
        if conn:
            conn.close()