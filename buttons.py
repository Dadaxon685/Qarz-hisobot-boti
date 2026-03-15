
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

def admin_keyboard():
    buttons = [
        [KeyboardButton(text="🏪 Maskan qo'shish"), KeyboardButton(text="🔍 Maskanni qidirish")],
        [KeyboardButton(text="📝 Maskanlar ro'yxati"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="📢 Reklama yuborish")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)



# def shop_keyboard():
#     buttons = [
#         [KeyboardButton(text="➕ Qarz yozish"), KeyboardButton(text="📊 Qarzlar ro'yxati")],
#         [KeyboardButton(text="🔍 Qidirish"), KeyboardButton(text="💰 To'lovni qabul qilish")],
#         [KeyboardButton(text="📢 E'lon yuborish"), KeyboardButton(text="📊 Excel hisobot")],
#         [KeyboardButton(text="📖 Botdan foydalanish")]
#     ]
#     return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def shop_keyboard():
    buttons = [
        # Birinchi qator: Eng ko'p ishlatiladigan asosiy operatsiyalar
        [
            KeyboardButton(text="➕ Qarz yozish"), 
            KeyboardButton(text="💰 To'lovni qabul qilish")
        ],
        # Ikkinchi qator: Monitoring va nazorat (Tezkor qidiruv va muammoli qarzlar)
        [
            KeyboardButton(text="🔍 Qidirish"), 
            KeyboardButton(text="🚨 Muddati o'tganlar")
        ],
        # Uchinchi qator: Umumiy tahlil (Keng tugma ko'rinishida)
        [
            KeyboardButton(text="📊 Qarzlar umumiy")
        ],
        # To'rtinchi qator: Ma'muriy va hisobot ishlari
        [
            KeyboardButton(text="📈 Excel hisobot"), 
            KeyboardButton(text="📢 E'lon yuborish")
        ],
        # Beshinchi qator: Yordam va yo'riqnoma (Kichikroq va pastda)
        [
            KeyboardButton(text="📖 Botdan foydalanish")
        ]
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons, 
        resize_keyboard=True,
        input_field_placeholder="Kerakli bo'limni tanlang..."
    )