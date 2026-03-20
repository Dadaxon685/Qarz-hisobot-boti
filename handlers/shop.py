import asyncio
import re
import io
import logging
from datetime import datetime
from openpyxl import Workbook

from aiogram import Router, F, types
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
)
from aiogram.fsm.context import FSMContext
from aiogram.filters.state import State, StatesGroup

from states import PaymentStates, ShopSearchStates, ShopBroadcast
from buttons import shop_keyboard

# SQLite o'rniga PostgreSQL ulanishini ishlatamiz
from handlers.connections import get_connection

SUPER_ADMIN_ID = 5148276461
shop_router = Router()


# --- MASKANCHI HOLATLARI ---
class DebtAdd(StatesGroup):
    customer_phone = State()
    found_existing = State()
    customer_name = State()
    amount = State()
    due_date = State()
    confirm = State()


# --- BEKOR QILISH KLAVIATURASI ---
def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🚫 Bekor qilish")]],
        resize_keyboard=True
    )


# ============================================================
# QARZ YOZISH
# ============================================================

@shop_router.message(F.text == "➕ Qarz yozish")
async def debt_start(message: Message, state: FSMContext):
    await state.set_state(DebtAdd.customer_phone)
    await message.answer(
        "📞 Qarzdorning telefon raqamini kiriting (masalan: +998901234567):",
        reply_markup=cancel_keyboard()
    )


@shop_router.message(F.text == "🚫 Bekor qilish")
async def cancel_action(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.clear()
    await message.answer("📥 Jarayon bekor qilindi.", reply_markup=shop_keyboard())


@shop_router.message(DebtAdd.customer_phone)
async def debt_phone_check(message: Message, state: FSMContext):
    phone = message.text.strip()

    if not re.match(r'^\+?998\d{9}$', phone):
        return await message.answer(
            "❌ Xato format!\nNamuna: <code>+998901234567</code>",
            parse_mode="HTML"
        )

    if not phone.startswith('+'):
        phone = '+' + phone
    await state.update_data(customer_phone=phone)

    uid = message.from_user.id
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Maskan ID sini aniqlaymiz
        # SQLite: ? → PostgreSQL: %s
        cursor.execute("SELECT id FROM shops WHERE owner_id = %s", (uid,))
        shop_res = cursor.fetchone()

        if not shop_res:
            return await message.answer("⚠️ Siz Maskan egasi sifatida ro'yxatdan o'tmagansiz!")

        shop_id = shop_res[0]
        await state.update_data(shop_id=shop_id)

        # Telefon raqami orqali mijozning Telegram ID sini qidirish
        cursor.execute("""
            SELECT customer_id FROM debts
            WHERE customer_phone = %s AND customer_id IS NOT NULL
            LIMIT 1
        """, (phone,))
        c_res = cursor.fetchone()
        c_id = c_res[0] if c_res else None

        # Agar bazada bo'lmasa, users jadvalidan qidirish
        if not c_id:
            cursor.execute("SELECT telegram_id FROM users WHERE phone = %s", (phone,))
            user_res = cursor.fetchone()
            c_id = user_res[0] if user_res else None

        # Mavjud qarzni tekshiramiz
        cursor.execute("""
            SELECT customer_name, amount, due_date FROM debts
            WHERE shop_id = %s AND customer_phone = %s AND status = 'unpaid'
        """, (shop_id, phone))
        existing = cursor.fetchone()

        if existing:
            name, amount, date = existing
            await state.update_data(customer_name=name)

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Ustiga qo'shish", callback_data="existing_add")],
                [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="existing_cancel")]
            ])

            text = (
                f"⚠️ <b>Ushbu mijozda faol qarz bor!</b>\n\n"
                f"👤 Ismi: <b>{name}</b>\n"
                f"💰 Qarzi: <b>{amount:,} so'm</b>\n\n"
                f"Yangi summani qo'shmoqchimisiz?"
            )
            await state.set_state(DebtAdd.found_existing)
            await message.answer(text, reply_markup=kb, parse_mode="HTML")

        else:
            await state.set_state(DebtAdd.customer_name)
            await message.answer(
                f"✅ Raqam: <code>{phone}</code>\n\n"
                "🆕 <b>Yangi mijoz!</b>\n👤 Iltimos, mijoz ismini kiriting:",
                parse_mode="HTML",
                reply_markup=types.ReplyKeyboardRemove()
            )

    except Exception as e:
        await message.answer(f"❌ Xatolik: {e}")
    finally:
        if conn:
            conn.close()


