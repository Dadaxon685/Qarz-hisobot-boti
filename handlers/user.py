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


class CheckDebt(StatesGroup):
    waiting_phone = State()

class ShopApply(StatesGroup):
    name = State()
    phone = State()
    address = State()
    confirm = State()

class AddEmployee(StatesGroup):
    waiting_id = State()

class RemoveEmployee(StatesGroup):
    waiting_id = State()


def gen_token(telegram_id: int) -> str:
    return hashlib.sha256(f"{telegram_id}{SECRET_KEY}".encode()).hexdigest()[:16]

def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Qarzlarimni tekshirish", callback_data="check_debt")],
        [InlineKeyboardButton(text="🏪 Do'kon ochish", callback_data="open_shop")],
    ])

def cancel_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True
    )

def shop_panel_kb(uid: int, shop_name: str):
    token = gen_token(uid)
    if USE_WEBAPP:
        url = f"{SHOP_WEB_URL}?token={token}&id={uid}"
        return InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text=f"🏪 {shop_name} — Panelni Ochish", web_app=WebAppInfo(url=url))
        ]])
    return None

def owner_menu_kb():
    """Do'kon egasi uchun menyu"""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👥 Xodimlar"), KeyboardButton(text="➕ Xodim qo'shish")],
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="🌐 Panelni ochish")],
    ], resize_keyboard=True)

def staff_menu_kb():
    """Xodim uchun menyu"""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🌐 Panelni ochish")],
    ], resize_keyboard=True)


# ============================================================
# START
# ============================================================

@user_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    name = message.from_user.full_name

    # 1. SUPER ADMIN
    if uid == SUPER_ADMIN_ID:
        token = gen_token(uid)
        if USE_WEBAPP and ADMIN_WEB_URL.startswith("https"):
            url = f"{ADMIN_WEB_URL}?token={token}&id={uid}"
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="⚙️ Admin Panelni Ochish", web_app=WebAppInfo(url=url))
            ]])
            return await message.answer(
                f"👑 <b>Xush kelibsiz, Boss!</b>",
                reply_markup=kb, parse_mode="HTML"
            )
        return await message.answer(f"👑 <b>Xush kelibsiz, Boss!</b>", parse_mode="HTML")

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 2. DO'KON EGASI
        cursor.execute("SELECT id, name FROM shops WHERE owner_id = %s", (uid,))
        shop = cursor.fetchone()
        if shop:
            shop_id, shop_name = shop
            kb = shop_panel_kb(uid, shop_name)
            text = (
                f"✅ <b>Xush kelibsiz, {name}!</b>\n\n"
                f"🏪 <b>{shop_name}</b> do'koni paneli\n\n"
                f"👥 Xodimlar qo'shish va boshqarish uchun quyidagi menyudan foydalaning:"
            )
            await message.answer(text, reply_markup=owner_menu_kb(), parse_mode="HTML")
            if kb:
                await message.answer("🌐 Web panel:", reply_markup=kb)
            return

        # 3. XODIM
        cursor.execute("""
            SELECT e.shop_id, s.name, e.role
            FROM employees e JOIN shops s ON s.id = e.shop_id
            WHERE e.telegram_id = %s
        """, (uid,))
        emp = cursor.fetchone()
        if emp:
            shop_id, shop_name, role = emp
            # Xodim uchun owner_id o'rniga o'zining ID sini ishlatamiz
            cursor.execute("SELECT owner_id FROM shops WHERE id = %s", (shop_id,))
            owner = cursor.fetchone()
            token = gen_token(owner[0]) if owner else gen_token(uid)

            if USE_WEBAPP:
                url = f"{SHOP_WEB_URL}?token={token}&id={owner[0]}"
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text=f"🏪 {shop_name} — Panelni Ochish", web_app=WebAppInfo(url=url))
                ]])
            else:
                kb = None

            text = (
                f"👷 <b>Xush kelibsiz, {name}!</b>\n\n"
                f"🏪 <b>{shop_name}</b> xodimisiz\n"
                f"📋 Rol: <b>{'Xodim' if role == 'staff' else 'Menejer'}</b>"
            )
            await message.answer(text, reply_markup=staff_menu_kb(), parse_mode="HTML")
            if kb:
                await message.answer("🌐 Web panel:", reply_markup=kb)
            return

        # 4. ODDIY FOYDALANUVCHI
        await message.answer(
            f"👋 <b>Assalomu alaykum, {name}!</b>\n\nQuyidagilardan birini tanlang:",
            reply_markup=main_menu_kb(), parse_mode="HTML"
        )
    finally:
        if conn: conn.close()


