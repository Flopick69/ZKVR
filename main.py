import os
import re
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# Токен твоего бота и ID администратора (замени на свои актуальные данные)
BOT_TOKEN = "ТВОЙ_ТОКЕН_БОТА"
MY_ID = 123456789  # Замени на свой реальный Telegram ID

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Базовые категории с эмодзи для точной синхронизации
DEFAULT_CATS = {
    "🌊": "🌊 Жидкости",
    "🔌": "🔌 Под-системы",
    "⚙️": "⚙️ Расходники / Испарители",
    "⚠️": "⚠️ Снюс"
}

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS brands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            name TEXT,
            UNIQUE(category_id, name)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            brand_id INTEGER,
            name TEXT,
            price INTEGER,
            quantity INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_id INTEGER,
            quantity INTEGER
        )
    """)
    
    # Принудительно создаем базовые категории при первом запуске
    for emoji, cat_full_name in DEFAULT_CATS.items():
        cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat_full_name,))
        
    conn.commit()
    conn.close()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ГЕНЕРАЦИИ ТЕКСТА ---
def generate_stock_text(for_copy=False):
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name FROM categories")
    categories = cursor.fetchall()
    
    text = "❗️ZKVR SHOP❗️\n\n" if for_copy else "📋 Текущая витрина магазина:\n\n"
    
    for cat_id, cat_name in categories:
        cursor.execute("SELECT id, name FROM products WHERE category_id = ?", (cat_id,))
        products = cursor.fetchall()
        
        if not products:
            continue
            
        text += f"{cat_name}:\n"
        
        # Группируем по ценам внутри одной категории для красивого вывода
        prices_dict = {}
        for prod_id, prod_name in products:
            cursor.execute("SELECT price, quantity FROM products WHERE id = ?", (prod_id,))
            p_price, p_qty = cursor.fetchone()
            
            if p_price not in prices_dict:
                prices_dict[p_price] = []
            prices_dict[p_price].append((prod_name, p_qty))
            
        for price, items in prices_dict.items():
            for name, qty in items:
                status_emoji = "✅" if qty > 0 else "❌"
                qty_text = f" — {qty} шт." if qty > 1 else ""
                text += f"{status_emoji}{name}{qty_text}\n"
            text += f"Цена: {price} руб.\n\n"
            
    if for_copy:
        text += "По поводу покупки писать:\n@PornHub_Tag\n⬇️⬇️⬇️⬇️⬇️\nСсылка на канал"
        
    conn.close()
    return text.strip()

# --- ФУНКЦИЯ ДЛЯ СБОРКИ КНОПОК КАТЕГОРИЙ (ДЛЯ СТАРТА И КНОПКИ НАЗАД) ---
def get_categories_markup():
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories")
    categories = cursor.fetchall()
    conn.close()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for cat_id, cat_name in categories:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=cat_name, callback_data=f"cat_{cat_id}")])
    return keyboard

# --- КЛАВИАТУРЫ (РЕПЛАЙ) ---
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Начать покупки")],
            [KeyboardButton(text="📦 Мои брони"), KeyboardButton(text="ℹ️ О нас")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_admin_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Посмотреть остатки"), KeyboardButton(text="📋 Скопировать прайс")]
        ],
        resize_keyboard=True
    )
    return keyboard


# --- ОБРАБОТЧИКИ ДЛЯ КЛИЕНТОВ ---

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user.id == MY_ID:
        await message.answer("👋 Привет, Админ! Твоя панель управления готова.", reply_markup=get_admin_main_keyboard())
    else:
        # Сразу выдаем старый визуал: красивое приветствие и Inline-кнопки под ним
        await message.answer(
            f"Привет, {message.from_user.first_name}! 👋\nВыбери интересующую тебя категорию товаров ниже:", 
            reply_markup=get_categories_markup()
        )
        # Также обновляем обычную нижнюю клавиатуру, чтобы она была доступна
        await message.answer("Или воспользуйся меню:", reply_markup=get_main_keyboard())

@dp.message(F.text == "🛒 Начать покупки")
async def show_categories(message: Message):
    # При клике на кнопку «Начать покупки» выдаем то же меню с категориями
    await message.answer(
        "Выбери интересующую тебя категорию товаров ниже:", 
        reply_markup=get_categories_markup()
    )

@dp.callback_query(F.data.startswith("cat_"))
async def show_brands(callback: CallbackQuery):
    cat_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    
    # Показываем только те бренды, у которых есть товары в наличии
    cursor.execute("SELECT DISTINCT b.id, b.name FROM brands b JOIN products p ON b.id = p.brand_id WHERE p.category_id = ? AND p.quantity > 0", (cat_id,))
    brands = cursor.fetchall()
    conn.close()
    
    if not brands:
        await callback.answer("😔 В этой категории пока ничего нет в наличии!", show_alert=True)
        return
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for brand_id, brand_name in brands:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=brand_name, callback_data=f"brand_{cat_id}_{brand_id}")])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад к категориям", callback_data="back_to_cats")])
    
    await callback.message.edit_text("🔥 Выберите бренд/линейку:", reply_markup=keyboard)

@dp.callback_query(F.data == "back_to_cats")
async def back_to_categories_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выбери интересующую тебя категорию товаров ниже:", 
        reply_markup=get_categories_markup()
    )

@dp.callback_query(F.data.startswith("brand_"))
async def show_products_by_brand(callback: CallbackQuery):
    data = callback.data.split("_")
    cat_id = int(data[1])
    brand_id = int(data[2])
    
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, quantity FROM products WHERE category_id = ? AND brand_id = ? AND quantity > 0", (cat_id, brand_id))
    products = cursor.fetchall()
    conn.close()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for prod_id, name, price, qty in products:
        btn_text = f"{name} — {price}₽ ({qty} шт)"
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"prod_{prod_id}")])
        
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад к брендам", callback_data=f"cat_{cat_id}")])
    await callback.message.edit_text("⚡️ Выберите конкретную позицию:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("prod_"))
async def show_product_card(callback: CallbackQuery):
    prod_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, quantity, category_id FROM products WHERE id = ?", (prod_id,))
    product = cursor.fetchone()
    conn.close()
    
    if not product or product[2] <= 0:
        await callback.answer("❌ Товар только что закончился!", show_alert=True)
        return
        
    name, price, qty, cat_id = product
    text = f"📦 *{name}*\n\n💰 Цена: {price} руб.\n🔹 В наличии: {qty} шт.\n\n Нажмите кнопку ниже, чтобы забронировать товар."
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔒 Забронировать 1 шт.", callback_data=f"book_{prod_id}")],
        [InlineKeyboardButton(text="🔙 Назад к списку", callback_data=f"back_to_brand_{prod_id}")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("back_to_brand_"))
async def back_to_brand(callback: CallbackQuery):
    prod_id = int(callback.data.split("_")[3])
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT category_id, brand_id FROM products WHERE id = ?", (prod_id,))
    res = cursor.fetchone()
    conn.close()
    if res:
        callback.data = f"brand_{res[0]}_{res[1]}"
        await show_products_by_brand(callback)

@dp.callback_query(F.data.startswith("book_"))
async def process_booking(callback: CallbackQuery):
    prod_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT name, price, quantity FROM products WHERE id = ?", (prod_id,))
    product = cursor.fetchone()
    
    if not product or product[2] <= 0:
        await callback.answer("❌ Извините, товар закончился!", show_alert=True)
        conn.close()
        return
        
    name, price, current_qty = product
    
    # Снижаем остаток у товара и добавляем в бронь
    cursor.execute("UPDATE products SET quantity = quantity - 1 WHERE id = ?", (prod_id,))
    cursor.execute("INSERT INTO bookings (user_id, product_id, quantity) VALUES (?, ?, 1)", (user_id, prod_id))
    conn.commit()
    conn.close()
    
    success_text = f"🎉 *Товар успешно забронирован!*\n\nПозиция: {name}\nСумма к оплате: {price} руб.\n\n📱 Для покупки и встречи напишите администратору:\n@PornHub_Tag"
    await callback.message.edit_text(success_text, parse_mode="Markdown")

@dp.message(F.text == "📦 Мои брони")
async def show_user_bookings(message: Message):
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.id, p.name, p.price 
        FROM bookings b 
        JOIN products p ON b.product_id = p.id 
        WHERE b.user_id = ?
    """, (message.from_user.id,))
    my_books = cursor.fetchall()
    conn.close()
    
    if not my_books:
        await message.answer("🔒 У вас пока нет активных броней.")
        return
        
    text = "📦 Ваши текущие брони:\n\n"
    total = 0
    for b_id, p_name, price in my_books:
        text += f"• {p_name} — {price} руб.\n"
        total += price
    text += f"\n💰 Итого к оплате: *{total} руб.*\n\nДля выкупа свяжитесь с @PornHub_Tag"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "ℹ️ О нас")