# --- MAVJUD MIJOZ CALLBACKLARI ---

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


# --- YANGI MIJOZ UCHUN ISM ---

@shop_router.message(DebtAdd.customer_name)
async def debt_name_set(message: Message, state: FSMContext):
    await state.update_data(customer_name=message.text.strip())
    await state.set_state(DebtAdd.amount)
    await message.answer("💰 Qarz miqdorini kiriting:")


# --- SUMMA QABUL QILISH ---

@shop_router.message(DebtAdd.amount)
async def debt_amount_set(message: Message, state: FSMContext):
    amount_str = message.text.strip().replace(' ', '').replace(',', '')
    if not amount_str.isdigit():
        return await message.answer("❌ Xato! Faqat raqam kiriting.")
    await state.update_data(amount=float(amount_str))
    await state.set_state(DebtAdd.due_date)
    await message.answer("📅 To'lov muddati: (Format: DD.MM.YYYY, masalan: 25.12.2024)")


# --- SANA TEKSHIRISH VA TASDIQLASH ---

@shop_router.message(DebtAdd.due_date)
async def debt_due_date_confirm(message: Message, state: FSMContext):
    date_str = message.text.strip()
    try:
        formatted_date = date_str.replace('-', '.').replace('/', '.')
        valid_date = datetime.strptime(formatted_date, "%d.%m.%Y")
        if valid_date.date() < datetime.now().date():
            return await message.answer("⚠️ Xato! Sana bugundan oldingi bo'lishi mumkin emas.")
    except ValueError:
        return await message.answer("❌ Sana formati xato!\nNamuna: 31.12.2024")

    await state.update_data(due_date=formatted_date)
    data = await state.get_data()
    await state.set_state(DebtAdd.confirm)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Saqlash", callback_data="confirm_debt_yes"),
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="confirm_debt_no")
    ]])

    text = (
        f"📋 <b>Ma'lumotlarni tekshiring:</b>\n\n"
        f"👤 Mijoz: <b>{data['customer_name']}</b>\n"
        f"💰 Summa: <b>{data['amount']:,} so'm</b>\n"
        f"📅 Muddat: <b>{formatted_date}</b>\n\n"
        f"Saqlaymiz-mi?"
    )
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


# --- BAZAGA YOZISH (CALLBACK) ---

