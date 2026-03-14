import logging
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters.state import State, StatesGroup
from models import init_db
from apscheduler.schedulers.asyncio import AsyncIOScheduler
# --- SOZLAMALAR ---
API_TOKEN = '8340168068:AAE126I8LCTcEcGfrAh9pqJ2c7cB4Ih7fJs'
SUPER_ADMIN_ID = 5148276461  

# Logging
logging.basicConfig(level=logging.INFO)

# Bot va Dispatcher
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- MA'LUMOTLAR BAZASI ---


# --- FSM (Holatlar) ---
class ShopRegistration(StatesGroup):
    name = State()
    owner_id = State()
    phone = State()
    address = State()
    confirm = State()

class BroadcastState(StatesGroup):
    message = State()

# --- SUPER ADMIN KLAVIATURASI ---
def admin_keyboard():
    buttons = [
        [KeyboardButton(text="🏪 Do'kon qo'shish"), KeyboardButton(text="🔍 Do'konni qidirish")],
        [KeyboardButton(text="📝 Do'konlar ro'yxati"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="📢 Reklama yuborish")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- BOT BUYRUQLARI ---


# Asosiy menyu tugmalari ro'yxati
MENU_BUTTONS = ["🏪 Do'kon qo'shish", "🔍 Do'konni qidirish", "📝 Do'konlar ro'yxati", "📊 Statistika", "📢 Reklama yuborish"]

# Jarayonni tekshirish uchun funksiya
async def is_menu_button(message: Message):
    return message.text in MENU_BUTTONS
# --- KERAKLI KLAVIATURA ---
def get_phone_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]
    ], resize_keyboard=True, one_time_keyboard=True)

# --- START KOMANDASI ---
@dp.message(CommandStart())
async def start_bot(message: Message):
    uid = message.from_user.id
    
    # 1. Super Admin tekshiruvi
    if uid == SUPER_ADMIN_ID:
        return await message.answer("Xush kelibsiz, Boss!", reply_markup=admin_keyboard())

    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()

    # 2. Do'konchi tekshiruvi
    cursor.execute("SELECT name FROM shops WHERE owner_id = ?", (uid,))
    shop = cursor.fetchone()
    
    if shop:
        conn.close()
        return await message.answer(f"🏪 {shop[0]} do'koni paneli", reply_markup=shop_keyboard())

    # 3. Xaridor/Qarzdor ekanligini tekshirish (customer_id orqali)
    cursor.execute("""
        SELECT d.amount, d.due_date, s.name 
        FROM debts d 
        JOIN shops s ON d.shop_id = s.id 
        WHERE d.customer_id = ? AND d.status = 'unpaid'
    """, (uid,))
    debts = cursor.fetchall()
    conn.close()

    if debts:
            # Sarlavha va tabrik
            text = f"👋 <b>Assalomu alaykum, {message.from_user.full_name}!</b>\n"
            text += "────────────────────\n"
            text += "📊 <b>SIZNING QARZLARINGIZ HISOBOTI:</b>\n\n"
            
            total_sum = 0
            for amount, due_date, shop_name in debts:
                # Har bir qarz uchun alohida blok
                text += f"🏛 <b>Do'kon:</b> <code>{shop_name}</code>\n"
                text += f"💰 <b>Qarz miqdori:</b> {amount:,} so'm\n"
                text += f"📅 <b>To'lov muddati:</b> {due_date}\n"
                text += "────────────────────\n"
                total_sum += amount
            
            # Yakuniy natija
            text += f"\n🏦 <b>UMUMIY QARZINGIZ:</b> <u>{total_sum:,} so'm</u>\n\n"
            text += "🔔 <i>Bot sizga to'lov muddatlari haqida avtomatik eslatib turadi. Iltimos, to'lovlarni o'z vaqtida amalga oshiring.</i>"
            
            await message.answer(text, parse_mode="HTML", reply_markup=types.ReplyKeyboardRemove())
    else:
        # Tanilmagan mijoz uchun chiroyli taklif
        text = (
            f"👋 <b>Xush kelibsiz, {message.from_user.full_name}!</b>\n\n"
            "Sizning qarzlar hisobingizni shakllantirishimiz uchun tizimga telefon raqamingiz kerak.\n\n"
            "👇 <b>Tasdiqlash</b> tugmasini bossangiz, barcha do'konlardagi qarzlaringizni shu yerda ko'rasiz:"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=get_phone_keyboard())