async def cmd_about(message: Message):
    await message.answer("🏪 *ZKVR SHOP*\n\nБыстрая выдача, оригинальный товар.\nПо всем вопросам: @PornHub_Tag", parse_mode="Markdown")


# --- АДМИН-ПАНЕЛЬ (УПРАВЛЕНИЕ И УМНЫЙ ПАРСИНГ) ---

@dp.message(F.chat.id == MY_ID, F.text == "📊 Посмотреть остатки")
async def admin_view_stock(message: Message):
    stock_info = generate_stock_text(for_copy=False)
    await message.answer(stock_info)

@dp.message(F.chat.id == MY_ID, F.text == "📋 Скопировать прайс")
async def admin_copy_stock(message: Message):
    stock_info = generate_stock_text(for_copy=True)
    await message.answer(f"```{stock_info}```", parse_mode="MarkdownV2")

@dp.message(F.chat.id == MY_ID, Command("clear"))
async def clear_database(message: Message):
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products")
    cursor.execute("DELETE FROM brands")
    cursor.execute("DELETE FROM bookings")
    conn.commit()
    conn.close()
    await message.answer("🧹 База данных полностью очищена (кроме структуры категорий). Можешь заливать новый прайс!")

# --- СВЕРХНАДЕЖНЫЙ УМНЫЙ ПАРСЕР ПРАЙСА ПО ЭМОДЗИ ---
@dp.message(F.chat.id == MY_ID, Command("update"))
async def update_assortment(message: Message):
    raw_text = message.text.replace("/update", "").strip()
    if not raw_text:
        await message.answer("❌ Пришли прайс-лист после команды `/update`!")
        return
    
    lines = raw_text.split("\n")
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    
    # Очищаем старый ассортимент
    cursor.execute("DELETE FROM products")
    cursor.execute("DELETE FROM brands")
    cursor.execute("DELETE FROM bookings")
    
    # Принудительно гарантируем корректные названия категорий
    for emoji, cat_full_name in DEFAULT_CATS.items():
        cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat_full_name,))
    
    added_count = 0
    
    # Дефолтная начальная категория — Жидкости
    cursor.execute("SELECT id FROM categories WHERE name = ?", ("🌊 Жидкости",))
    current_cat_id = cursor.fetchone()[0]
    
    temp_products = []
    current_block_price = None
    
    for line in lines:
        try:
            line = line.strip()
            if not line: continue
            line_lower = line.lower()
            
            # 1. Смена категории ПО ЭМОДЗИ (самый стабильный метод)
            cat_changed = False
            for emoji, cat_full_name in DEFAULT_CATS.items():
                if emoji in line and "цена" not in line_lower and not line.startswith("✅") and not line.startswith("❌"):
                    cursor.execute("SELECT id FROM categories WHERE name = ?", (cat_full_name,))
                    current_cat_id = cursor.fetchone()[0]
                    cat_changed = True
                    current_block_price = None # Сбрасываем цену для новой категории
                    break
            if cat_changed: continue
            
            # 2. Если парсер встретил строку цены
            price_match = re.search(r'(?:цена|Цена):\s*(\d+)', line)
            if price_match:
                current_block_price = int(price_match.group(1))
                # Заполняем цену всем позициям текущей категории, у которых её ещё нет
                for prod in temp_products:
                    if prod['cat_id'] == current_cat_id and prod['price'] is None:
                        prod['price'] = current_block_price
                continue
                
            # 3. Парсинг конкретного товара
            if line.startswith("✅") or line.startswith("❌"):
                is_available = line.startswith("✅")
                clean_line = line[1:].strip()
                
                # Обрезаем сложные внутренние пояснения в скобках, чтобы не путать регулярку шт.
                clean_line_before_brackets = clean_line.split("(")[0].strip()
                qty_match = re.search(r'[-—]\s*(\d+)\s*шт', clean_line_before_brackets) or re.search(r'(\d+)\s*шт', clean_line_before_brackets)
                
                if qty_match:
                    quantity = int(qty_match.group(1))
                    full_name = clean_line[:qty_match.start()].strip()
                    full_name = full_name.rstrip("-— ").strip()
                else:
                    quantity = 1 if is_available else 0
                    full_name = clean_line
                    
                if not is_available: quantity = 0
                
                # Вычленяем имя бренда/производителя для кнопок интерфейса
                if " — " in full_name:
                    brand_name = full_name.split(" — ", 1)[0].strip()
                elif " - " in full_name:
                    brand_name = full_name.split(" - ", 1)[0].strip()
                elif " x " in full_name:
                    brand_name = full_name.split(" x ", 1)[0].strip()
                else:
                    brand_name = full_name.split(" ")[0].strip() if " " in full_name else "Разное"
                    
                temp_products.append({
                    'cat_id': current_cat_id,
                    'brand_name': brand_name,
                    'full_name': full_name,
                    'price': current_block_price,
                    'quantity': quantity
                })
        except Exception as line_error:
            print(f"Ошибка парсинга строки '{line}': {line_error}")
            continue

    # Сохраняем распарсенные товары в базу с проверкой дефолтных цен
    for prod in temp_products:
        try:
            # Предохранитель на случай, если в блоке забыли написать цену
            if prod['price'] is None:
                cursor.execute("SELECT name FROM categories WHERE id = ?", (prod['cat_id'],))
                cat_name_db = cursor.fetchone()[0]
                if "Под-системы" in cat_name_db:
                    final_price = 500
                elif "Расходники" in cat_name_db:
                    final_price = 300
                else:
                    final_price = 450
            else:
                final_price = prod['price']
                
            cursor.execute("INSERT OR IGNORE INTO brands (category_id, name) VALUES (?, ?)", (prod['cat_id'], prod['brand_name']))
            cursor.execute("SELECT id FROM brands WHERE category_id = ? AND name = ?", (prod['cat_id'], prod['brand_name']))
            brand_id = cursor.fetchone()[0]
            
            cursor.execute(
                "INSERT OR REPLACE INTO products (category_id, brand_id, name, price, quantity) VALUES (?, ?, ?, ?, ?)",
                (prod['cat_id'], brand_id, prod['full_name'], final_price, prod['quantity'])
            )
            added_count += 1
        except Exception as save_error:
            print(f"Ошибка保存товара {prod['full_name']}: {save_error}")
            continue
            
    try:
        conn.commit()
        await message.answer(f"✅ Успешно обновлено позиций в базе: {added_count}")
        await message.answer(generate_stock_text(for_copy=False), reply_markup=get_admin_main_keyboard())
    except Exception as e: 
        await message.answer(f"❌ Ошибка фиксации БД: {e}")
    finally: 
        conn.close()

