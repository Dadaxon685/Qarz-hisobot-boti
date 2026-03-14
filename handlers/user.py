import sqlite3
from aiogram import Router, F, types
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, 
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

# Tugmalarni import qilish (faylingiz nomiga qarab o'zgartiring)
try:
    from buttons import admin_keyboard, shop_keyboard
except ImportError:
    # Test uchun vaqtincha funksiyalar (sizda buttons.py bo'lsa buni o'chiring)
    def shop_keyboard(): return ReplyKeyboardRemove()

user_router = Router()
SUPER_ADMIN_ID = 5148276461  # O'zingizning ID-ingiz

class ShopApply(StatesGroup):
    name = State()
    address = State()
    phone = State()

# --- KLAVIATURALAR (Dizaynli) ---

def get_cancel_kb():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="❌ Bekor qilish"))
    return builder.as_markup(resize_keyboard=True)

def get_phone_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True))
    builder.row(KeyboardButton(text="❌ Bekor qilish"))
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)

def user_start_inline():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔍 Qarzlarimni tekshirish", callback_data="check_debts"))
    builder.row(InlineKeyboardButton(text="🚀 O'z do'konimni ochish", callback_data="open_shop"))
    return builder.as_markup()

# --- START BUYRUQI ---
@user_router.message(CommandStart())
async def start_bot(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()

    # 1. DO'KONCHI EKANLIGINI TEKSHIRISH
    cursor.execute("SELECT name FROM shops WHERE owner_id = ?", (uid,))
    shop = cursor.fetchone()

    if shop:
        conn.close()
        return await message.answer(
            f"🏪 <b>{shop[0]}</b> do'koni paneli\n\n<i>Xizmat ko'rsatishga tayyor!</i>", 
            reply_markup=shop_keyboard(), 
            parse_mode="HTML"
        )

    # 2. MIJOZ QARZLARINI TEKSHIRISH
    cursor.execute("""
        SELECT d.amount, d.due_date, s.name 
        FROM debts d 
        JOIN shops s ON d.shop_id = s.id 
        WHERE d.customer_id = ? AND d.status = 'unpaid'
    """, (uid,))
    debts = cursor.fetchall()
    conn.close()

    if debts:
        text = (
            f"👋 <b>Assalomu alaykum, {message.from_user.full_name}!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 <b>SIZNING QARZLARINGIZ:</b>\n\n"
        )
        total_sum = 0
        for amount, due_date, shop_name in debts:
            text += (
                f"🏛 <b>Do'kon:</b> <code>{shop_name}</code>\n"
                f"💰 <b>Summa:</b> {amount:,} so'm\n"
                f"📅 <b>Muddat:</b> {due_date}\n"
                f"────────────────────\n"
            )
            total_sum += amount
        text += f"\n🏦 <b>UMUMIY QARZINGIZ:</b> <u>{total_sum:,} so'm</u>"
        
        await message.answer(text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
        await message.answer("💡 <b>Boshqa amallar:</b>", reply_markup=user_start_inline(), parse_mode="HTML")
    
    else:
        text = (
            f"👋 <b>Xush kelibsiz, {message.from_user.full_name}!</b>\n\n"
            "Siz tizimda hali ro'yxatdan o'tmagansiz.\n"
            "Nima qilmoqchisiz? 👇"
        )
        await message.answer(text, reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
        await message.answer("👇 <b>Tanlang:</b>", reply_markup=user_start_inline(), parse_mode="HTML")

# --- BEKOR QILISH HANDLERI ---
@user_router.message(F.text == "❌ Bekor qilish")
async def cancel_process(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🚫 <b>Jarayon bekor qilindi.</b>", reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
    await message.answer("Bosh menyu:", reply_markup=user_start_inline())

# --- DO'KON OCHISH ARIZASI (FSM) ---

@user_router.callback_query(F.data == "open_shop")
async def apply_shop_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ShopApply.name)
    await callback.message.answer(
        "🏪 <b>Do'kon ochish uchun ariza berish</b>\n\n1️⃣ Do'koningiz nomini kiriting:", 
        reply_markup=get_cancel_kb(),
        parse_mode="HTML"
    )
    await callback.answer()

@user_router.message(ShopApply.name)
async def apply_name(message: Message, state: FSMContext):
    await state.update_data(shop_name=message.text)
    await state.set_state(ShopApply.address)
    await message.answer("2️⃣ Do'kon manzilini kiriting (shahar, ko'cha...):", reply_markup=get_cancel_kb())

@user_router.message(ShopApply.address)
async def apply_address(message: Message, state: FSMContext):
    await state.update_data(shop_address=message.text)
    await state.set_state(ShopApply.phone)
    await message.answer(
        "3️⃣ <b>Oxirgi qadam!</b>\nTelefon raqamingizni yuboring:", 
        reply_markup=get_phone_keyboard(),
        parse_mode="HTML"
    )

@user_router.message(ShopApply.phone, F.contact)
async def apply_phone(message: Message, state: FSMContext):
    data = await state.get_data()
    uid = message.from_user.id
    phone = message.contact.phone_number
    if not phone.startswith('+'): phone = '+' + phone
    
    # Admin tugmalari
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"approve_{uid}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_{uid}")]
    ])
    
    admin_text = (
        f"🚀 <b>YANGI DO'KON ARIZASI!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Foydalanuvchi:</b> {message.from_user.full_name}\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"🏪 <b>Do'kon:</b> <b>{data['shop_name']}</b>\n"
        f"📍 <b>Manzil:</b> {data['shop_address']}\n"
        f"📞 <b>Tel:</b> {phone}\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    
    await message.bot.send_message(chat_id=SUPER_ADMIN_ID, text=admin_text, reply_markup=kb, parse_mode="HTML")
    await message.answer(
        "✅ <b>Arizangiz adminga yuborildi!</b>\n\nTez orada ko'rib chiqib javob beramiz.", 
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )
    await state.clear()

# --- ADMIN TASDIQLASHI ---

@user_router.callback_query(F.data.startswith("approve_"))
async def approve_shop(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    lines = callback.message.text.split('\n')
    
    shop_data = {}
    for line in lines:
        if "Do'kon:" in line: shop_data['name'] = line.split(": ")[1]
        if "Manzil:" in line: shop_data['address'] = line.split(": ")[1]
        if "Tel:" in line: shop_data['phone'] = line.split(": ")[1]

    try:
        conn = sqlite3.connect('qarz_tizimii.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO shops (name, owner_id, phone, address) VALUES (?, ?, ?, ?)",
            (shop_data.get('name'), user_id, shop_data.get('phone'), shop_data.get('address'))
        )
        conn.commit()
        conn.close()
        
        await callback.bot.send_message(
            user_id, 
            "🎉 <b>Xushxabar!</b>\n\nSizning do'koningiz tasdiqlandi. /start bosing va panelga kiring!", 
            parse_mode="HTML"
        )
        await callback.message.edit_text(callback.message.text + "\n\n✅ <b>TASDIQLANDI</b>")
    except Exception as e:
        await callback.answer(f"Xato: {e}", show_alert=True)

@user_router.callback_query(F.data.startswith("reject_"))
async def reject_shop(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    await callback.bot.send_message(user_id, "❌ Uzr, sizning do'kon ochish haqidagi arizangiz rad etildi.")
    await callback.message.edit_text(callback.message.text + "\n\n❌ <b>RAD ETILDI</b>")
    await callback.answer()

# --- QARZNI TEKSHIRISH ---

@user_router.callback_query(F.data == "check_debts")
async def check_debts_callback(callback: types.CallbackQuery):
    await callback.message.answer(
        "📊 <b>Qarzlarni ko'rish uchun</b> pastdagi tugma orqali telefon raqamingizni yuboring:",
        reply_markup=get_phone_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@user_router.message(F.contact)
async def handle_contact(message: Message):
    phone = message.contact.phone_number
    if not phone.startswith('+'): phone = '+' + phone
    uid = message.from_user.id
    
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE shops SET owner_id = ? WHERE phone = ? AND owner_id IS NULL", (uid, phone))
    cursor.execute("UPDATE debts SET customer_id = ? WHERE customer_phone = ?", (uid, phone))
    conn.commit()

    cursor.execute("SELECT name FROM shops WHERE owner_id = ?", (uid,))
    shop = cursor.fetchone()

    if shop:
        conn.close()
        return await message.answer(
            f"✅ <b>{shop[0]}</b> do'koni paneli faollashdi!", 
            reply_markup=shop_keyboard(), 
            parse_mode="HTML"
        )

    cursor.execute("""
        SELECT d.amount, d.due_date, s.name 
        FROM debts d 
        JOIN shops s ON d.shop_id = s.id 
        WHERE d.customer_id = ? AND d.status = 'unpaid'
    """, (uid,))
    debts = cursor.fetchall()
    conn.close()

    if debts:
        text = "📋 <b>Sizning faol qarzlaringiz:</b>\n\n"
        total = 0
        for amount, date, sname in debts:
            text += f"🏪 <b>Do'kon:</b> {sname}\n💰 <b>Summa:</b> {amount:,} so'm\n📅 <b>Muddat:</b> {date}\n"
            text += "────────────────────\n"
            total += amount
        text += f"\n💵 <b>JAMI QARZ:</b> <u>{total:,} so'm</u>"
        await message.answer(text, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    else:
        await message.answer("✅ Faol qarzlar topilmadi.", reply_markup=ReplyKeyboardRemove())