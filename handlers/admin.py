import asyncio
import sqlite3
from aiogram import Router, F, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import State, StatesGroup

from aiogram.filters import CommandStart
# 1. Routerni yaratish
admin_router = Router()

# 2. Super Admin ID (Buni configdan olgan ma'qul)
SUPER_ADMIN_ID = 5148276461

# 3. Faqat admin kirishi uchun filtr o'rnatamiz
admin_router.message.filter(F.from_user.id == SUPER_ADMIN_ID)

# 4. FSM (Holatlar)
class ShopRegistration(StatesGroup):
    name = State()
    owner_id = State()
    phone = State()
    address = State()
    confirm = State()

class BroadcastState(StatesGroup):
    message = State()

# 5. Klaviatura funksiyasi
def admin_keyboard():
    buttons = [
        [KeyboardButton(text="🏪 Do'kon qo'shish"), KeyboardButton(text="🔍 Do'konni qidirish")],
        [KeyboardButton(text="📝 Do'konlar ro'yxati"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="📢 Reklama yuborish")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


@admin_router.message(CommandStart())
async def admin_start(message: Message):
    await message.answer("Xush kelibsiz, Boss!", reply_markup=admin_keyboard())


def cancel_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚫 Bekor qilish")]
    ], resize_keyboard=True)

# 6. Admin Handlerlar
@admin_router.message(F.text == "🏪 Do'kon qo'shish")
async def start_shop_reg(message: Message, state: FSMContext):
    await state.set_state(ShopRegistration.name)
    await message.answer("🏪 Do'kon nomini kiriting:", reply_markup=cancel_keyboard())

@admin_router.message(F.text == "🚫 Bekor qilish")
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("📥 Jarayon bekor qilindi.", reply_markup=admin_keyboard())

# Qolgan barcha admin buyruqlarini shu yerga davom ettiring...


@admin_router.message(ShopRegistration.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await state.set_state(ShopRegistration.owner_id)
    await message.answer("Do'kon egasining Telegram ID raqamini yuboring:")

@admin_router.message(ShopRegistration.owner_id)
async def process_owner_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("ID faqat raqamlardan iborat bo'lishi kerak!")
    await state.update_data(owner_id=int(message.text))
    await state.set_state(ShopRegistration.phone)
    await message.answer("Do'konchi telefon raqamini kiriting:")

@admin_router.message(ShopRegistration.phone)
async def process_phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(ShopRegistration.address)
    await message.answer("Do'kon manzilini kiriting:")

# 1. Manzil kiritilgandan keyin darrov bazaga yozmaymiz, tekshirishga chiqaramiz
@admin_router.message(ShopRegistration.address)
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
@admin_router.callback_query(ShopRegistration.confirm, F.data.startswith("confirm_shop_"))
async def shop_confirm_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "confirm_shop_no":
        await state.clear()
        await callback.message.edit_text("❌ Do'kon qo'shish bekor qilindi.")
        return await callback.answer()

    # Tasdiqlash bosilganda
    data = await state.get_data()
    
    try: # ASOSIY TRY (Bazaga yozish uchun)
        conn = sqlite3.connect('qarz_tizimii.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO shops (name, owner_id, phone, address) VALUES (?, ?, ?, ?)",
            (data['name'], data['owner_id'], data['phone'], data['address'])
        )
        conn.commit()
        conn.close()
        
        await callback.message.edit_text(f"✅ <b>{data['name']}</b> do'koni muvaffaqiyatli qo'shildi!")
        
        # Do'kon egasiga xabar yuborish
        try: # ICHKI TRY (Xabar yuborish uchun)
            await callback.bot.send_message(
                chat_id=data['owner_id'], 
                text=f"🎉 Tabriklaymiz! {data['name']} do'koni tizimga qo'shildi.\n/start tugmasini bosing."
            )
        except Exception as e:
            print(f"Xabar yuborishda xato: {e}")
            await callback.message.answer("⚠️ Do'konchiga xabar yetib bormadi.")

    except Exception as db_error: # TASHQI TRY uchun EXCEPT
        print(f"Baza xatosi: {db_error}")
        await callback.message.answer(f"❌ Bazaga yozishda xatolik yuz berdi.")
    
    finally: # Har doim ishlaydi
        await state.clear()
        await callback.answer()

# 2. DO'KONLAR RO'YXATI
@admin_router.message(F.text == "📝 Do'konlar ro'yxati", F.from_user.id == SUPER_ADMIN_ID)
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
@admin_router.message(F.text == "📢 Reklama yuborish", F.from_user.id == SUPER_ADMIN_ID)
async def start_broadcast(message: Message, state: FSMContext):
    await state.set_state(AdminStatess.waiting_for_ad_text) # Endi xato bermaydi
    await message.answer("Barcha foydalanuvchilarga yuboriladigan reklama matnini kiriting:")

# --- REKLAMANI YUBORISH ---
@admin_router.message(AdminStatess.waiting_for_ad_text)
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
            await message.bot.send_message(user_id, f"📣 <b>ADMIN XABARI</b>\n\n{ad_text}", parse_mode="HTML")
            sent_count += 1
            await asyncio.sleep(0.05) # Spamga tushmaslik uchun
        except:
            continue
    
    await message.answer(f"✅ Reklama {sent_count} ta foydalanuvchiga muvaffaqiyatli yuborildi.")
    await state.clear()

# --- DO'KONLAR RO'YXATI VA O'CHIRISH ---
@admin_router.message(F.text == "📝 Do'konlar ro'yxati", F.from_user.id == SUPER_ADMIN_ID)
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

@admin_router.message(AdminStatess.waiting_for_shop_id_to_delete)
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
@admin_router.message(F.text == "📊 Statistika", F.from_user.id == SUPER_ADMIN_ID)
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
@admin_router.message(F.text == "🔍 Do'konni qidirish", F.from_user.id == SUPER_ADMIN_ID)
async def search_shop_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_search_query)
    await message.answer("Qidirilayotgan do'kon nomini yoki qismini kiriting:")

# --- QIDIRUV NATIJASI ---
@admin_router.message(AdminStates.waiting_for_search_query)
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
@admin_router.callback_query(F.data.startswith("del_shop_"))
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