# --- KONTAKTNI QABUL QILISH VA BAZANI YANGILASH ---
@dp.message(F.contact)
async def handle_contact(message: Message):
    phone = message.contact.phone_number
    # Raqamni formatlash (ba'zan + bo'lmaydi)
    if not phone.startswith('+'):
        phone = '+' + phone
    
    uid = message.from_user.id
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()

    # 1. Shu raqamga yozilgan barcha qarzlarga mijozning TG ID sini bog'laymiz
    cursor.execute("UPDATE debts SET customer_id = ? WHERE customer_phone = ?", (uid, phone))
    conn.commit()

    # 2. Endi yangilangan ma'lumotlarni chiqaramiz
    cursor.execute("""
        SELECT d.amount, d.due_date, s.name 
        FROM debts d 
        JOIN shops s ON d.shop_id = s.id 
        WHERE d.customer_id = ? AND d.status = 'unpaid'
    """, (uid,))
    debts = cursor.fetchall()
    conn.close()

    if debts:
            # Sarlavha qismi
            text = "🔓 <b>Raqamingiz tasdiqlandi!</b>\n"
            text += "────────────────────\n"
            text += "📋 <b>Sizning faol qarzlaringiz:</b>\n\n"
            
            total = 0
            for amount, date, sname in debts:
                # Har bir do'kon uchun alohida blok
                text += f"🏪 <b>Do'kon:</b> {sname}\n"
                text += f"💰 <b>Summa:</b> {amount:,} so'm\n"
                text += f"📅 <b>Muddat:</b> <code>{date}</code>\n"
                text += "────────────────────\n"
                total += amount
            
            # Yakuniy hisob
            text += f"\n💵 <b>JAMI QARZ:</b> <u>{total:,} so'm</u>"
            
            await message.answer(text, parse_mode="HTML", reply_markup=types.ReplyKeyboardRemove())
    else:
        # Qarz mavjud bo'lmagandagi xabar
        text = (
            "✅ <b>Raqamingiz muvaffaqiyatli tasdiqlandi!</b>\n\n"
            "🎉 Tabriklaymiz, sizning hisobingizda hech qanday faol qarzlar topilmadi.\n\n"
            "<i>Eslatma: Yangi qarz yozilganda bot sizga darhol xabar yuboradi.</i>"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=types.ReplyKeyboardRemove())
# 1. DO'KON QO'SHISH BOSQICHLARI
# Aiogram 3 da F.text va F.from_user.id ishlatiladi
def cancel_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚫 Bekor qilish")]
    ], resize_keyboard=True)

# Qarz yozish yoki Do'kon qo'shish boshlanganda shu klaviaturani yuboramiz
@dp.message(F.text == "🏪 Do'kon qo'shish")
async def start_shop_reg(message: Message, state: FSMContext):
    await state.set_state(ShopRegistration.name)
    await message.answer("🏪 Do'kon nomini kiriting:", reply_markup=cancel_keyboard())

# Bekor qilish tugmasi uchun handler
@dp.message(F.text == "🚫 Bekor qilish")
async def cancel_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    
    await state.clear()
    await message.answer("📥 Jarayon bekor qilindi.", reply_markup=admin_keyboard())

@dp.message(ShopRegistration.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(ShopRegistration.owner_id)
    await message.answer("Do'kon egasining Telegram ID raqamini yuboring:")

@dp.message(ShopRegistration.owner_id)
async def process_owner_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("ID faqat raqamlardan iborat bo'lishi kerak!")
    await state.update_data(owner_id=int(message.text))
    await state.set_state(ShopRegistration.phone)
    await message.answer("Do'konchi telefon raqamini kiriting:")

@dp.message(ShopRegistration.phone)
async def process_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(ShopRegistration.address)
    await message.answer("Do'kon manzilini kiriting:")

# 1. Manzil kiritilgandan keyin darrov bazaga yozmaymiz, tekshirishga chiqaramiz
@dp.message(ShopRegistration.address)
async def shop_address(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    data = await state.get_data()
    
    # Tasdiqlash tugmalari
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_shop_yes"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="confirm_shop_no")
        ]
    ])
    
    confirm_text = (
        f"📝 <b>Yangi do'kon ma'lumotlari:</b>\n\n"
        f"🏪 Nomi: <b>{data['name']}</b>\n"
        f"🆔 Egasi (ID): <code>{data['owner_id']}</code>\n"
        f"📞 Tel: <b>{data['phone']}</b>\n"
        f"📍 Manzil: <b>{message.text}</b>\n\n"
        f"Ma'lumotlar to'g'rimi?"
    )
    
    await state.set_state(ShopRegistration.confirm)
    await message.answer(confirm_text, reply_markup=kb, parse_mode="HTML")

# 2. Tugma bosilganda ishlovchi handler
@dp.callback_query(ShopRegistration.confirm, F.data.startswith("confirm_shop_"))
async def shop_confirm_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "confirm_shop_no":
        await state.clear()
        await callback.message.edit_text("❌ Do'kon qo'shish bekor qilindi.")
        return await callback.answer()

    # Agar "Tasdiqlash" bo'lsa, bazaga yozamiz
    data = await state.get_data()
    
    try:
        conn = sqlite3.connect('qarz_tizimii.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO shops (name, owner_id, phone, address) VALUES (?, ?, ?, ?)",
            (data['name'], data['owner_id'], data['phone'], data['address'])
        )
        conn.commit()
        conn.close()
        
        await callback.message.edit_text(f"✅ <b>{data['name']}</b> do'koni muvaffaqiyatli qo'shildi!")
        
        # Do'kon egasiga tabrik xabari yuborish
        try:
            await bot.send_message(data['owner_id'], "🎉 Tabriklaymiz! Sizning do'koningiz tizimga qo'shildi. /start tugmasini bosing.")
        except:
            pass
            
    except Exception as e:
        await callback.message.edit_text(f"❌ Xatolik yuz berdi: {e}")
    
    await state.clear()
    await callback.answer()

