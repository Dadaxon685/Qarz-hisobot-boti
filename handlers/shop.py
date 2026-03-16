import asyncio
import sqlite3
import re
# import d
# at000+00etime
from datetime import datetime

import logging
from aiogram import Router, F, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import State, StatesGroup
from states import PaymentStates, ShopSearchStates, ShopBroadcast
# API_TOKEN = '8340168068:AAE126I8LCTcEcGfrAh9pqJ2c7cB4Ih7fJs'
from buttons import shop_keyboard
SUPER_ADMIN_ID = 5148276461
shop_router = Router()

# --- MaskanCHI HOLATLARI ---
class DebtAdd(StatesGroup):
    customer_phone = State()
    found_existing = State()
    customer_name = State()
    amount = State()
    due_date = State()
    confirm = State()

# --- MaskanCHI KLAVIATURASI ---
def cancel_keyboard():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🚫 Bekor qilish")]
    ], resize_keyboard=True)

@shop_router.message(F.text == "➕ Qarz yozish")
async def debt_start(message: Message, state: FSMContext):
    await state.set_state(DebtAdd.customer_phone)
    # Asosiy menyu o'rniga faqat bekor qilish tugmasi chiqadi
    await message.answer(
        "📞 Qarzdorning telefon raqamini kiriting (masalan: +998901234567):",
        reply_markup=cancel_keyboard()
    )

@shop_router.message(F.text == "🚫 Bekor qilish")
async def cancel_action(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return # Agar hech qanday jarayon bo'lmasa, javob bermaymiz

    await state.clear()
    await message.answer(
        "📥 Jarayon bekor qilindi.", 
        reply_markup=shop_keyboard() # Asosiy menyu qaytadi
    )

# --- 2. RAQAMNI TEKSHIRISH VA BAZADAN QIDIRISH ---
@shop_router.message(DebtAdd.customer_phone)
async def debt_phone_check(message: Message, state: FSMContext):
    phone = message.text.strip()
    
    if not re.match(r'^\+?998\d{9}$', phone):
        return await message.answer("❌ <b>Xato format!</b>\nNamuna: <code>+998901234567</code>", parse_mode="HTML")
    
    if not phone.startswith('+'): phone = '+' + phone
    await state.update_data(customer_phone=phone)
    
    uid = message.from_user.id
    
    try:
        conn = sqlite3.connect('qarz_tizimii.db')
        cursor = conn.cursor()
        
        # Avval Maskanchini aniqlab olamiz (shop_id kerak)
        cursor.execute("SELECT id FROM shops WHERE owner_id = ?", (uid,))
        shop_res = cursor.fetchone()
        
        if not shop_res:
            conn.close()
            return await message.answer("⚠️ Siz Maskan egasi sifatida ro'yxatdan o'tmagansiz!")
        
        shop_id = shop_res[0]
        await state.update_data(shop_id=shop_id)

        # Mijozning qarzi borligini tekshiramiz
        cursor.execute("""
            SELECT customer_name, amount, due_date FROM debts 
            WHERE shop_id = ? AND customer_phone = ? AND status = 'unpaid'
        """, (shop_id, phone))
        existing = cursor.fetchone()
        conn.close()

        if existing:
            name, amount, date = existing
            await state.update_data(customer_name=name)
            
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Ustiga qo'shish", callback_data="existing_add")],
                [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="existing_cancel")]
            ])
            
            text = (f"⚠️ <b>Ushbu mijozda faol qarz bor!</b>\n\n"
                    f"👤 Ismi: <b>{name}</b>\n"
                    f"💰 Qarzi: <b>{amount:,} so'm</b>\n\n"
                    f"Yangi summani qo'shmoqchimisiz?")
            
            await state.set_state(DebtAdd.found_existing)
            await message.answer(text, reply_markup=kb, parse_mode="HTML")
            
        else:
            # YANGI MIJOZ
            await state.set_state(DebtAdd.customer_name) 
            await message.answer(
                f"✅ Raqam: <code>{phone}</code>\n\n"
                "🆕 <b>Yangi mijoz!</b>\n👤 Iltimos, mijoz ismini kiriting:", 
                parse_mode="HTML",
                reply_markup=types.ReplyKeyboardRemove()
            )

    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")