# ============================================================
# BEKOR QILISH
# ============================================================

@user_router.message(F.text == "❌ Bekor qilish")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🚫 Bekor qilindi.", reply_markup=ReplyKeyboardRemove())
    await message.answer("Bosh menyu:", reply_markup=main_menu_kb())


# ============================================================
# DO'KON EGASI — XODIMLAR BOSHQARUVI
# ============================================================

@user_router.message(F.text == "👥 Xodimlar")
async def list_employees(message: Message):
    uid = message.from_user.id
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM shops WHERE owner_id = %s", (uid,))
        shop = cursor.fetchone()
        if not shop:
            return await message.answer("❌ Siz do'kon egasi emassiz.")

        cursor.execute("""
            SELECT telegram_id, full_name, role, added_at
            FROM employees WHERE shop_id = %s ORDER BY added_at
        """, (shop[0],))
        employees = cursor.fetchall()

        if not employees:
            return await message.answer(
                "👥 <b>Xodimlar yo'q</b>\n\n"
                "Xodim qo'shish uchun <b>➕ Xodim qo'shish</b> tugmasini bosing.",
                parse_mode="HTML"
            )

        text = "👥 <b>Sizning xodimlaringiz:</b>\n\n"
        for i, (tid, fname, role, added) in enumerate(employees, 1):
            text += f"{i}. {fname or 'Noma\'lum'} — <code>{tid}</code> ({role})\n"

        text += "\n❌ Xodimni o'chirish uchun uning ID sini yuboring yoki bekor yozing."

        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="➕ Xodim qo'shish", callback_data="add_employee"),
            InlineKeyboardButton(text="❌ O'chirish", callback_data="remove_employee"),
        ]])
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
    finally:
        if conn: conn.close()


@user_router.message(F.text == "➕ Xodim qo'shish")
async def add_employee_start(message: Message, state: FSMContext):
    uid = message.from_user.id
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM shops WHERE owner_id = %s", (uid,))
        if not cursor.fetchone():
            return await message.answer("❌ Siz do'kon egasi emassiz.")
    finally:
        if conn: conn.close()

    await state.set_state(AddEmployee.waiting_id)
    await message.answer(
        "➕ <b>Xodim qo'shish</b>\n\n"
        "Xodimning Telegram ID sini yuboring.\n"
        "ID ni bilish uchun xodim @userinfobot ga /start yuborsın.",
        reply_markup=cancel_kb(), parse_mode="HTML"
    )