# --- ЗАПУСК БОТА ---
if __name__ == "__main__":
    init_db()
    print("Бот успешно запущен!")
    dp.run_polling(bot)import os
import re
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# Токен твоего бота и ID администратора (замени на свои актуальные данные)
BOT_TOKEN = "ТВОЙ_ТОКЕН_БОТА"
MY_ID = 123456789  # Замени на свой реальный Telegram ID

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Базовые категории с эмодзи для точной синхронизации
DEFAULT_CATS = {
    "🌊": "🌊 Жидкости",
    "🔌": "🔌 Под-системы",
    "⚙️": "⚙️ Расходники / Испарители",
    "⚠️": "⚠️ Снюс"
}

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS brands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            name TEXT,
            UNIQUE(category_id, name)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            brand_id INTEGER,
            name TEXT,
            price INTEGER,
            quantity INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_id INTEGER,
            quantity INTEGER
        )
    """)
    
    # Принудительно создаем базовые категории при первом запуске
    for emoji, cat_full_name in DEFAULT_CATS.items():
        cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat_full_name,))
        
    conn.commit()
    conn.close()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ГЕНЕРАЦИИ ТЕКСТА ---
def generate_stock_text(for_copy=False):
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, name FROM categories")
    categories = cursor.fetchall()
    
    text = "❗️ZKVR SHOP❗️\n\n" if for_copy else "📋 Текущая витрина магазина:\n\n"
    
    for cat_id, cat_name in categories:
        cursor.execute("SELECT id, name FROM products WHERE category_id = ?", (cat_id,))
        products = cursor.fetchall()
        
        if not products:
            continue
            
        text += f"{cat_name}:\n"
        
        # Группируем по ценам внутри одной категории для красивого вывода
        prices_dict = {}
        for prod_id, prod_name in products:
            cursor.execute("SELECT price, quantity FROM products WHERE id = ?", (prod_id,))
            p_price, p_qty = cursor.fetchone()
            
            if p_price not in prices_dict:
                prices_dict[p_price] = []
            prices_dict[p_price].append((prod_name, p_qty))
            
        for price, items in prices_dict.items():
            for name, qty in items:
                status_emoji = "✅" if qty > 0 else "❌"
                qty_text = f" — {qty} шт." if qty > 1 else ""
                text += f"{status_emoji}{name}{qty_text}\n"
            text += f"Цена: {price} руб.\n\n"
            
    if for_copy:
        text += "По поводу покупки писать:\n@PornHub_Tag\n⬇️⬇️⬇️⬇️⬇️\nСсылка на канал"
        
    conn.close()
    return text.strip()

# --- ФУНКЦИЯ ДЛЯ СБОРКИ КНОПОК КАТЕГОРИЙ (ДЛЯ СТАРТА И КНОПКИ НАЗАД) ---
def get_categories_markup():
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories")
    categories = cursor.fetchall()
    conn.close()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for cat_id, cat_name in categories:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=cat_name, callback_data=f"cat_{cat_id}")])
    return keyboard

# --- КЛАВИАТУРЫ (РЕПЛАЙ) ---
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Начать покупки")],
            [KeyboardButton(text="📦 Мои брони"), KeyboardButton(text="ℹ️ О нас")]
        ],
        resize_keyboard=True
    )
    return keyboard

def get_admin_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Посмотреть остатки"), KeyboardButton(text="📋 Скопировать прайс")]
        ],
        resize_keyboard=True
    )
    return keyboard


# --- ОБРАБОТЧИКИ ДЛЯ КЛИЕНТОВ ---

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user.id == MY_ID:
        await message.answer("👋 Привет, Админ! Твоя панель управления готова.", reply_markup=get_admin_main_keyboard())
    else:
        # Сразу выдаем старый визуал: красивое приветствие и Inline-кнопки под ним
        await message.answer(
            f"Привет, {message.from_user.first_name}! 👋\nВыбери интересующую тебя категорию товаров ниже:", 
            reply_markup=get_categories_markup()
        )
        # Также обновляем обычную нижнюю клавиатуру, чтобы она была доступна
        await message.answer("Или воспользуйся меню:", reply_markup=get_main_keyboard())

@dp.message(F.text == "🛒 Начать покупки")
async def show_categories(message: Message):
    # При клике на кнопку «Начать покупки» выдаем то же меню с категориями
    await message.answer(
        "Выбери интересующую тебя категорию товаров ниже:", 
        reply_markup=get_categories_markup()
    )

@dp.callback_query(F.data.startswith("cat_"))
async def show_brands(callback: CallbackQuery):
    cat_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    
    # Показываем только те бренды, у которых есть товары в наличии
    cursor.execute("SELECT DISTINCT b.id, b.name FROM brands b JOIN products p ON b.id = p.brand_id WHERE p.category_id = ? AND p.quantity > 0", (cat_id,))
    brands = cursor.fetchall()
    conn.close()
    
    if not brands:
        await callback.answer("😔 В этой категории пока ничего нет в наличии!", show_alert=True)
        return
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for brand_id, brand_name in brands:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=brand_name, callback_data=f"brand_{cat_id}_{brand_id}")])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад к категориям", callback_data="back_to_cats")])
    
    await callback.message.edit_text("🔥 Выберите бренд/линейку:", reply_markup=keyboard)

@dp.callback_query(F.data == "back_to_cats")
async def back_to_categories_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выбери интересующую тебя категорию товаров ниже:", 
        reply_markup=get_categories_markup()
    )

@dp.callback_query(F.data.startswith("brand_"))
async def show_products_by_brand(callback: CallbackQuery):
    data = callback.data.split("_")
    cat_id = int(data[1])
    brand_id = int(data[2])
    
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, quantity FROM products WHERE category_id = ? AND brand_id = ? AND quantity > 0", (cat_id, brand_id))
    products = cursor.fetchall()
    conn.close()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for prod_id, name, price, qty in products:
        btn_text = f"{name} — {price}₽ ({qty} шт)"
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"prod_{prod_id}")])
        
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔙 Назад к брендам", callback_data=f"cat_{cat_id}")])
    await callback.message.edit_text("⚡️ Выберите конкретную позицию:", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("prod_"))
async def show_product_card(callback: CallbackQuery):
    prod_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, quantity, category_id FROM products WHERE id = ?", (prod_id,))
    product = cursor.fetchone()
    conn.close()
    
    if not product or product[2] <= 0:
        await callback.answer("❌ Товар только что закончился!", show_alert=True)
        return
        
    name, price, qty, cat_id = product
    text = f"📦 *{name}*\n\n💰 Цена: {price} руб.\n🔹 В наличии: {qty} шт.\n\n Нажмите кнопку ниже, чтобы забронировать товар."
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔒 Забронировать 1 шт.", callback_data=f"book_{prod_id}")],
        [InlineKeyboardButton(text="🔙 Назад к списку", callback_data=f"back_to_brand_{prod_id}")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("back_to_brand_"))
async def back_to_brand(callback: CallbackQuery):
    prod_id = int(callback.data.split("_")[3])
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT category_id, brand_id FROM products WHERE id = ?", (prod_id,))
    res = cursor.fetchone()
    conn.close()
    if res:
        callback.data = f"brand_{res[0]}_{res[1]}"
        await show_products_by_brand(callback)

@dp.callback_query(F.data.startswith("book_"))
async def process_booking(callback: CallbackQuery):
    prod_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    
    cursor.execute("SELECT name, price, quantity FROM products WHERE id = ?", (prod_id,))
    product = cursor.fetchone()
    
    if not product or product[2] <= 0:
        await callback.answer("❌ Извините, товар закончился!", show_alert=True)
        conn.close()
        return
        
    name, price, current_qty = product
    
    # Снижаем остаток у товара и добавляем в бронь
    cursor.execute("UPDATE products SET quantity = quantity - 1 WHERE id = ?", (prod_id,))
    cursor.execute("INSERT INTO bookings (user_id, product_id, quantity) VALUES (?, ?, 1)", (user_id, prod_id))
    conn.commit()
    conn.close()
    
    success_text = f"🎉 *Товар успешно забронирован!*\n\nПозиция: {name}\nСумма к оплате: {price} руб.\n\n📱 Для покупки и встречи напишите администратору:\n@PornHub_Tag"
    await callback.message.edit_text(success_text, parse_mode="Markdown")

@dp.message(F.text == "📦 Мои брони")
async def show_user_bookings(message: Message):
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT b.id, p.name, p.price 
        FROM bookings b 
        JOIN products p ON b.product_id = p.id 
        WHERE b.user_id = ?
    """, (message.from_user.id,))
    my_books = cursor.fetchall()
    conn.close()
    
    if not my_books:
        await message.answer("🔒 У вас пока нет активных броней.")
        return
        
    text = "📦 Ваши текущие брони:\n\n"
    total = 0
    for b_id, p_name, price in my_books:
        text += f"• {p_name} — {price} руб.\n"
        total += price
    text += f"\n💰 Итого к оплате: *{total} руб.*\n\nДля выкупа свяжитесь с @PornHub_Tag"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "ℹ️ О нас")