@shop_router.callback_query(DebtAdd.confirm, F.data.startswith("confirm_debt_"))
async def debt_confirm_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "confirm_debt_no":
        await state.clear()
        await callback.message.edit_text("❌ Jarayon bekor qilindi.")
        return await callback.answer()

    data = await state.get_data()
    uid = callback.from_user.id
    conn = None

    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, name FROM shops WHERE owner_id = %s", (uid,))
        shop_res = cursor.fetchone()
        if not shop_res:
            return await callback.answer("Xato: Maskan topilmadi!")
        shop_id, shop_name = shop_res

        # Telefon raqami orqali mijoz ID sini topish
        cursor.execute("""
            SELECT customer_id FROM debts
            WHERE customer_phone = %s AND customer_id IS NOT NULL
            LIMIT 1
        """, (data['customer_phone'],))
        c_res = cursor.fetchone()
        c_id = c_res[0] if c_res else None

        if not c_id:
            cursor.execute("SELECT telegram_id FROM users WHERE phone = %s", (data['customer_phone'],))
            user_res = cursor.fetchone()
            c_id = user_res[0] if user_res else None

        # Mavjud qarzni tekshirish
        cursor.execute("""
            SELECT id, amount FROM debts
            WHERE shop_id = %s AND customer_phone = %s AND status = 'unpaid'
        """, (shop_id, data['customer_phone']))
        existing = cursor.fetchone()

        if existing:
            total = existing[1] + data['amount']
            # SQLite: DATE('now') → PostgreSQL: CURRENT_DATE
            cursor.execute("""
                UPDATE debts
                SET amount = %s, due_date = %s, debt_date = CURRENT_DATE, customer_id = %s
                WHERE id = %s
            """, (total, data['due_date'], c_id, existing[0]))
            res_text = f"✅ Qarz yangilandi. Umumiy summa: <b>{total:,} so'm</b>"
        else:
            cursor.execute("""
                INSERT INTO debts
                (shop_id, customer_id, customer_phone, customer_name, amount, due_date, status, debt_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_DATE)
            """, (
                shop_id, c_id, data['customer_phone'], data['customer_name'],
                data['amount'], data['due_date'], 'unpaid'
            ))
            res_text = "✅ Yangi qarz muvaffaqiyatli saqlandi."

        conn.commit()
        await callback.message.edit_text(res_text, parse_mode="HTML")

        # Mijozga xabar yuborish
        if c_id:
            try:
                notification_text = (
                    f"💰 <b>YANGI QARZ YOZILDI!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🏪 <b>Maskan:</b> {shop_name}\n"
                    f"👤 <b>Sizning ismingiz:</b> {data['customer_name']}\n"
                    f"💵 <b>Qarz summasi:</b> {data['amount']:,} so'm\n"
                    f"📅 <b>To'lov muddati:</b> {data['due_date']}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚠️ <i>Iltimos, muddatida to'lang!</i>"
                )
                await callback.bot.send_message(
                    chat_id=c_id, text=notification_text, parse_mode="HTML"
                )
                await callback.message.answer(
                    f"📤 <b>{data['customer_name']}</b>ga Telegram orqali xabar yuborildi!",
                    parse_mode="HTML"
                )
            except Exception as e:
                logging.error(f"Xabar yuborishda xato: {e}")
                await callback.message.answer(
                    "⚠️ Mijozga xabar yetib bormadi. (Bot bloklangan yoki ID xato)"
                )
        else:
            await callback.message.answer(
                f"ℹ️ <b>{data['customer_name']}</b> hali botdan ro'yxatdan o'tmagan.\n"
                f"Qarz saqlandi, lekin xabar yuborilmadi.",
                parse_mode="HTML"
            )

    except Exception as db_error:
        logging.error(f"Baza xatosi: {db_error}")
        await callback.message.answer(f"❌ Bazaga yozishda xatolik yuz berdi: {db_error}")
    finally:
        if conn:
            conn.close()
        await state.clear()
        await callback.answer()


# ============================================================
# QARZLAR UMUMIY (STATISTIKA)
# ============================================================