# --- 3. CALLBACKLAR (MAVJUD MIJOZ UCHUN) ---
@shop_router.callback_query(DebtAdd.found_existing, F.data == "existing_add")
async def process_existing_add(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(DebtAdd.amount)
    await callback.message.edit_text("💰 Qo'shiladigan summa miqdorini kiriting:")
    await callback.answer()

@shop_router.callback_query(DebtAdd.found_existing, F.data == "existing_cancel")
async def process_existing_cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Jarayon bekor qilindi.")
    await callback.answer()

# --- 4. ISMNI QABUL QILISH (YANGI MIJOZ UCHUN) ---
@shop_router.message(DebtAdd.customer_name)
async def debt_name_set(message: Message, state: FSMContext):
    await state.update_data(customer_name=message.text.strip())
    await state.set_state(DebtAdd.amount)
    await message.answer("💰 Qarz miqdorini kiriting:")

# --- 5. SUMMANI QABUL QILISH ---
@shop_router.message(DebtAdd.amount)
async def debt_amount_set(message: Message, state: FSMContext):
    amount_str = message.text.strip().replace(' ', '').replace(',', '')
    
    if not amount_str.isdigit():
        return await message.answer("❌ Xato! Faqat raqam kiriting.")
    
    await state.update_data(amount=float(amount_str))
    await state.set_state(DebtAdd.due_date)
    await message.answer("📅 To'lov muddati:(Format: DD.MM.YYYY, masalan: 25.12.2024)")

# --- 6. SANANI TEKSHIRISH VA TASDIQLASH ---
@shop_router.message(DebtAdd.due_date)
async def debt_due_date_confirm(message: Message, state: FSMContext):
    date_str = message.text.strip()
    
    try:
        formatted_date = date_str.replace('-', '.').replace('/', '.')
        valid_date = datetime.strptime(formatted_date, "%d.%m.%Y")
        
        if valid_date.date() < datetime.now().date():
            return await message.answer("⚠️ <b>Xato!</b> Sana bugundan oldingi bo'lishi mumkin emas.")
            
    except ValueError:
        return await message.answer("❌ <b>Sana formati xato!</b>\nNamuna: 31.12.2024")

    await state.update_data(due_date=formatted_date)
    data = await state.get_data()

    await state.set_state(DebtAdd.confirm)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Saqlash", callback_data="confirm_debt_yes"),
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="confirm_debt_no")
        ]
    ])
    
    text = (f"📋 <b>Ma'lumotlarni tekshiring:</b>\n\n"
            f"👤 Mijoz: <b>{data['customer_name']}</b>\n"
            f"💰 Summa: <b>{data['amount']:,} so'm</b>\n"
            f"📅 Muddat: <b>{formatted_date}</b>\n\n"
            f"Saqlaymiz-mi?")
    
    await message.answer(text, reply_markup=kb, parse_mode="HTML")
# --- 5. BAZAGA YOZISH (CALLBACK) ---
@shop_router.callback_query(DebtAdd.confirm, F.data.startswith("confirm_debt_"))
async def debt_confirm_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "confirm_debt_no":
        await state.clear()
        await callback.message.edit_text("❌ Jarayon bekor qilindi.")
        return await callback.answer()

    data = await state.get_data()
    uid = callback.from_user.id
    
    try:
        conn = sqlite3.connect('qarz_tizimii.db')
        cursor = conn.cursor()
        
        # Maskan ma'lumotlarini olish
        cursor.execute("SELECT id, name FROM shops WHERE owner_id = ?", (uid,))
        shop_res = cursor.fetchone()
        if not shop_res:
            return await callback.answer("Xato: Maskan topilmadi!")
        
        shop_id, shop_name = shop_res

        # Mijozning TG ID sini qidirish
        cursor.execute("SELECT customer_id FROM debts WHERE customer_phone = ? AND customer_id IS NOT NULL LIMIT 1", (data['customer_phone'],))
        c_res = cursor.fetchone()
        c_id = c_res[0] if c_res else None

        # Mavjud qarzni tekshirish
        cursor.execute("SELECT id, amount FROM debts WHERE shop_id = ? AND customer_phone = ? AND status = 'unpaid'", (shop_id, data['customer_phone']))
        existing = cursor.fetchone()

        if existing:
            total = existing[1] + data['amount']
            cursor.execute("UPDATE debts SET amount = ?, due_date = ?, debt_date = DATE('now'), customer_id = ? WHERE id = ?", 
                           (total, data['due_date'], c_id, existing[0]))
            res_text = f"✅ Qarz yangilandi. Umumiy summa: <b>{total:,} so'm</b>"
        else:
            cursor.execute("INSERT INTO debts (shop_id, customer_id, customer_phone, customer_name, amount, due_date, status, debt_date) VALUES (?,?,?,?,?,?,?, DATE('now'))",
                           (shop_id, c_id, data['customer_phone'], data['customer_name'], data['amount'], data['due_date'], 'unpaid'))
            res_text = "✅ Yangi qarz muvaffaqiyatli saqlandi."

        conn.commit()
        conn.close()

        # Mijozga bildirishnoma yuborish
        if c_id:
            try:
                await callback.bot.send_message(c_id, f"💰 <b>Qarz hisobingiz yangilandi!</b>\n🏪 {shop_name}\n➕ Qo'shildi: {data['amount']:,} so'm\n📅 Muddat: {data['due_date']}")
            except: pass

        await callback.message.edit_text(res_text, parse_mode="HTML")
        
    except Exception as e:
        await callback.message.answer(f"❌ Xatolik: {e}")
    
    finally:
        await state.clear()
        await callback.answer()