async def cmd_about(message: Message):
    await message.answer("🏪 *ZKVR SHOP*\n\nБыстрая выдача, оригинальный товар.\nПо всем вопросам: @PornHub_Tag", parse_mode="Markdown")


# --- АДМИН-ПАНЕЛЬ (УПРАВЛЕНИЕ И УМНЫЙ ПАРСИНГ) ---

@dp.message(F.chat.id == MY_ID, F.text == "📊 Посмотреть остатки")
async def admin_view_stock(message: Message):
    stock_info = generate_stock_text(for_copy=False)
    await message.answer(stock_info)

@dp.message(F.chat.id == MY_ID, F.text == "📋 Скопировать прайс")
async def admin_copy_stock(message: Message):
    stock_info = generate_stock_text(for_copy=True)
    await message.answer(f"```{stock_info}```", parse_mode="MarkdownV2")

@dp.message(F.chat.id == MY_ID, Command("clear"))
async def clear_database(message: Message):
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products")
    cursor.execute("DELETE FROM brands")
    cursor.execute("DELETE FROM bookings")
    conn.commit()
    conn.close()
    await message.answer("🧹 База данных полностью очищена (кроме структуры категорий). Можешь заливать новый прайс!")

# --- СВЕРХНАДЕЖНЫЙ УМНЫЙ ПАРСЕР ПРАЙСА ПО ЭМОДЗИ ---
@dp.message(F.chat.id == MY_ID, Command("update"))
async def update_assortment(message: Message):
    raw_text = message.text.replace("/update", "").strip()
    if not raw_text:
        await message.answer("❌ Пришли прайс-лист после команды `/update`!")
        return
    
    lines = raw_text.split("\n")
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    
    # Очищаем старый ассортимент
    cursor.execute("DELETE FROM products")
    cursor.execute("DELETE FROM brands")
    cursor.execute("DELETE FROM bookings")
    
    # Принудительно гарантируем корректные названия категорий
    for emoji, cat_full_name in DEFAULT_CATS.items():
        cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat_full_name,))
    
    added_count = 0
    
    # Дефолтная начальная категория — Жидкости
    cursor.execute("SELECT id FROM categories WHERE name = ?", ("🌊 Жидкости",))
    current_cat_id = cursor.fetchone()[0]
    
    temp_products = []
    current_block_price = None
    
    for line in lines:
        try:
            line = line.strip()
            if not line: continue
            line_lower = line.lower()
            
            # 1. Смена категории ПО ЭМОДЗИ (самый стабильный метод)
            cat_changed = False
            for emoji, cat_full_name in DEFAULT_CATS.items():
                if emoji in line and "цена" not in line_lower and not line.startswith("✅") and not line.startswith("❌"):
                    cursor.execute("SELECT id FROM categories WHERE name = ?", (cat_full_name,))
                    current_cat_id = cursor.fetchone()[0]
                    cat_changed = True
                    current_block_price = None # Сбрасываем цену для новой категории
                    break
            if cat_changed: continue
            
            # 2. Если парсер встретил строку цены
            price_match = re.search(r'(?:цена|Цена):\s*(\d+)', line)
            if price_match:
                current_block_price = int(price_match.group(1))
                # Заполняем цену всем позициям текущей категории, у которых её ещё нет
                for prod in temp_products:
                    if prod['cat_id'] == current_cat_id and prod['price'] is None:
                        prod['price'] = current_block_price
                continue
                
            # 3. Парсинг конкретного товара
            if line.startswith("✅") or line.startswith("❌"):
                is_available = line.startswith("✅")
                clean_line = line[1:].strip()
                
                # Обрезаем сложные внутренние пояснения в скобках, чтобы не путать регулярку шт.
                clean_line_before_brackets = clean_line.split("(")[0].strip()
                qty_match = re.search(r'[-—]\s*(\d+)\s*шт', clean_line_before_brackets) or re.search(r'(\d+)\s*шт', clean_line_before_brackets)
                
                if qty_match:
                    quantity = int(qty_match.group(1))
                    full_name = clean_line[:qty_match.start()].strip()
                    full_name = full_name.rstrip("-— ").strip()
                else:
                    quantity = 1 if is_available else 0
                    full_name = clean_line
                    
                if not is_available: quantity = 0
                
                # Вычленяем имя бренда/производителя для кнопок интерфейса
                if " — " in full_name:
                    brand_name = full_name.split(" — ", 1)[0].strip()
                elif " - " in full_name:
                    brand_name = full_name.split(" - ", 1)[0].strip()
                elif " x " in full_name:
                    brand_name = full_name.split(" x ", 1)[0].strip()
                else:
                    brand_name = full_name.split(" ")[0].strip() if " " in full_name else "Разное"
                    
                temp_products.append({
                    'cat_id': current_cat_id,
                    'brand_name': brand_name,
                    'full_name': full_name,
                    'price': current_block_price,
                    'quantity': quantity
                })
        except Exception as line_error:
            print(f"Ошибка парсинга строки '{line}': {line_error}")
            continue

    # Сохраняем распарсенные товары в базу с проверкой дефолтных цен
    for prod in temp_products:
        try:
            # Предохранитель на случай, если в блоке забыли написать цену
            if prod['price'] is None:
                cursor.execute("SELECT name FROM categories WHERE id = ?", (prod['cat_id'],))
                cat_name_db = cursor.fetchone()[0]
                if "Под-системы" in cat_name_db:
                    final_price = 500
                elif "Расходники" in cat_name_db:
                    final_price = 300
                else:
                    final_price = 450
            else:
                final_price = prod['price']
                
            cursor.execute("INSERT OR IGNORE INTO brands (category_id, name) VALUES (?, ?)", (prod['cat_id'], prod['brand_name']))
            cursor.execute("SELECT id FROM brands WHERE category_id = ? AND name = ?", (prod['cat_id'], prod['brand_name']))
            brand_id = cursor.fetchone()[0]
            
            cursor.execute(
                "INSERT OR REPLACE INTO products (category_id, brand_id, name, price, quantity) VALUES (?, ?, ?, ?, ?)",
                (prod['cat_id'], brand_id, prod['full_name'], final_price, prod['quantity'])
            )
            added_count += 1
        except Exception as save_error:
            print(f"Ошибка保存товара {prod['full_name']}: {save_error}")
            continue
            
    try:
        conn.commit()
        await message.answer(f"✅ Успешно обновлено позиций в базе: {added_count}")
        await message.answer(generate_stock_text(for_copy=False), reply_markup=get_admin_main_keyboard())
    except Exception as e: 
        await message.answer(f"❌ Ошибка фиксации БД: {e}")
    finally: 
        conn.close()

# --- ЗАПУСК БОТА ---
if __name__ == "__main__":
    init_db()
    print("Бот успешно запущен!")
    dp.run_polling(bot)