@shop_router.message(F.text == "📊 Qarzlar umumiy")
async def shop_stats(message: Message):
    uid = message.from_user.id
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*), SUM(amount) FROM debts
            WHERE shop_id = (SELECT id FROM shops WHERE owner_id = %s) AND status = 'unpaid'
        """, (uid,))
        res = cursor.fetchone()

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
    finally:
        if conn:
            conn.close()


# ============================================================
# TO'LOV QABUL QILISH
# ============================================================

@shop_router.message(F.text == "💰 To'lovni qabul qilish")
async def payment_start(message: Message, state: FSMContext):
    await state.set_state(PaymentStates.waiting_for_phone_last4)
    await message.answer("Mijoz telefon raqamining oxirgi 4 ta raqamini kiriting:")


@shop_router.message(PaymentStates.waiting_for_phone_last4)
async def payment_find_user(message: Message, state: FSMContext):
    last4 = message.text.strip()
    if not last4.isdigit() or len(last4) != 4:
        return await message.answer("Iltimos, faqat 4 ta raqam yuboring!")

    uid = message.from_user.id
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # SQLite: LIKE '%1234' → PostgreSQL: LIKE '%1234' (bir xil, lekin ILIKE ham ishlatsa bo'ladi)
        cursor.execute("""
            SELECT id, customer_name, customer_phone, amount, debt_date
            FROM debts
            WHERE shop_id = (SELECT id FROM shops WHERE owner_id = %s)
            AND customer_phone LIKE %s AND status = 'unpaid'
        """, (uid, f'%{last4}'))

        debts = cursor.fetchall()

        if not debts:
            await message.answer("Bunday raqamli qarzdor topilmadi.")
            await state.clear()
            return

        await message.answer(f"🔍 Topilgan qarzlar ({len(debts)} ta):")
        for d in debts:
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ To'liq to'lash", callback_data=f"pay_full_{d[0]}"),
                InlineKeyboardButton(text="📉 Qisman qirqish", callback_data=f"pay_part_{d[0]}")
            ]])
            await message.answer(
                f"👤 <b>Mijoz:</b> {d[1]}\n"
                f"📞 <b>Tel:</b> {d[2]}\n"
                f"💰 <b>Qarz:</b> {d[3]:,} so'm\n"
                f"🗓 <b>Sana:</b> {d[4]}",
                reply_markup=kb, parse_mode="HTML"
            )
    finally:
        if conn:
            conn.close()


@shop_router.callback_query(F.data.startswith("pay_full_"))
async def process_full_payment(callback: types.CallbackQuery):
    debt_id = int(callback.data.split("_")[2])
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM debts WHERE id = %s", (debt_id,))
        conn.commit()
        await callback.message.edit_text("✅ To'lov qabul qilindi va qarz bazadan o'chirildi.")
    finally:
        if conn:
            conn.close()
    await callback.answer()


@shop_router.callback_query(F.data.startswith("pay_part_"))
async def process_partial_payment(callback: types.CallbackQuery, state: FSMContext):
    debt_id = int(callback.data.split("_")[2])
    await state.update_data(active_debt_id=debt_id)
    await state.set_state(PaymentStates.waiting_for_partial_amount)
    await callback.message.answer("Qancha summa to'lanmoqda? (Masalan: 50000)")
    await callback.answer()


@shop_router.message(PaymentStates.waiting_for_partial_amount)
async def save_partial_payment(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    raw_amount = message.text.strip().replace(' ', '').replace(',', '')
    if not raw_amount.isdigit():
        return await message.answer("❌ Faqat raqam kiriting! To'lov bekor qilindi.")

    pay_amount = int(raw_amount)
    debt_id = data.get('active_debt_id')

    if not debt_id:
        return await message.answer("⚠️ Xatolik: Qarz ID topilmadi.")

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT amount, customer_id FROM debts WHERE id = %s", (debt_id,))
        res = cursor.fetchone()

        if not res:
            return await message.answer("❌ Qarz topilmadi.")

        current_debt, customer_id = res

        if pay_amount >= current_debt:
            cursor.execute("DELETE FROM debts WHERE id = %s", (debt_id,))
            msg = "✅ Qarz to'liq yopildi va o'chirildi."
        else:
            new_amount = current_debt - pay_amount
            cursor.execute("UPDATE debts SET amount = %s WHERE id = %s", (new_amount, debt_id))
            msg = f"✅ {pay_amount:,} so'm qabul qilindi. Qolgan: {new_amount:,} so'm."

        conn.commit()
        await message.answer(msg, reply_markup=shop_keyboard())

        if customer_id:
            try:
                await message.bot.send_message(customer_id, f"💰 To'lov: {pay_amount:,} so'm.\n{msg}")
            except:
                pass
    finally:
        if conn:
            conn.close()


# ============================================================
# QIDIRISH
# ============================================================

@shop_router.message(F.text == "🔍 Qidirish")
async def universal_search_start(message: Message, state: FSMContext):
    await state.set_state(ShopSearchStates.waiting_for_query)
    await message.answer("🔍 Qidirish uchun mijozning ismi yoki telefon raqamini kiriting:")


@shop_router.message(ShopSearchStates.waiting_for_query)
async def process_universal_search(message: Message, state: FSMContext):
    query = message.text.strip()
    uid = message.from_user.id
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM shops WHERE owner_id = %s", (uid,))
        shop_res = cursor.fetchone()

        if not shop_res:
            return await message.answer("Siz Maskan egasi emassiz.")
        shop_id = shop_res[0]

        # SQLite: LIKE → PostgreSQL: ILIKE (katta-kichik harfga sezgir emas)
        cursor.execute("""
            SELECT customer_name, customer_phone, amount, due_date, status, id
            FROM debts
            WHERE shop_id = %s
            AND (customer_name ILIKE %s OR customer_phone ILIKE %s)
            ORDER BY status DESC
        """, (shop_id, f'%{query}%', f'%{query}%'))

        results = cursor.fetchall()

        if not results:
            await message.answer(f"😔 '{query}' bo'yicha hech qanday ma'lumot topilmadi.")
            await state.clear()
            return

        await message.answer(f"🔎 <b>'{query}'</b> bo'yicha {len(results)} ta natija:", parse_mode="HTML")

        for res in results:
            status_icon = "🔴 To'lanmagan" if res[4] == 'unpaid' else "🟢 To'langan"
            kb = None
            if res[4] == 'unpaid':
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✅ To'liq yopish", callback_data=f"pay_full_{res[5]}"),
                    InlineKeyboardButton(text="📉 Qisman", callback_data=f"pay_part_{res[5]}")
                ]])

            text = (
                f"👤 <b>Mijoz:</b> {res[0]}\n"
                f"📞 <b>Tel:</b> {res[1]}\n"
                f"💰 <b>Summa:</b> {res[2]:,} so'm\n"
                f"📅 <b>Muddat:</b> {res[3]}\n"
                f"📊 <b>Holat:</b> {status_icon}"
            )
            await message.answer(text, reply_markup=kb, parse_mode="HTML")

    finally:
        if conn:
            conn.close()
        await state.clear()


# ============================================================
# E'LON YUBORISH
# ============================================================

@shop_router.message(F.text == "📢 E'lon yuborish")
async def shop_broadcast_start(message: Message, state: FSMContext):
    await state.set_state(ShopBroadcast.waiting_for_message)
    await message.answer("📣 Faqat sizning qarzdorlaringizga yuboriladigan xabar matnini kiriting:")


@shop_router.message(ShopBroadcast.waiting_for_message)
async def process_shop_broadcast(message: Message, state: FSMContext):
    broadcast_text = message.text
    uid = message.from_user.id
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT DISTINCT d.customer_id, s.name
            FROM debts d
            JOIN shops s ON d.shop_id = s.id
            WHERE s.owner_id = %s AND d.customer_id IS NOT NULL AND d.status = 'unpaid'
        """, (uid,))
        customers = cursor.fetchall()

        if not customers:
            await message.answer("Sizda hali botdan ro'yxatdan o'tgan qarzdorlar yo'q.")
            await state.clear()
            return

        shop_name = customers[0][1]
        sent_count = 0
        await message.answer("🚀 Xabar yuborish boshlandi...")

        for customer in customers:
            try:
                target_id = customer[0]
                text = (f"📩 <b>{shop_name} Maskanidan xabar:</b>\n\n{broadcast_text}")
                await message.bot.send_message(target_id, text, parse_mode="HTML")
                sent_count += 1
                await asyncio.sleep(0.05)
            except:
                continue

        await message.answer(f"✅ Xabar {sent_count} ta qarzdoringizga muvaffaqiyatli yuborildi.")
    finally:
        if conn:
            conn.close()
        await state.clear()