# --- QARZLAR RO'YXATI ---
@shop_router.message(F.text == "📊 Qarzlar umumiy") # Maskanchi uchun
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
        "📈 <b>Sizning Maskaningiz ko'rsatkichlari:</b>\n"
        "────────────────────\n"
        f"👥 Qarzdorlar soni: <b>{count} ta</b>\n"
        f"💰 Jami kutilayotgan summa: <b>{total:,} so'm</b>\n"
        "────────────────────\n"
        "<i>Eslatma: To'langan qarzlar avtomatik o'chiriladi.</i>"
    )
    await message.answer(text, parse_mode="HTML")

# 1. To'lovni qabul qilishni boshlash
@shop_router.message(F.text == "💰 To'lovni qabul qilish")
async def payment_start(message: Message, state: FSMContext):
    await state.set_state(PaymentStates.waiting_for_phone_last4)
    await message.answer("Mijoz telefon raqamining oxirgi 4 ta raqamini kiriting:")

# 2. Raqam bo'yicha qidirish
@shop_router.message(PaymentStates.waiting_for_phone_last4)
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
@shop_router.callback_query(F.data.startswith("pay_full_"))
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
@shop_router.callback_query(F.data.startswith("pay_part_"))
async def process_partial_payment(callback: types.CallbackQuery, state: FSMContext):
    debt_id = int(callback.data.split("_")[2])
    await state.update_data(active_debt_id=debt_id)
    await state.set_state(PaymentStates.waiting_for_partial_amount)
    await callback.message.answer("Qancha summa to'lanmoqda? (Masalan: 50000)")
    await callback.answer()

# 5. Qisman summani ayirish
#  5. Qisman summani ayirish
@shop_router.message(PaymentStates.waiting_for_partial_amount)
async def save_partial_payment(message: Message, state: FSMContext):
    # 1. Statni darhol tozalash (Xabar kelishi bilan yopamiz)
    data = await state.get_data()
    await state.clear() 

    raw_amount = message.text.strip().replace(' ', '').replace(',', '')
    if not raw_amount.isdigit():
        # Agar xato bo'lsa, stateni qayta yoqamiz yoki jarayonni to'xtatamiz
        return await message.answer("❌ Faqat raqam kiriting! To'lov bekor qilindi.")
    
    pay_amount = int(raw_amount)
    debt_id = data.get('active_debt_id')

    if not debt_id:
        return await message.answer("⚠️ Xatolik: Qarz ID topilmadi.")

    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Qarzni tekshirish
    cursor.execute("SELECT amount, customer_id FROM debts WHERE id = ?", (debt_id,))
    res = cursor.fetchone()

    if not res:
        conn.close()
        return await message.answer("❌ Qarz topilmadi.")

    current_debt, customer_id = res

    if pay_amount >= current_debt:
        cursor.execute("DELETE FROM debts WHERE id = ?", (debt_id,))
        msg = "✅ Qarz to'liq yopildi va o'chirildi."
    else:
        new_amount = current_debt - pay_amount
        cursor.execute("UPDATE debts SET amount = ? WHERE id = ?", (new_amount, debt_id))
        msg = f"✅ {pay_amount:,} so'm qabul qilindi. Qolgan: {new_amount:,} so'm."

    conn.commit()
    conn.close()
    
    # Javob xabari va Maskanchi menyusini qaytarish
    await message.answer(msg, reply_markup=shop_keyboard())
    
    # Mijozga xabar (ixtiyoriy)
    if customer_id:
        try:
            await message.bot.send_message(customer_id, f"💰 To'lov: {pay_amount:,} so'm.\n{msg}")
        except: pass

# 1. Qidiruvni boshlash
@shop_router.message(F.text == "🔍 Qidirish")
async def universal_search_start(message: Message, state: FSMContext):
    await state.set_state(ShopSearchStates.waiting_for_query)
    await message.answer("🔍 Qidirish uchun mijozning ismi yoki telefon raqamini kiriting:")