# 2. DO'KONLAR RO'YXATI
@dp.message(F.text == "📝 Do'konlar ro'yxati", F.from_user.id == SUPER_ADMIN_ID)
async def list_shops(message: Message):
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, owner_id, phone FROM shops")
    shops = cursor.fetchall()
    conn.close()

    if not shops:
        return await message.answer("Hozircha do'konlar yo'q.")
    
    text = "🏬 <b>Do'konlar ro'yxati:</b>\n\n"
    for s in shops:
        text += f"📍 {s[0]} | Admin ID: <code>{s[1]}</code> | Tel: {s[2]}\n"
    
    await message.answer(text, parse_mode="HTML")


# --- SUPERADMIN HOLATLARI ---
class AdminStatess(StatesGroup):
    waiting_for_ad_text = State()           # Reklama matnini kutish
    waiting_for_search_query = State()      # Qidiruv so'zini kutish
    waiting_for_shop_id_to_delete = State() # O'chiriladigan IDni kutish

# --- REKLAMA YUBORISH (HAMMAGA) ---
# --- REKLAMA BOSHLASH ---
@dp.message(F.text == "📢 Reklama yuborish", F.from_user.id == SUPER_ADMIN_ID)
async def start_broadcast(message: Message, state: FSMContext):
    await state.set_state(AdminStatess.waiting_for_ad_text) # Endi xato bermaydi
    await message.answer("Barcha foydalanuvchilarga yuboriladigan reklama matnini kiriting:")

# --- REKLAMANI YUBORISH ---
@dp.message(AdminStatess.waiting_for_ad_text)
async def process_broadcast(message: Message, state: FSMContext):
    ad_text = message.text
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Barcha foydalanuvchilarni yig'ish (Do'konchilar + Qarzdorlar)
    cursor.execute("SELECT owner_id FROM shops")
    owners = [row[0] for row in cursor.fetchall()]
    cursor.execute("SELECT customer_id FROM debts")
    customers = [row[0] for row in cursor.fetchall()]
    
    all_users = list(set(owners + customers)) # Takrorlanmas IDlar
    conn.close()

    sent_count = 0
    for user_id in all_users:
        try:
            await bot.send_message(user_id, f"📣 <b>ADMIN XABARI</b>\n\n{ad_text}", parse_mode="HTML")
            sent_count += 1
            await asyncio.sleep(0.05) # Spamga tushmaslik uchun
        except:
            continue
    
    await message.answer(f"✅ Reklama {sent_count} ta foydalanuvchiga muvaffaqiyatli yuborildi.")
    await state.clear()

# --- DO'KONLAR RO'YXATI VA O'CHIRISH ---
@dp.message(F.text == "📝 Do'konlar ro'yxati", F.from_user.id == SUPER_ADMIN_ID)
async def list_shops_admin(message: Message, state: FSMContext):
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, owner_id FROM shops")
    shops = cursor.fetchall()
    conn.close()

    if not shops:
        return await message.answer("Hozircha do'konlar yo'q.")

    text = "🏬 <b>Tizimdagi do'konlar:</b>\n\n"
    for s in shops:
        text += f"🆔 <code>{s[0]}</code> | 🏪 {s[1]} | ID: {s[2]}\n"
    
    text += "\n❌ Do'konni o'chirish uchun uning <b>ID raqamini</b> yuboring (yoki 'bekor' deb yozing):"
    await state.set_state(AdminStates.waiting_for_shop_id_to_delete)
    await message.answer(text, parse_mode="HTML")

@dp.message(AdminStatess.waiting_for_shop_id_to_delete)
async def process_shop_delete(message: Message, state: FSMContext):
    if message.text.lower() == 'bekor':
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=admin_keyboard())

    if not message.text.isdigit():
        return await message.answer("Iltimos, faqat raqam (ID) yuboring!")

    shop_id = int(message.text)
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Do'konni o'chirishdan oldin borligini tekshiramiz
    cursor.execute("SELECT name FROM shops WHERE id = ?", (shop_id,))
    shop = cursor.fetchone()
    
    if shop:
        cursor.execute("DELETE FROM shops WHERE id = ?", (shop_id,))
        # Do'konga tegishli qarzlarni ham o'chirib tashlash (ixtiyoriy)
        cursor.execute("DELETE FROM debts WHERE shop_id = ?", (shop_id,))
        conn.commit()
        await message.answer(f"✅ '{shop[0]}' do'koni va uning barcha ma'lumotlari o'chirildi.")
    else:
        await message.answer("⚠️ Bunday ID dagi do'kon topilmadi.")
    
    conn.close()
    await state.clear()

# --- STATISTIKA ---
@dp.message(F.text == "📊 Statistika", F.from_user.id == SUPER_ADMIN_ID)
async def show_stats(message: Message):
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM shops")
    shops_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*), SUM(amount) FROM debts WHERE status = 'unpaid'")
    debts_data = cursor.fetchone()
    
    cursor.execute("SELECT COUNT(DISTINCT customer_id) FROM debts")
    users_count = cursor.fetchone()[0]
    
    conn.close()

    text = (f"📈 <b>Tizim statistikasi:</b>\n\n"
            f"🏪 Jami do'konlar: <b>{shops_count} ta</b>\n"
            f"👥 Jami mijozlar: <b>{users_count} ta</b>\n"
            f"💰 To'lanmagan qarzlar soni: <b>{debts_data[0]} ta</b>\n"
            f"💵 Jami qarz miqdori: <b>{debts_data[1] or 0:,} so'm</b>")
    
    await message.answer(text, parse_mode="HTML")

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- HOLAT ---
class AdminStates(StatesGroup):
    waiting_for_search_query = State()