# ============================================================
# EXCEL HISOBOT
# ============================================================

@shop_router.message(F.text == "📈 Excel hisobot")
async def export_excel(message: types.Message):
    uid = message.from_user.id
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, name FROM shops WHERE owner_id = %s", (uid,))
        shop = cursor.fetchone()

        if not shop:
            return await message.answer("Siz Maskan egasi emassiz!")

        shop_id, shop_name = shop

        cursor.execute("""
            SELECT customer_name, customer_phone, amount, due_date, status, debt_date
            FROM debts WHERE shop_id = %s
        """, (shop_id,))
        rows = cursor.fetchall()

        if not rows:
            return await message.answer(
                f"❌ <b>{shop_name}</b> Maskanida hali qarz olgan mijozlar mavjud emas.",
                parse_mode="HTML"
            )

        wb = Workbook()
        ws = wb.active
        ws.title = "Qarzlar Hisoboti"
        ws.append(["Mijoz Ismi", "Telefon", "Summa", "Muddat", "Holat", "Yozilgan sana"])

        for row in rows:
            ws.append(list(row))

        excel_file = io.BytesIO()
        wb.save(excel_file)
        excel_file.seek(0)

        document = BufferedInputFile(excel_file.getvalue(), filename=f"{shop_name}_qarzlar.xlsx")
        await message.answer_document(
            document=document,
            caption=f"📊 <b>{shop_name}</b> Maskani uchun to'liq hisobot.",
            parse_mode="HTML"
        )
    finally:
        if conn:
            conn.close()