# 2. Qidiruv natijalarini chiqarish
@shop_router.message(ShopSearchStates.waiting_for_query)
async def process_universal_search(message: Message, state: FSMContext):
    query = message.text.strip()
    uid = message.from_user.id
    
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Maskan ID sini aniqlaymiz
    cursor.execute("SELECT id FROM shops WHERE owner_id = ?", (uid,))
    shop_res = cursor.fetchone()
    
    if not shop_res:
        conn.close()
        return await message.answer("Siz Maskan egasi emassiz.")
    
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
@shop_router.message(F.text == "📢 E'lon yuborish")
async def shop_broadcast_start(message: Message, state: FSMContext):
    await state.set_state(ShopBroadcast.waiting_for_message)
    await message.answer("📣Faqat sizning qarzdorlaringizga yuboriladigan xabar matnini kiriting:")

# 2. Xabarni tarqatish
@shop_router.message(ShopBroadcast.waiting_for_message)
async def process_shop_broadcast(message: Message, state: FSMContext):
    broadcast_text = message.text
    uid = message.from_user.id # Maskanchi IDsi
    
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Maskan ma'lumotlarini va uning qarzdorlarini olamiz
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
            text = (f"📩 <b>{shop_name} Maskanidan xabar:</b>\n\n"
                    f"{broadcast_text}")
            
            await message.bot.send_message(target_id, text, parse_mode="HTML")
            sent_count += 1
            await asyncio.sleep(0.05) # Telegram limitidan oshmaslik uchun
        except Exception:
            continue

    await message.answer(f"✅ Xabar {sent_count} ta qarzdoringizga muvaffaqiyatli yuborildi.")
    await state.clear()


import sqlite3
import io
from openpyxl import Workbook
from aiogram import types, F
from aiogram.types import BufferedInputFile

@shop_router.message(F.text == "📈 Excel hisobot")
async def export_excel(message: types.Message):
    uid = message.from_user.id
    
    # 1. Ma'lumotlarni bazadan olish
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Maskan ID sini olish
    cursor.execute("SELECT id, name FROM shops WHERE owner_id = ?", (uid,))
    shop = cursor.fetchone()
    
    if not shop:
        conn.close()
        return await message.answer("Siz Maskan egasi emassiz!")
    
    shop_id, shop_name = shop
    
    # Qarzlar ro'yxatini olish
    cursor.execute("""
        SELECT customer_name, customer_phone, amount, due_date, status, debt_date 
        FROM debts WHERE shop_id = ?
    """, (shop_id,))
    rows = cursor.fetchall()
    conn.close()

    # --- TEKSHIRUV QISMI ---
    if not rows:
        return await message.answer(
            f"❌ <b>{shop_name}</b> Maskanida hali qarz olgan mijozlar mavjud emas."
        )
    # -----------------------

    # 2. Excel faylini yaratish (openpyxl orqali)
    wb = Workbook()
    ws = wb.active
    ws.title = "Qarzlar Hisoboti"
    
    # Sarlavhalarni chiroyli qilish (Ixtiyoriy: Stil qo'shish mumkin)
    headers = ["Mijoz Ismi", "Telefon", "Summa", "Muddat", "Holat", "Yozilgan sana"]
    ws.append(headers)
    
    # Ma'lumotlarni qo'shish
    for row in rows:
        ws.append(row)
    
    # 3. Faylni xotirada (Buffer) saqlash
    excel_file = io.BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)
    
    # 4. Foydalanuvchiga yuborish
    document = BufferedInputFile(
        excel_file.getvalue(), 
        filename=f"{shop_name}_qarzlar.xlsx"
    )
    
    await message.answer_document(
        document=document, 
        caption=f"📊 <b>{shop_name}</b> Maskani uchun to'liq hisobot."
    )