@user_router.callback_query(F.data == "add_employee")
async def add_employee_cb(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AddEmployee.waiting_id)
    await callback.message.answer(
        "➕ Xodimning Telegram ID sini yuboring:",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@user_router.message(AddEmployee.waiting_id)
async def add_employee_save(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Faqat raqam kiriting!")

    emp_id = int(message.text)
    uid = message.from_user.id

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM shops WHERE owner_id = %s", (uid,))
        shop = cursor.fetchone()
        if not shop:
            return await message.answer("❌ Siz do'kon egasi emassiz.")

        shop_id, shop_name = shop

        # Xodim allaqachon bormi?
        cursor.execute("SELECT id FROM employees WHERE shop_id=%s AND telegram_id=%s", (shop_id, emp_id))
        if cursor.fetchone():
            await state.clear()
            return await message.answer("⚠️ Bu xodim allaqachon qo'shilgan!")

        # Xodim boshqa do'konda ishlaydimi?
        cursor.execute("SELECT s.name FROM employees e JOIN shops s ON s.id=e.shop_id WHERE e.telegram_id=%s", (emp_id,))
        existing = cursor.fetchone()
        if existing:
            await state.clear()
            return await message.answer(f"⚠️ Bu kishi allaqachon <b>{existing[0]}</b> do'konida xodim!", parse_mode="HTML")

        # Xodimni qo'shish
        cursor.execute("""
            INSERT INTO employees (shop_id, telegram_id, full_name, role)
            VALUES (%s, %s, %s, 'staff')
        """, (shop_id, emp_id, f"Xodim {emp_id}"))
        conn.commit()

        await state.clear()
        await message.answer(
            f"✅ <b>Xodim qo'shildi!</b>\n\n"
            f"🆔 ID: <code>{emp_id}</code>\n"
            f"🏪 Do'kon: <b>{shop_name}</b>",
            reply_markup=owner_menu_kb(), parse_mode="HTML"
        )

        # Xodimga xabar
        try:
            await message.bot.send_message(
                chat_id=emp_id,
                text=(
                    f"🎉 <b>Siz xodim sifatida qo'shildingiz!</b>\n\n"
                    f"🏪 Do'kon: <b>{shop_name}</b>\n\n"
                    f"Panelga kirish uchun /start bosing."
                ),
                parse_mode="HTML"
            )
        except: pass

    except Exception as e:
        await message.answer(f"❌ Xato: {e}")
    finally:
        if conn: conn.close()


@user_router.callback_query(F.data == "remove_employee")
async def remove_employee_cb(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(RemoveEmployee.waiting_id)
    await callback.message.answer(
        "❌ O'chirmoqchi bo'lgan xodim ID sini yuboring:",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@user_router.message(RemoveEmployee.waiting_id)
async def remove_employee_save(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Faqat raqam kiriting!")

    emp_id = int(message.text)
    uid = message.from_user.id
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM shops WHERE owner_id=%s", (uid,))
        shop = cursor.fetchone()
        if not shop:
            return await message.answer("❌ Siz do'kon egasi emassiz.")

        cursor.execute("DELETE FROM employees WHERE shop_id=%s AND telegram_id=%s RETURNING id", (shop[0], emp_id))
        deleted = cursor.fetchone()
        conn.commit()
        await state.clear()

        if deleted:
            await message.answer(f"✅ Xodim <code>{emp_id}</code> o'chirildi.", reply_markup=owner_menu_kb(), parse_mode="HTML")
            try:
                await message.bot.send_message(emp_id, "⚠️ Siz do'kon xodimlari ro'yxatidan o'chirildingiz.")
            except: pass
        else:
            await message.answer("⚠️ Bu ID topilmadi.")
    finally:
        if conn: conn.close()


@user_router.message(F.text == "🌐 Panelni ochish")
async def open_panel(message: Message):
    uid = message.from_user.id
    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # Egami yoki xodimmi?
        cursor.execute("SELECT id, name FROM shops WHERE owner_id=%s", (uid,))
        shop = cursor.fetchone()

        if not shop:
            cursor.execute("""
                SELECT s.id, s.name, s.owner_id FROM employees e
                JOIN shops s ON s.id=e.shop_id WHERE e.telegram_id=%s
            """, (uid,))
            row = cursor.fetchone()
            if row:
                shop = (row[0], row[1])
                owner_id = row[2]
            else:
                return await message.answer("❌ Sizga tegishli do'kon topilmadi.")
        else:
            owner_id = uid

        shop_id, shop_name = shop
        token = gen_token(owner_id)

        if USE_WEBAPP:
            url = f"{SHOP_WEB_URL}?token={token}&id={owner_id}"
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text=f"🏪 {shop_name}", web_app=WebAppInfo(url=url))
            ]])
            await message.answer("🌐 Web panel:", reply_markup=kb)
        else:
            await message.answer("⚠️ Web panel hali sozlanmagan.")
    finally:
        if conn: conn.close()


# ============================================================
# QARZNI TEKSHIRISH
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
            await message.answer("✅ <b>Yaxshi xabar!</b>\n\nBu raqamda faol qarz topilmadi.",
                reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
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
    await message.answer("3️⃣ Do'kon joylashuvini kiriting:")

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
    shop_data = {}
    for line in lines:
        if "🏪" in line and "ARIZA" not in line: shop_data['name'] = line.replace("🏪","").strip()
        if "📞" in line: shop_data['phone'] = line.replace("📞","").strip()
        if "📍" in line: shop_data['address'] = line.replace("📍","").strip()

    conn = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO shops (name,owner_id,phone,address) VALUES (%s,%s,%s,%s)",
            (shop_data.get('name','Do\'kon'), uid, shop_data.get('phone',''), shop_data.get('address','')))
        conn.commit()

        token = gen_token(uid)
        if USE_WEBAPP:
            url = f"{SHOP_WEB_URL}?token={token}&id={uid}"
            kb = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🚀 Maskan Panelini Ochish", web_app=WebAppInfo(url=url))
            ]])
        else:
            kb = None

        await callback.bot.send_message(
            chat_id=uid,
            text=f"🎉 <b>Tabriklaymiz!</b>\n\n✅ Do'koningiz tasdiqlandi!\n\nBotda ishlash uchun /start bosing 👇",
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
    await callback.bot.send_message(uid, "😔 Do'kon ochish arizangiz rad etildi.", parse_mode="HTML")
    await callback.message.edit_text(callback.message.text + "\n\n❌ <b>RAD ETILDI</b>", parse_mode="HTML")
    await callback.answer()