# ============================================================
# MUDDATI O'TGANLAR
# ============================================================

@shop_router.message(F.text == "🚨 Muddati o'tganlar")
async def show_overdue_debts(message: types.Message):
    uid = message.from_user.id
    conn = None
    today_date = datetime.now().date()
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM shops WHERE owner_id = %s", (uid,))
        shop_res = cursor.fetchone()

        if not shop_res:
            return await message.answer("⚠️ Siz Maskan egasi emassiz!")
        shop_id = shop_res[0]

        cursor.execute("""
            SELECT customer_name, customer_phone, amount, due_date
            FROM debts
            WHERE shop_id = %s AND status = 'unpaid'
        """, (shop_id,))
        all_unpaid = cursor.fetchall()

        overdue_list = []
        for name, phone, amount, d_date in all_unpaid:
            try:
                db_date = datetime.strptime(d_date, "%d.%m.%Y").date()
                if db_date < today_date:
                    overdue_list.append((name, phone, amount, d_date))
            except ValueError:
                continue

        if not overdue_list:
            return await message.answer(
                "✅ <b>Hozircha muddati o'tgan qarzdorlar yo'q.</b>",
                parse_mode="HTML"
            )

        text = "🚨 <b>MUDDATI O'TGAN QARZLAR:</b>\n────────────────────\n"
        total_overdue = 0
        for name, phone, amount, date in overdue_list:
            text += f"👤 <b>{name}</b>\n📞 {phone}\n💰 <b>{amount:,} so'm</b> (Muddat: {date})\n────────────────────\n"
            total_overdue += amount

        text += f"\n🏦 <b>JAMI KECHIKKAN:</b> <u>{total_overdue:,} so'm</u>"
        await message.answer(text, parse_mode="HTML")
    finally:
        if conn:
            conn.close()


# ============================================================
# BOTDAN FOYDALANISH QO'LLANMASI
# ============================================================

@shop_router.message(F.text == "📖 Botdan foydalanish")
async def shop_help_guide(message: Message):
    guide_text = (
        "📖 <b>BOTDAN FOYDALANISH BO'YICHA TO'LIQ QO'LLANMA</b>\n\n"
        "➕ <b>1. Qarz yozish</b>\nYangi qarz kiritish uchun ushbu tugmani bosing. "
        "Mijozning telefon raqamini kiritganingizda, bot avtomatik tarzda bazani tekshiradi.\n\n"
        "💰 <b>2. To'lovni qabul qilish</b>\nMijoz qarzining bir qismini yoki hammasini "
        "to'laganda foydalaniladi.\n\n"
        "🔍 <b>3. Qidirish tizimi</b>\nIsm yoki telefon raqami orqali mijozni toping.\n\n"
        "📊 <b>4. Ro'yxat va Hisobotlar</b>\n"
        "• <b>Qarzlar ro'yxati:</b> Barcha faol qarzdorlar.\n"
        "• <b>Excel hisobot:</b> Ma'lumotlarni Excel formatida yuklab olish.\n\n"
        "📢 <b>5. E'lon yuborish</b>\nBarcha qarzdorlarga bir vaqtda xabar yuborish.\n\n"
        "🔔 <b>6. Avtomatik eslatmalar</b>\nBot har kuni <b>4 marta</b> (09:00, 13:00, "
        "17:00, 21:00) qarzdorlarga eslatma yuboradi.\n\n"
        "🛡 <i>Ma'lumotlaringiz xavfsizligi va maxfiyligi to'liq kafolatlangan!</i>"
    )
    await message.answer(guide_text, parse_mode="HTML")