@shop_router.message(F.text == "📖 Botdan foydalanish")
async def shop_help_guide(message: Message):
    guide_text = (
        "📖 <b>BOTDAN FOYDALANISH BO'YICHA TO'LIQ QO'LLANMA</b>\n\n"
        "Botingiz orqali savdo va qarz hisob-kitoblarini avtomatlashtirish uchun quyidagi imkoniyatlardan foydalaning:\n\n"
        
        "➕ <b>1. Qarz yozish</b>\n"
        "Yangi qarz kiritish uchun ushbu tugmani bosing. Mijozning telefon raqamini kiritganingizda, bot avtomatik tarzda bazani tekshiradi. Agar mijoz mavjud bo'lsa, yangi qarz eskisiga qo'shiladi, bo'lmasa yangi profil yaratiladi.\n\n"
        
        "💰 <b>2. To'lovni qabul qilish</b>\n"
        "Mijoz qarzining bir qismini yoki hammasini to'laganda foydalaniladi. To'lov kiritilgach, umumiy qarz miqdori avtomatik kamayadi va tarixda saqlanadi.\n\n"
        
        "🔍 <b>3. Qidirish tizimi</b>\n"
        "Ism yoki telefon raqami orqali mijozni soniyalar ichida toping. Mijozning barcha operatsiyalari va joriy qarzi bitta oynada ko'rinadi.\n\n"
        
        "📊 <b>4. Ro'yxat va Hisobotlar</b>\n"
        "• <b>Qarzlar ro'yxati:</b> Barcha faol qarzdorlar va umumiy summa.\n"
        "• <b>Excel hisobot:</b> Barcha ma'lumotlarni (ism, raqam, summa, sana) Excel formatida yuklab olish.\n\n"
        
        "📢 <b>5. E'lon yuborish</b>\n"
        "Barcha qarzdorlarga bir vaqtda xabar yuborish imkoniyati. Bu reklama yoki umumiy ogohlantirish uchun juda qulay.\n\n"
        
        "🔔 <b>6. Avtomatik eslatmalar</b>\n"
        "Sizdan qo'shimcha harakat talab etilmaydi! Bot har kuni <b>4 marta</b> belgilangan vaqtlarda (09:00, 13:00, 17:00, 21:00) qarzdorlarga ularning qarzi haqida muloyim eslatma yuboradi.\n\n"
        
        "🛡 <i>Ma'lumotlaringiz xavfsizligi va maxfiyligi to'liq kafolatlangan!</i>"
    )
    
    await message.answer(guide_text, parse_mode="HTML")

from datetime import datetime
import sqlite3
from aiogram import types, F

@shop_router.message(F.text == "🚨 Muddati o'tganlar")
async def show_overdue_debts(message: types.Message):
    uid = message.from_user.id
    
    # 1. Bugungi sanani olish (DD.MM.YYYY formatida bo'lsa)
    today_str = datetime.now().strftime("%d.%m.%Y")
    # SQL-da solishtirish oson bo'lishi uchun YYYY-MM-DD formatiga o'tkazish kerak bo'lishi mumkin
    # Lekin bizning bazada sanalar qanday saqlanganiga qarab ish tutamiz.
    
    conn = sqlite3.connect('qarz_tizimii.db')
    cursor = conn.cursor()
    
    # Maskan ID-sini aniqlash
    cursor.execute("SELECT id FROM shops WHERE owner_id = ?", (uid,))
    shop_res = cursor.fetchone()
    
    if not shop_res:
        conn.close()
        return await message.answer("⚠️ Siz Maskan egasi emassiz!")
    
    shop_id = shop_res[0]

    # 2. To'lanmagan qarzlarni olish
    cursor.execute("""
        SELECT customer_name, customer_phone, amount, due_date 
        FROM debts 
        WHERE shop_id = ? AND status = 'unpaid'
    """, (shop_id,))
    all_unpaid = cursor.fetchall()
    conn.close()

    overdue_list = []
    today_date = datetime.now().date()

    # 3. Sanani tekshirish (Format: DD.MM.YYYY)
    for name, phone, amount, d_date in all_unpaid:
        try:
            # Bazadagi satr ko'rinishidagi sanani obyektga o'tkazamiz
            db_date = datetime.strptime(d_date, "%d.%m.%Y").date()
            
            # Agar muddat bugundan kichik bo'lsa - demak muddati o'tgan
            if db_date < today_date:
                overdue_list.append((name, phone, amount, d_date))
        except ValueError:
            continue # Sana formati xato bo'lsa o'tkazib yuboramiz

    # 4. Natijani chiqarish
    if not overdue_list:
        return await message.answer("✅ <b>Hozircha muddati o'tgan qarzdorlar yo'q.</b>", parse_mode="HTML")

    text = "🚨 <b>MUDDATI O'TGAN QARZLAR:</b>\n"
    text += "────────────────────\n"
    
    total_overdue = 0
    for name, phone, amount, date in overdue_list:
        text += f"👤 <b>{name}</b>\n"
        text += f"📞 {phone}\n"
        text += f"💰 <b>{amount:,} so'm</b> (Muddat: {date})\n"
        text += "────────────────────\n"
        total_overdue += amount

    text += f"\n🏦 <b>JAMI KECHIKKAN:</b> <u>{total_overdue:,} so'm</u>"
    
    await message.answer(text, parse_mode="HTML")