# --- QIDIRUVNI BOSHLASH ---
@dp.message(F.text == "🔍 Do'konni qidirish", F.from_user.id == SUPER_ADMIN_ID)
async def search_shop_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_search_query)
    await message.answer("Qidirilayotgan do'kon nomini yoki qismini kiriting:")

# --- QIDIRUV NATIJASI ---
@dp.message(AdminStates.waiting_for_search_query)
async def process_shop_search(message: Message, state: FSMContext):
    query = message.text.strip() # Bo'shliqlarni olib tashlaymiz
    
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Qidiruv mantiqi: %query% - bu har qanday joyidan qidirish degani
    cursor.execute("SELECT id, name, owner_id, phone FROM shops WHERE name LIKE ?", (f'%{query}%',))
    shops = cursor.fetchall()
    conn.close()

    if not shops:
        await message.answer(f"🔍 '{query}' so'zi qatnashgan hech qanday do'kon topilmadi.")
        await state.clear()
        return

    await message.answer(f"🔎 <b>'{query}'</b> bo'yicha natijalar:")

    for shop in shops:
        # Har bir do'kon uchun o'chirish tugmasi
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Do'konni o'chirish", callback_data=f"del_shop_{shop[0]}")]
        ])
        
        await message.answer(
            f"🏪 <b>Do'kon:</b> {shop[1]}\n"
            f"📞 Tel: {shop[3]}\n"
            f"🆔 ID: <code>{shop[2]}</code>",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    
    await state.clear()
# --- O'CHIRISH TUGMASI UCHUN HANDLER ---
@dp.callback_query(F.data.startswith("del_shop_"))
async def delete_shop_callback(callback: types.CallbackQuery):
    shop_id = int(callback.data.split("_")[2])
    
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Avval do'kon nomini olamiz (xabar uchun)
    cursor.execute("SELECT name FROM shops WHERE id = ?", (shop_id,))
    shop = cursor.fetchone()
    
    if shop:
        # Do'konni va unga tegishli qarzlarni o'chiramiz
        cursor.execute("DELETE FROM shops WHERE id = ?", (shop_id,))
        cursor.execute("DELETE FROM debts WHERE shop_id = ?", (shop_id,))
        conn.commit()
        
        await callback.answer(f"'{shop[0]}' o'chirildi!", show_alert=True)
        # Xabarni o'zgartiramiz
        await callback.message.edit_text(f"❌ <b>{shop[0]}</b> do'koni tizimdan butunlay o'chirildi.", parse_mode="HTML")
    else:
        await callback.answer("Do'kon topilmadi yoki allaqachon o'chirilgan.")
    
    conn.close()
####################################################################################################################
# DO"KO"NCHI QISMI
from datetime import datetime
from aiogram import F

# --- DO'KONCHI HOLATLARI ---
class DebtAdd(StatesGroup):
    customer_phone = State()
    found_existing = State()
    customer_name = State()
    amount = State()
    due_date = State()
    confirm = State()


class PaymentStates(StatesGroup):
    waiting_for_phone_last4 = State()   # 4 ta raqam kutish
    waiting_for_select_debt = State()   # Qaysi qarzligini tanlash
    waiting_for_partial_amount = State() # Qisman to'lov summasini kutish

class ShopSearchStates(StatesGroup):
    waiting_for_query = State()  # Ism yoki tel kutish

class ShopBroadcast(StatesGroup):
    waiting_for_message = State()
# --- DO'KONCHI KLAVIATURASI ---
def shop_keyboard():
    buttons = [
        [KeyboardButton(text="➕ Qarz yozish"), KeyboardButton(text="📊 Qarzlar ro'yxati")],
        [KeyboardButton(text="🔍 Qidirish"), KeyboardButton(text="💰 To'lovni qabul qilish")],
        [KeyboardButton(text="📢 E'lon yuborish"), KeyboardButton(text="📊 Excel hisobot")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- START KOMANDASINI YANGILASH ---
@dp.message(CommandStart())
async def start_bot(message: Message):
    uid = message.from_user.id
    
    # Super Admin tekshiruvi
    if uid == SUPER_ADMIN_ID:
        return await message.answer("Boss, xush kelibsiz!", reply_markup=admin_keyboard())

    # Do'konchi tekshiruvi
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM shops WHERE owner_id = ?", (uid,))
    shop = cursor.fetchone()
    conn.close()

    if shop:
        await message.answer(f"🏪 {shop[0]} do'koni boshqaruv panelingiz xush kelibsiz!", reply_markup=shop_keyboard())
    else:
        await message.answer("Siz tizimda ro'yxatdan o'tmagansiz. ID-ingiz: " + str(uid))


# --- AVTOMATIK XABAR YUBORISH FUNKSIYASI ---
# --- AVTOMATIK ESLATMA FUNKSIYASI ---
async def auto_reminder():
    conn = sqlite3.connect('qarz_tizimii.db') # Fayl nomini bazangizga moslang (odatda qarz_tizimii.db)
    cursor = conn.cursor()
    
    # To'lanmagan qarzlarni olamiz (faqat customer_id si borlarga yuboradi)
    cursor.execute("""
        SELECT d.customer_id, d.customer_name, d.amount, d.due_date, s.name 
        FROM debts d 
        JOIN shops s ON d.shop_id = s.id 
        WHERE d.status = 'unpaid' AND d.customer_id IS NOT NULL
    """)
    records = cursor.fetchall()
    conn.close()

    for cid, name, amount, date, sname in records:
        try:
            text = (f"🔔 <b>ESLATMA</b>\n\n"
                    f"Hurmatli {name}, <b>{sname}</b> do'konidan "
                    f"<b>{amount:,} so'm</b> qarzingiz bor.\n"
                    f"📅 To'lov muddati: <b>{date}</b>\n\n"
                    f"Iltimos, qarzni qaytarishni unutmang! 🙏")
            
            await bot.send_message(cid, text, parse_mode="HTML")
            await asyncio.sleep(0.05) # Telegram limitiga tushmaslik uchun
        except Exception:
            logging.info(f"Mijoz {cid} botni bloklagan yoki hali start bosmagan.")

# --- BOTNI ISHGA TUSHIRISH ---

# --- QARZ YOZISH MANTIQI ---
# --- QARZ YOZISH (DO'KONCHI UCHUN) ---
@dp.message(F.text == "➕ Qarz yozish")
async def debt_start(message: Message, state: FSMContext):
    await state.set_state(DebtAdd.customer_phone)
    await message.answer("Qarzdorning telefon raqamini kiriting (masalan: +998901234567):")

@dp.message(DebtAdd.customer_phone)
async def debt_phone_check(message: Message, state: FSMContext):
    phone = message.text.strip()
    if not phone.startswith('+'): phone = '+' + phone
    
    await state.update_data(customer_phone=phone)
    
    uid = message.from_user.id
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Do'kon ID sini olamiz
    cursor.execute("SELECT id FROM shops WHERE owner_id = ?", (uid,))
    shop_id = cursor.fetchone()[0]

    # Shu do'konda shu raqamli faol qarzni qidiramiz
    cursor.execute("""
        SELECT customer_name, amount, due_date FROM debts 
        WHERE shop_id = ? AND customer_phone = ? AND status = 'unpaid'
    """, (shop_id, phone))
    existing = cursor.fetchone()
    conn.close()

    if existing:
        name, amount, date = existing
        await state.update_data(customer_name=name) # Ismni avtomatik saqlaymiz
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Ustiga qo'shish", callback_data="existing_add")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="existing_cancel")]
        ])
        
        text = (f"⚠️ <b>Bu mijozda qarz mavjud!</b>\n\n"
                f"👤 Ismi: <b>{name}</b>\n"
                f"💰 Hozirgi qarzi: <b>{amount:,} so'm</b>\n"
                f"📅 Oxirgi muddat: <b>{date}</b>\n\n"
                f"Yangi summani hozirgi qarzga qo'shishni xohlaysizmi?")
        
        await state.set_state(DebtAdd.found_existing)
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
    else:
        # Qarz topilmasa, odatdagidek ismini so'raymiz
        await state.set_state(DebtAdd.customer_name)
        await message.answer("👤 Mijoz ismini kiriting:")

# Inline tugma bosilganda
@dp.callback_query(DebtAdd.found_existing, F.data.startswith("existing_"))
async def process_existing_choice(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "existing_cancel":
        await state.clear()
        await callback.message.edit_text("❌ Jarayon bekor qilindi.")
        return await callback.answer()
    
    # Agar "Ustiga qo'shish" bo'lsa, to'g'ridan-to'g'ri summani so'rashga o'tamiz
    await state.set_state(DebtAdd.amount)
    await callback.message.edit_text("💰 Qo'shiladigan summa miqdorini kiriting:")
    await callback.answer()

@dp.message(DebtAdd.customer_name)
async def debt_name(message: Message, state: FSMContext):
    await state.update_data(customer_name=message.text)
    await state.set_state(DebtAdd.amount)
    await message.answer("Qarz miqdori:")

@dp.message(DebtAdd.amount)
async def debt_amount(message: Message, state: FSMContext):
    await state.update_data(amount=float(message.text))
    await state.set_state(DebtAdd.due_date)
    await message.answer("To'lov muddati (kun.oy.yil):")

# 1. Muddat kiritilgandan keyin tasdiqlashni so'raymiz

# --- 2. AGAR QARZ TOPILSA, TUGMA BOSILISHI ---
@dp.callback_query(DebtAdd.found_existing, F.data == "existing_add")
async def process_existing_add(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(DebtAdd.amount)
    await callback.message.edit_text("💰 Qo'shiladigan summa miqdorini kiriting:")
    await callback.answer()

# --- 3. SUMMA VA MUDDAT KIRITISH (ODATIY) ---
@dp.message(DebtAdd.amount)
async def debt_amount(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Iltimos, faqat raqam kiriting!")
    await state.update_data(amount=float(message.text))
    await state.set_state(DebtAdd.due_date)
    await message.answer("📅 To'lov muddati (masalan: 25.12.2024):")

# --- 4. YAKUNIY TASDIQLASH BOSQICHI ---
@dp.message(DebtAdd.due_date)
async def debt_due_date_confirm(message: Message, state: FSMContext):
    await state.update_data(due_date=message.text)
    data = await state.get_data()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Ha, saqlash", callback_data="confirm_debt_yes"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="confirm_debt_no")
        ]
    ])
    
    confirmation_text = (
        f"📋 <b>Ma'lumotlarni tekshiring:</b>\n\n"
        f"👤 Mijoz: <b>{data['customer_name']}</b>\n"
        f"📞 Tel: <b>{data['customer_phone']}</b>\n"
        f"💰 Yangi summa: <b>{data['amount']:,} so'm</b>\n"
        f"📅 Muddat: <b>{message.text}</b>\n\n"
        f"Ma'lumotlar to'g'rimi?"
    )
    
    await state.set_state(DebtAdd.confirm)
    await message.answer(confirmation_text, reply_markup=kb, parse_mode="HTML")

# --- 5. BAZAGA YOZISH ---
@dp.callback_query(DebtAdd.confirm, F.data.startswith("confirm_debt_"))
async def debt_confirm_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "confirm_debt_no":
        await state.clear()
        await callback.message.edit_text("❌ Jarayon bekor qilindi.")
        return await callback.answer()

    data = await state.get_data()
    uid = callback.from_user.id
    phone = data['customer_phone']
    new_amount = data['amount']
    due_date = data['due_date']

    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name FROM shops WHERE owner_id = ?", (uid,))
    shop_id, shop_name = cursor.fetchone()

    # Bazada qarz bor-yo'qligini yana bir bor tekshiramiz
    cursor.execute("SELECT id, amount FROM debts WHERE shop_id = ? AND customer_phone = ? AND status = 'unpaid'", (shop_id, phone))
    existing = cursor.fetchone()

    # Mijozning TG ID sini qidirish
    cursor.execute("SELECT customer_id FROM debts WHERE customer_phone = ? AND customer_id IS NOT NULL LIMIT 1", (phone,))
    c_res = cursor.fetchone()
    c_id = c_res[0] if c_res else None

    if existing:
        total = existing[1] + new_amount
        cursor.execute("UPDATE debts SET amount = ?, due_date = ?, debt_date = DATE('now'), customer_id = ? WHERE id = ?", 
                       (total, due_date, c_id, existing[0]))
        res_text = f"✅ Qarz yangilandi. Umumiy summa: <b>{total:,} so'm</b>"
    else:
        cursor.execute("INSERT INTO debts (shop_id, customer_id, customer_phone, customer_name, amount, due_date, status, debt_date) VALUES (?,?,?,?,?,?,?, DATE('now'))",
                       (shop_id, c_id, phone, data['customer_name'], new_amount, due_date, 'unpaid'))
        res_text = "✅ Yangi qarz muvaffaqiyatli saqlandi."

    conn.commit()
    conn.close()

    # Mijozga bildirishnoma
    if c_id:
        try:
            await bot.send_message(c_id, f"💰 <b>Qarz hisobingiz yangilandi!</b>\n🏪 {shop_name}\n➕ Qo'shildi: {new_amount:,} so'm\n📅 Muddat: {due_date}")
        except: pass

    await callback.message.edit_text(res_text, parse_mode="HTML")
    await state.clear()
    await callback.answer()
# --- QARZLAR RO'YXATI ---
@dp.message(F.text == "📊 Qarzlar ro'yxati") # Do'konchi uchun
async def shop_stats(message: Message):
    uid = message.from_user.id
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT COUNT(*), SUM(amount) FROM debts 
        WHERE shop_id = (SELECT id FROM shops WHERE owner_id = ?) AND status = 'unpaid'
    """, (uid,))
    res = cursor.fetchone()
    conn.close()

    count = res[0] if res[0] else 0
    total = res[1] if res[1] else 0

    text = (
        "📈 <b>Sizning do'koningiz ko'rsatkichlari:</b>\n"
        "────────────────────\n"
        f"👥 Qarzdorlar soni: <b>{count} ta</b>\n"
        f"💰 Jami kutilayotgan summa: <b>{total:,} so'm</b>\n"
        "────────────────────\n"
        "<i>Eslatma: To'langan qarzlar avtomatik o'chiriladi.</i>"
    )
    await message.answer(text, parse_mode="HTML")

# 1. To'lovni qabul qilishni boshlash
@dp.message(F.text == "💰 To'lovni qabul qilish")
async def payment_start(message: Message, state: FSMContext):
    await state.set_state(PaymentStates.waiting_for_phone_last4)
    await message.answer("Mijoz telefon raqamining oxirgi 4 ta raqamini kiriting:")

# 2. Raqam bo'yicha qidirish
@dp.message(PaymentStates.waiting_for_phone_last4)
async def payment_find_user(message: Message, state: FSMContext):
    last4 = message.text.strip()
    if not last4.isdigit() or len(last4) != 4:
        return await message.answer("Iltimos, faqat 4 ta raqam yuboring!")

    uid = message.from_user.id
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Oxirgi 4 raqam bo'yicha topish (LIKE %1234)
    cursor.execute("""
        SELECT id, customer_name, customer_phone, amount, debt_date 
        FROM debts 
        WHERE shop_id = (SELECT id FROM shops WHERE owner_id = ?) 
        AND customer_phone LIKE ? AND status = 'unpaid'
    """, (uid, f'%{last4}'))
    
    debts = cursor.fetchall()
    conn.close()

    if not debts:
        await message.answer("Bunday raqamli qarzdor topilmadi.")
        await state.clear()
        return

    await message.answer(f"🔍 Topilgan qarzlar ({len(debts)} ta):")
    
    for d in debts:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ To'liq to'lash", callback_data=f"pay_full_{d[0]}"),
                InlineKeyboardButton(text="📉 Qisman qirqish", callback_data=f"pay_part_{d[0]}")
            ]
        ])
        
        await message.answer(
            f"👤 <b>Mijoz:</b> {d[1]}\n"
            f"📞 <b>Tel:</b> {d[2]}\n"
            f"💰 <b>Qarz:</b> {d[3]:,} so'm\n"
            f"🗓 <b>Sana:</b> {d[4]}",
            reply_markup=kb,
            parse_mode="HTML"
        )

# 3. To'liq to'lov (Callback)
@dp.callback_query(F.data.startswith("pay_full_"))
async def process_full_payment(callback: types.CallbackQuery):
    debt_id = int(callback.data.split("_")[2])
    
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Statusni o'zgartirish o'rniga - o'chirib tashlaymiz!
    cursor.execute("DELETE FROM debts WHERE id = ?", (debt_id,))
    
    conn.commit()
    conn.close()

    await callback.message.edit_text("✅ To'lov qabul qilindi va qarz bazadan o'chirildi.")
    await callback.answer()

# 4. Qisman to'lov (Callback)
@dp.callback_query(F.data.startswith("pay_part_"))
async def process_partial_payment(callback: types.CallbackQuery, state: FSMContext):
    debt_id = int(callback.data.split("_")[2])
    await state.update_data(active_debt_id=debt_id)
    await state.set_state(PaymentStates.waiting_for_partial_amount)
    await callback.message.answer("Qancha summa to'lanmoqda? (Masalan: 50000)")
    await callback.answer()

# 5. Qisman summani ayirish
@dp.message(PaymentStates.waiting_for_partial_amount)
async def save_partial_payment(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Iltimos, faqat raqam kiriting!")
    
    pay_amount = float(message.text)
    data = await state.get_data()
    debt_id = data['active_debt_id']

    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Hozirgi qarzni olamiz
    cursor.execute("SELECT amount, customer_id FROM debts WHERE id = ?", (debt_id,))
    current = cursor.fetchone()
    
    if current[0] <= pay_amount:
        # Agar to'lov qarzdan ko'p yoki teng bo'lsa - to'liq yopiladi
        cursor.execute("UPDATE debts SET status = 'paid', amount = 0 WHERE id = ?", (debt_id,))
        msg = "Qarz to'liq yopildi!"
    else:
        # Qarzdan yechib qolganini saqlaymiz
        new_amount = current[0] - pay_amount
        cursor.execute("UPDATE debts SET amount = ? WHERE id = ?", (new_amount, debt_id))
        msg = f"Qarzdan {pay_amount:,} so'm yechildi. Qolgan qarz: {new_amount:,} so'm."

    conn.commit()
    conn.close()
    
    await message.answer(f"✅ {msg}")
    
    if current[1]: # Mijozga xabarnoma
        try:
            await bot.send_message(current[1], f"💰 To'lov qabul qilindi: {pay_amount:,} so'm.\n" + msg)
        except: pass

    await state.clear()


# 1. Qidiruvni boshlash
@dp.message(F.text == "🔍 Qidirish")
async def universal_search_start(message: Message, state: FSMContext):
    await state.set_state(ShopSearchStates.waiting_for_query)
    await message.answer("🔍 Qidirish uchun mijozning ismi yoki telefon raqamini kiriting:")

# 2. Qidiruv natijalarini chiqarish
@dp.message(ShopSearchStates.waiting_for_query)
async def process_universal_search(message: Message, state: FSMContext):
    query = message.text.strip()
    uid = message.from_user.id
    
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Do'kon ID sini aniqlaymiz
    cursor.execute("SELECT id FROM shops WHERE owner_id = ?", (uid,))
    shop_res = cursor.fetchone()
    
    if not shop_res:
        conn.close()
        return await message.answer("Siz do'kon egasi emassiz.")
    
    shop_id = shop_res[0]

    # UNIVERSAL QIDIRUV: Ismi bo'yicha YOKI Telefon raqami bo'yicha
    cursor.execute("""
        SELECT customer_name, customer_phone, amount, due_date, status, id
        FROM debts 
        WHERE shop_id = ? 
        AND (customer_name LIKE ? OR customer_phone LIKE ?)
        ORDER BY status DESC -- Avval to'lanmaganlar chiqadi
    """, (shop_id, f'%{query}%', f'%{query}%'))
    
    results = cursor.fetchall()
    conn.close()

    if not results:
        await message.answer(f"😔 '{query}' bo'yicha hech qanday ma'lumot topilmadi.")
        await state.clear()
        return

    await message.answer(f"🔎 <b>'{query}'</b> bo'yicha {len(results)} ta natija:")

    for res in results:
        status_icon = "🔴 To'lanmagan" if res[4] == 'unpaid' else "🟢 To'langan"
        
        # Har bir topilgan natija ostiga To'lov tugmasini ham qo'shib ketamiz (qulaylik uchun)
        kb = None
        if res[4] == 'unpaid':
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ To'liq yopish", callback_data=f"pay_full_{res[5]}"),
                    InlineKeyboardButton(text="📉 Qisman", callback_data=f"pay_part_{res[5]}")
                ]
            ])

        text = (f"👤 <b>Mijoz:</b> {res[0]}\n"
                f"📞 <b>Tel:</b> {res[1]}\n"
                f"💰 <b>Summa:</b> {res[2]:,} so'm\n"
                f"📅 <b>Muddat:</b> {res[3]}\n"
                f"📊 <b>Holat:</b> {status_icon}")
        
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

    await state.clear()


# 1. E'lon yuborishni boshlash
@dp.message(F.text == "📢 E'lon yuborish")
async def shop_broadcast_start(message: Message, state: FSMContext):
    await state.set_state(ShopBroadcast.waiting_for_message)
    await message.answer("📣 <b>Faqat sizning qarzdorlaringizga</b> yuboriladigan xabar matnini kiriting:")

# 2. Xabarni tarqatish
@dp.message(ShopBroadcast.waiting_for_message)
async def process_shop_broadcast(message: Message, state: FSMContext):
    broadcast_text = message.text
    uid = message.from_user.id # Do'konchi IDsi
    
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Do'kon ma'lumotlarini va uning qarzdorlarini olamiz
    # Faqat botga a'zo bo'lgan (customer_id bor) va qarzi uzilmaganlarni olamiz
    cursor.execute("""
        SELECT DISTINCT d.customer_id, s.name 
        FROM debts d 
        JOIN shops s ON d.shop_id = s.id 
        WHERE s.owner_id = ? AND d.customer_id IS NOT NULL AND d.status = 'unpaid'
    """, (uid,))
    
    customers = cursor.fetchall()
    conn.close()

    if not customers:
        await message.answer("Sizda hali botdan ro'yxatdan o'tgan qarzdorlar yo'q.")
        await state.clear()
        return

    shop_name = customers[0][1]
    sent_count = 0
    
    await message.answer(f"🚀 Xabar yuborish boshlandi...")

    for customer in customers:
        try:
            target_id = customer[0]
            text = (f"📩 <b>{shop_name} do'konidan xabar:</b>\n\n"
                    f"{broadcast_text}")
            
            await bot.send_message(target_id, text, parse_mode="HTML")
            sent_count += 1
            await asyncio.sleep(0.05) # Telegram limitidan oshmaslik uchun
        except Exception:
            continue

    await message.answer(f"✅ Xabar {sent_count} ta qarzdoringizga muvaffaqiyatli yuborildi.")
    await state.clear()



import pandas as pd
import os
from aiogram.types import FSInputFile

# --- EXCEL HISOBOT YARATISH ---
@dp.message(F.text == "📊 Excel hisobot", F.from_user.id != SUPER_ADMIN_ID) # Faqat do'konchilar uchun
async def export_debts_to_excel(message: Message):
    uid = message.from_user.id
    conn = sqlite3.connect('qarz_tizimii.db')
    
    # Do'kon ma'lumotlarini va qarzlarini birlashtirib olamiz
    query = """
        SELECT d.customer_name AS 'Mijoz ismi', 
               d.customer_phone AS 'Telefon', 
               d.amount AS 'Qarz miqdori', 
               d.due_date AS 'To''lov muddati',
               d.status AS 'Holati'
        FROM debts d
        JOIN shops s ON d.shop_id = s.id
        WHERE s.owner_id = ? AND d.status = 'unpaid'
    """
    
    # Pandas orqali ma'lumotni o'qiymiz
    df = pd.read_sql_query(query, conn, params=(uid,))
    conn.close()

    if df.empty:
        return await message.answer("Hozircha hisobot uchun ma'lumotlar yetarli emas (qarzlar yo'q).")

    # Fayl nomi
    file_name = f"hisobot_{uid}.xlsx"
    
    # Excelga yozish
    df.to_excel(file_name, index=False, engine='openpyxl')

    # Faylni yuborish
    document = FSInputFile(file_name)
    await message.answer_document(document, caption="📈 Sizning do'koningiz bo'yicha qarzdorlar ro'yxati.")
    
    # Yuborgandan keyin serverdan faylni o'chirib tashlaymiz (tozalik uchun)
    os.remove(file_name)
# --- ISHGA TUSHIRISH ---
async def main():
    init_db()
    
    # Eslatmalarni sozlash
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    # Soat 09:00, 14:00 va 20:00 da avtomatik yuboradi
    scheduler.add_job(auto_reminder, 'cron', hour='9,14,20,22', minute=0)
    
    # AGAR TEST QILMOQCHI BO'LSANGIZ (har 1 minutda yuboradi):
    # scheduler.add_job(auto_reminder, 'interval', minutes=1)
    
    scheduler.start()
    
    print("🚀 Bot va Scheduler ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi")