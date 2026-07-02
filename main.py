import asyncio
import logging
import sqlite3
import os
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

logging.basicConfig(level=logging.INFO)

# --- ТВОИ ДАННЫЕ ---
BOT_TOKEN = "8940239980:AAH1u8qqQo9MtSpv4KHLlRcr6ckm3s3_ZQI"
ADMIN_ID = 8344626747  

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'shop.db')

class ShopStates(StatesGroup):
    waiting_for_age = State()
    waiting_for_inventory = State()
    waiting_for_ban_id = State()
    waiting_for_unban_id = State()

# --- МИДЛВАРЬ ДЛЯ ПРОВЕРКИ БАНА И СБОРА ЮЗЕРОВ ---
@dp.message.outer_middleware()
async def user_tracking_middleware(handler, event: Message, data: dict):
    user = event.from_user
    if not user:
        return await handler(event, data)
        
    username = f"@{user.username}" if user.username else "Нет юзернейма"
    full_name = user.full_name
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Проверяем, существует ли юзер
    cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (user.id,))
    res = cursor.fetchone()
    
    if res is None:
        # Если новый пользователь — сохраняем со всеми данными
        cursor.execute('''
            INSERT INTO users (user_id, username, full_name, created_at, is_adult, is_banned)
            VALUES (?, ?, ?, ?, 0, 0)
        ''', (user.id, username, full_name, now_str))
        conn.commit()
        is_banned = 0
    else:
        is_banned = res[0]
        # Обновляем юзернейм и имя на случай, если пользователь их изменил
        cursor.execute('UPDATE users SET username = ?, full_name = ? WHERE user_id = ?', (username, full_name, user.id))
        conn.commit()
        
    conn.close()
    
    if is_banned == 1 and int(user.id) != int(str(ADMIN_ID).strip()):
        await event.answer("🚫 <b>Доступ заблокирован.</b> Вы были забанены администратором.", parse_mode="HTML")
        return # Останавливаем обработку, код дальше не идет
        
    return await handler(event, data)

@dp.callback_query.outer_middleware()
async def user_tracking_callback_middleware(handler, event: CallbackQuery, data: dict):
    user = event.from_user
    if not user:
        return await handler(event, data)
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (user.id,))
    res = cursor.fetchone()
    conn.close()
    
    if res and res[0] == 1 and int(user.id) != int(str(ADMIN_ID).strip()):
        await event.answer("🚫 Вы забанены!", show_alert=True)
        return
        
    return await handler(event, data)

# --- ФУНКЦИЯ ПАРСЕРА НАЛИЧИЯ ---
def parse_inventory(text: str) -> list:
    lines = text.split('\n')
    price_regex = re.compile(r'(?:Цена|Стоимость)\s*:\s*(\d+)\s*(?:руб|р)?', re.IGNORECASE)
    
    blocks = []
    current_block = {"category": None, "lines": []}
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if "💧" in line or "Жидкости" in line:
            if current_block["lines"]: blocks.append(current_block)
            current_block = {"category": "liquids", "lines": []}
            continue
        elif "🔌" in line or "Под-системы" in line:
            if current_block["lines"]: blocks.append(current_block)
            current_block = {"category": "pods", "lines": []}
            continue
        elif "⚙️" in line or "Расходники" in line or "Испарители" in line:
            if current_block["lines"]: blocks.append(current_block)
            current_block = {"category": "consumables", "lines": []}
            continue
        elif "⚠️" in line or "Снюс" in line:
            if current_block["lines"]: blocks.append(current_block)
            current_block = {"category": "snus", "lines": []}
            continue
        elif "❗️" in line or "По покупке" in line or "Ссылка" in line:
            continue
            
        if current_block["category"]:
            current_block["lines"].append(line)
            
    if current_block["lines"]:
        blocks.append(current_block)

    items = []
    for block in blocks:
        cat = block["category"]
        block_lines = block["lines"]
        temp_items = []
        local_price = None
        
        for line in block_lines:
            price_match = price_regex.search(line)
            if price_match:
                local_price = int(price_match.group(1))
                for t_item in temp_items:
                    if t_item["price"] is None:
                        t_item["price"] = local_price
                continue
                
            if line.startswith("✅"):
                clean_line = line.replace("✅", "").strip()
                count = 1
                count_match = re.search(r'—\s*(\d+)\s*шт', clean_line)
                if count_match:
                    count = int(count_match.group(1))
                    clean_line = re.sub(r'—\s*\d+\s*шт\.?', '', clean_line).strip()
                
                brand = "Разное"
                name = clean_line
                
                if cat in ["liquids", "pods"]:
                    if "—" in clean_line:
                        parts = clean_line.split("—", 1)
                        brand = parts[0].strip()
                        name = parts[1].strip()
                    else:
                        parts = clean_line.split(" ", 1)
                        brand = parts[0].strip()
                        name = parts[1].strip() if len(parts) > 1 else parts[0].strip()
                elif cat == "consumables":
                    if "Испаритель" in clean_line:
                        brand = "Испарители"
                    elif "Картридж" in clean_line:
                        brand = "Картриджи"
                elif cat == "snus":
                    if "—" in clean_line:
                        parts = clean_line.split("—", 1)
                        brand = parts[0].strip()
                        name = parts[1].strip()
                
                temp_items.append({
                    "category": cat,
                    "brand": brand,
                    "name": name,
                    "price": local_price,
                    "count": count
                })
        
        for t_item in temp_items:
            if t_item["price"] is None:
                t_item["price"] = local_price if local_price else 0
            items.append(t_item)

    return items

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            brand TEXT,
            name TEXT,
            price INTEGER,
            count INTEGER
        )
    ''')
    
    # Обновляем таблицу пользователей с поддержкой сбора статистики и банов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            created_at TEXT,
            is_adult INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0
        )
    ''')
    
    # Миграция старых БД (добавление колонок, если их не было)
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    if "username" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN username TEXT")
    if "full_name" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
    if "created_at" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
    if "is_banned" not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN is_banned INTEGER DEFAULT 0")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cart (
            user_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            PRIMARY KEY (user_id, product_id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ БД ---
def check_user_adult(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT is_adult FROM users WHERE user_id = ?', (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res and res[0] == 1

def set_user_adult(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_adult = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def get_main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💧 Жидкости", callback_data="showcat_liquids")],
        [InlineKeyboardButton(text="🔌 Под-системы", callback_data="showcat_pods")],
        [InlineKeyboardButton(text="⚙️ Расходники", callback_data="showcat_consumables")],
        [InlineKeyboardButton(text="⚠️ Снюс", callback_data="showcat_snus")],
        [InlineKeyboardButton(text="🛒 Корзина", callback_data="view_cart")]
    ])

def get_admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить наличие (Текст)", callback_data="admin_update")],
        [InlineKeyboardButton(text="📋 Посмотреть остатки", callback_data="admin_stock")],
        [InlineKeyboardButton(text="📉 Списать товар (-1 шт)", callback_data="admin_decrease_select_cat")],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_users_list")],
        [InlineKeyboardButton(text="🚫 Управление баном", callback_data="admin_ban_menu")]
    ])

# --- ХЕНДЛЕРЫ СТАРТА И ПРОВЕРКИ ВОЗРАСТА ---
@dp.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if check_user_adult(user_id):
        await message.answer("❗️ZKVR SHOP❗️\n\nПривет! Рады видеть тебя снова. Выбери категорию:", reply_markup=get_main_menu_kb())
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Мне есть 18 лет 🔞", callback_data="age_yes")],
            [InlineKeyboardButton(text="Мне нет 18 лет", callback_data="age_no")]
        ])
        await message.answer("⚠️ <b>ВЕРИФИКАЦИЯ ВОЗРАСТА</b> ⚠️\n\nДля доступа к боту подтвердите, что вам исполнилось 18 лет.", reply_markup=kb, parse_mode="HTML")
        await state.set_state(ShopStates.waiting_for_age)

@dp.callback_query(ShopStates.waiting_for_age, F.data == "age_yes")
async def age_confirmed(callback: CallbackQuery, state: FSMContext):
    set_user_adult(callback.from_user.id)
    await state.clear()
    await callback.message.edit_text("🔞 Доступ разрешен!\n\nДобро пожаловать в магазин ZKVR SHOP. Выберите категорию:", reply_markup=get_main_menu_kb())

@dp.callback_query(ShopStates.waiting_for_age, F.data == "age_no")
async def age_denied(callback: CallbackQuery):
    await callback.answer("Извините, доступ к боту заблокирован для лиц младше 18 лет.", show_alert=True)

# --- АДМИН-ФУНКЦИИ ---
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if int(message.from_user.id) != int(str(ADMIN_ID).strip()): return
    await message.answer("⚙️ Панель администратора ZKVR SHOP:", reply_markup=get_admin_kb())

@dp.callback_query(F.data == "back_to_admin_panel")
async def back_to_admin_panel_handler(callback: CallbackQuery, state: FSMContext):
    if int(callback.from_user.id) != int(str(ADMIN_ID).strip()): return
    await state.clear()
    await callback.message.edit_text("⚙️ Панель администратора ZKVR SHOP:", reply_markup=get_admin_kb())

@dp.callback_query(F.data == "admin_update")
async def ask_for_inventory(callback: CallbackQuery, state: FSMContext):
    if int(callback.from_user.id) != int(str(ADMIN_ID).strip()): return
    await callback.message.answer("Перешли или отправь мне текст с актуальным наличием в твоем формате. Все старые товары будут удалены!")
    await state.set_state(ShopStates.waiting_for_inventory)
    await callback.answer()

@dp.message(ShopStates.waiting_for_inventory)
async def process_new_inventory(message: Message, state: FSMContext):
    if int(message.from_user.id) != int(str(ADMIN_ID).strip()): return
    
    parsed_items = parse_inventory(message.text)
    if not parsed_items:
        await message.answer("❌ Не удалось распознать формат. Проверь наличие галочек ✅ и категорий.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products')
    cursor.execute('DELETE FROM cart')
    
    for item in parsed_items:
        cursor.execute('''
            INSERT INTO products (category, brand, name, price, count)
            VALUES (?, ?, ?, ?, ?)
        ''', (item['category'], item['brand'], item['name'], item['price'], item['count']))
        
    conn.commit()
    conn.close()
    
    await state.clear()
    await message.answer(f"✅ Успешно добавлено товаров: {len(parsed_items)} шт. Витрина обновлена!")

@dp.callback_query(F.data == "admin_stock")
async def send_current_stock_as_text(callback: CallbackQuery):
    if int(callback.from_user.id) != int(str(ADMIN_ID).strip()): return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    categories = {
        "liquids": "🌊Жидкости",
        "pods": "🔌 Под-системы:",
        "consumables": "⚙️ Расходники / Испарители:",
        "snus": "⚠️Снюс:"
    }
    
    output_text = "❗️ZKVR SHOP❗️\n"
    for cat_key, cat_name in categories.items():
        cursor.execute('SELECT DISTINCT price FROM products WHERE category = ? ORDER BY price ASC', (cat_key,))
        prices = cursor.fetchall()
        if not prices: continue
        
        output_text += f"\n{cat_name}\n"
        for p_row in prices:
            price = p_row[0]
            cursor.execute('SELECT brand, name, count FROM products WHERE category = ? AND price = ?', (cat_key, price))
            prod_items = cursor.fetchall()
            
            for item in prod_items:
                brand, name, count = item
                if count <= 0: continue
                cnt_str = f" — {count} шт." if count > 1 else ""
                if cat_key in ["liquids", "pods", "snus"] and brand != "Разное":
                    output_text += f"✅{brand} — {name}{cnt_str}\n"
                else:
                    output_text += f"✅{name}{cnt_str}\n"
            output_text += f"Цена: {price} руб.\n"
            
    output_text += "\nПо покупке писать: @PornHub_Tag\nСсылка для друга: https://t.me/+VTJW9uNAfTZmYmQy"
    conn.close()
    
    await callback.message.answer(output_text)
    await callback.answer()

# --- ФУНКЦИИ ПРОСМОТРА ПОЛЬЗОВАТЕЛЕЙ И БАНОВ ---
@dp.callback_query(F.data == "admin_users_list")
async def admin_users_list(callback: CallbackQuery):
    if int(callback.from_user.id) != int(str(ADMIN_ID).strip()): return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, username, full_name, created_at, is_banned FROM users ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        await callback.answer("Пользователей пока нет.", show_alert=True)
        return
        
    text = f"👥 <b>База пользователей бота (Всего: {len(rows)}):</b>\n\n"
    for row in rows:
        u_id, username, full_name, created_at, is_banned = row
        ban_status = " 🚫 [ЗАБАНЕН]" if is_banned == 1 else ""
        date_formatted = created_at if created_at else "Нет даты"
        text += f"👤 <b>{full_name}</b> ({username}){ban_status}\n🆔 ID: <code>{u_id}</code>\n📅 Вход: {date_formatted}\n\n"
        
    kb = InlineKeyboardMarkup(inline_keyboard=[[[InlineKeyboardButton(text="🔙 В админку", callback_data="back_to_admin_panel")]]])
    
    # Если текст огромный (больше 4000 символов), разбиваем его на части
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await callback.message.answer(text[i:i+4000], parse_mode="HTML")
        await callback.message.answer("Выше выведен весь список.", reply_markup=kb)
    else:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "admin_ban_menu")
async def admin_ban_menu(callback: CallbackQuery):
    if int(callback.from_user.id) != int(str(ADMIN_ID).strip()): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚫 Забанить по ID", callback_data="ban_user_action")],
        [InlineKeyboardButton(text="🟢 Разбанить по ID", callback_data="unban_user_action")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin_panel")]
    ])
    await callback.message.edit_text("🛠 <b>Управление блокировками:</b>", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "ban_user_action")
async def ask_ban_id(callback: CallbackQuery, state: FSMContext):
    if int(callback.from_user.id) != int(str(ADMIN_ID).strip()): return
    await callback.message.answer("✏️ Введите Telegram ID пользователя, которого хотите <b>ЗАБАНИТЬ</b>:", parse_mode="HTML")
    await state.set_state(ShopStates.waiting_for_ban_id)
    await callback.answer()

@dp.message(ShopStates.waiting_for_ban_id)
async def process_ban_id(message: Message, state: FSMContext):
    if int(message.from_user.id) != int(str(ADMIN_ID).strip()): return
    target_id = message.text.strip()
    
    if not target_id.isdigit():
        await message.answer("❌ ID должен состоять только из цифр. Попробуйте еще раз.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT username, full_name FROM users WHERE user_id = ?', (int(target_id),))
    user_found = cursor.fetchone()
    
    if not user_found:
        await message.answer("❌ Пользователь с таким ID не найден в базе данных.")
        conn.close()
        await state.clear()
        return
        
    cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (int(target_id),))
    conn.commit()
    conn.close()
    
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[[InlineKeyboardButton(text="🔙 В админку", callback_data="back_to_admin_panel")]]])
    await message.answer(f"🚫 Пользователь <b>{user_found[1]}</b> ({user_found[0]}) с ID <code>{target_id}</code> успешно <b>ЗАБАНЕН</b>!", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "unban_user_action")
async def ask_unban_id(callback: CallbackQuery, state: FSMContext):
    if int(callback.from_user.id) != int(str(ADMIN_ID).strip()): return
    await callback.message.answer("✏️ Введите Telegram ID пользователя, которого хотите <b>РАЗБАНИТЬ</b>:", parse_mode="HTML")
    await state.set_state(ShopStates.waiting_for_unban_id)
    await callback.answer()

@dp.message(ShopStates.waiting_for_unban_id)
async def process_unban_id(message: Message, state: FSMContext):
    if int(message.from_user.id) != int(str(ADMIN_ID).strip()): return
    target_id = message.text.strip()
    
    if not target_id.isdigit():
        await message.answer("❌ ID должен состоять только из цифр. Попробуйте еще раз.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT username, full_name FROM users WHERE user_id = ?', (int(target_id),))
    user_found = cursor.fetchone()
    
    if not user_found:
        await message.answer("❌ Пользователь с таким ID не найден в базе данных.")
        conn.close()
        await state.clear()
        return
        
    cursor.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (int(target_id),))
    conn.commit()
    conn.close()
    
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[[[InlineKeyboardButton(text="🔙 В админку", callback_data="back_to_admin_panel")]]])
    await message.answer(f"🟢 Пользователь <b>{user_found[1]}</b> ({user_found[0]}) с ID <code>{target_id}</code> успешно <b>РАЗБАНИТЬ</b>!", reply_markup=kb, parse_mode="HTML")


# --- ЛОГИКА РУЧНОГО СПИСАНИЯ ДЛЯ АДМИНА ---
@dp.callback_query(F.data == "admin_decrease_select_cat")
async def admin_dec_cat(callback: CallbackQuery):
    if int(callback.from_user.id) != int(str(ADMIN_ID).strip()): return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💧 Жидкости", callback_data="admdectype_liquids")],
        [InlineKeyboardButton(text="🔌 Под-системы", callback_data="admdectype_pods")],
        [InlineKeyboardButton(text="⚙️ Расходники", callback_data="admdectype_consumables")],
        [InlineKeyboardButton(text="⚠️ Снюс", callback_data="admdectype_snus")]
    ])
    await callback.message.edit_text("⚙️ <b>Списание товара</b>\nВыбери категорию для удаления 1 штуки:", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("admdectype_"))
async def admin_dec_brand(callback: CallbackQuery):
    if int(callback.from_user.id) != int(str(ADMIN_ID).strip()): return
    category = callback.data.split("_")[1]
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT brand FROM products WHERE category = ? AND count > 0', (category,))
    brands = cursor.fetchall()
    conn.close()
    
    if not brands:
        await callback.answer("В этой категории ничего нет.", show_alert=True)
        return
        
    buttons = []
    for b in brands:
        buttons.append([InlineKeyboardButton(text=b[0], callback_data=f"admdecbrand_{category}_{b[0]}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_decrease_select_cat")])
    
    await callback.message.edit_text("Выбери производителя для списания:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("admdecbrand_"))
async def admin_dec_items(callback: CallbackQuery):
    if int(callback.from_user.id) != int(str(ADMIN_ID).strip()): return
    _, category, brand = callback.data.split("_")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, count FROM products WHERE category = ? AND brand = ? AND count > 0', (category, brand))
    items = cursor.fetchall()
    conn.close()
    
    buttons = []
    for item in items:
        p_id, name, count = item
        buttons.append([InlineKeyboardButton(text=f"{name[:20]}... ({count} шт)", callback_data=f"admdecreal_{p_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"admdectype_{category}")])
    
    await callback.message.edit_text(f"Нажми на товар, чтобы списать <b>1 шт</b> из базы:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.callback_query(F.data.startswith("admdecreal_"))
async def admin_dec_execute(callback: CallbackQuery):
    if int(callback.from_user.id) != int(str(ADMIN_ID).strip()): return
    p_id = int(callback.data.split("_")[1])
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT brand, name, count, category FROM products WHERE id = ?', (p_id,))
    res = cursor.fetchone()
    
    if res:
        brand, name, count, category = res
        new_count = count - 1
        cursor.execute('UPDATE products SET count = ? WHERE id = ?', (new_count, p_id))
        conn.commit()
        await callback.answer(f"Списано! Осталось: {max(0, new_count)} шт.", show_alert=True)
        
        cursor.execute('SELECT id, name, count FROM products WHERE category = ? AND brand = ? AND count > 0', (category, brand))
        items = cursor.fetchall()
        
        buttons = []
        for item in items:
            buttons.append([InlineKeyboardButton(text=f"{item[1][:20]}... ({item[2]} шт)", callback_data=f"admdecreal_{item[0]}")])
        buttons.append([InlineKeyboardButton(text="🔙 В админку", callback_data="back_to_admin_panel")])
        
        await callback.message.edit_text(f"Успешно убрали 1 шт <b>{brand} — {name}</b>.\nМожно списать что-то еще из этой линейки:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    conn.close()

# --- КАТАЛОГ ДЛЯ КЛИЕНТОВ ---
@dp.callback_query(F.data.startswith("showcat_"))
async def client_show_brands(callback: CallbackQuery):
    category = callback.data.split("_")[1]
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT brand FROM products WHERE category = ? AND count > 0', (category,))
    brands = cursor.fetchall()
    conn.close()
    
    if not brands:
        await callback.answer("В этой категории сейчас ничего нет в наличии.", show_alert=True)
        return
        
    buttons = []
    for b in brands:
        brand_name = b[0]
        buttons.append([InlineKeyboardButton(text=brand_name, callback_data=f"showbrand_{category}_{brand_name}")])
        
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")])
    await callback.message.edit_text("Выбери производителя / тип:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("showbrand_"))
async def client_show_items(callback: CallbackQuery):
    _, category, brand = callback.data.split("_")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, price, count FROM products WHERE category = ? AND brand = ? AND count > 0', (category, brand))
    items = cursor.fetchall()
    conn.close()
    
    buttons = []
    for item in items:
        p_id, name, price, count = item
        text = f"{name} ({price}₽) — {count}шт"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"iteminfo_{p_id}")])
        
    buttons.append([InlineKeyboardButton(text="🔙 Назад к производителям", callback_data=f"showcat_{category}")])
    await callback.message.edit_text(f"Выбирай позицию от {brand}:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@dp.callback_query(F.data.startswith("iteminfo_"))
async def client_item_info(callback: CallbackQuery):
    p_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT category, brand, name, price, count FROM products WHERE id = ?', (p_id,))
    item = cursor.fetchone()
    conn.close()
    
    if not item:
        await callback.answer("Товар пропал из наличия.", show_alert=True)
        return
        
    category, brand, name, price, count = item
    text = f"📋 <b>Товар:</b> {brand} — {name}\n💰 <b>Цена:</b> {price} руб.\n📦 <b>В наличии:</b> {count} шт."
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Добавить в корзину", callback_data=f"addtocart_{p_id}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"showbrand_{category}_{brand}")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

# --- ЛОГИКА КОРЗИНЫ ---
@dp.callback_query(F.data.startswith("addtocart_"))
async def add_to_cart(callback: CallbackQuery):
    p_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT count FROM products WHERE id = ?', (p_id,))
    prod_count = cursor.fetchone()
    
    if not prod_count or prod_count[0] <= 0:
        await callback.answer("Извините, этот товар закончился.", show_alert=True)
        conn.close()
        return
        
    cursor.execute('SELECT quantity FROM cart WHERE user_id = ? AND product_id = ?', (user_id, p_id))
    cart_row = cursor.fetchone()
    current_in_cart = cart_row[0] if cart_row else 0
    
    if current_in_cart >= prod_count[0]:
        await callback.answer("Вы не можете взять больше, чем есть в наличии!", show_alert=True)
    else:
        cursor.execute('''
            INSERT INTO cart (user_id, product_id, quantity)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, product_id) DO UPDATE SET quantity = quantity + 1
        ''', (user_id, p_id))
        conn.commit()
        await callback.answer("Добавлено в корзину! 🎉")
    conn.close()

@dp.callback_query(F.data == "view_cart")
async def view_cart(callback: CallbackQuery):
    user_id = callback.from_user.id
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.id, p.brand, p.name, p.price, c.quantity, p.count 
        FROM cart c 
        JOIN products p ON c.product_id = p.id 
        WHERE c.user_id = ?
    ''', (user_id,))
    cart_items = cursor.fetchall()
    conn.close()
    
    if not cart_items:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_main")]])
        await callback.message.edit_text("🛒 Твоя корзина пуста.", reply_markup=kb)
        return
        
    text = "🛒 <b>Ваша корзина:</b>\n\n"
    total_price = 0
    buttons = []
    
    for item in cart_items:
        p_id, brand, name, price, quantity, stock = item
        if quantity > stock: quantity = stock
        cost = price * quantity
        total_price += cost
        text += f"▪️ {brand} - {name}\n   {quantity} шт. х {price}₽ = {cost}₽\n\n"
        buttons.append([InlineKeyboardButton(text=f"❌ Удалить {name[:15]}...", callback_data=f"delcart_{p_id}")])
        
    text += f"Total: 💰 <b>{total_price} руб.</b>"
    buttons.append([InlineKeyboardButton(text="✅ Забронировать всё", callback_data="checkout_cart")])
    buttons.append([InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart")])
    buttons.append([InlineKeyboardButton(text="🔙 Продолжить покупки", callback_data="back_to_main")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

@dp.callback_query(F.data.startswith("delcart_"))
async def delete_item_from_cart(callback: CallbackQuery):
    p_id = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM cart WHERE user_id = ? AND product_id = ?', (user_id, p_id))
    conn.commit()
    conn.close()
    await callback.answer("Удалено из корзины")
    await view_cart(callback)

@dp.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM cart WHERE user_id = ?', (callback.from_user.id,))
    conn.commit()
    conn.close()
    await callback.answer("Корзина очищена")
    await view_cart(callback)

# --- ФИНАЛЬНОЕ БРОНИРОВАНИЕ ---
@dp.callback_query(F.data == "checkout_cart")
async def checkout_cart(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = callback.from_user
    username = f"@{user.username}" if user.username else "Нет юзернейма"
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT p.id, p.brand, p.name, p.price, c.quantity, p.count 
        FROM cart c 
        JOIN products p ON c.product_id = p.id 
        WHERE c.user_id = ?
    ''', (user_id,))
    cart_items = cursor.fetchall()
    
    if not cart_items:
        await callback.answer("Корзина пуста!", show_alert=True)
        conn.close()
        return
        
    for item in cart_items:
        p_id, brand, name, price, quantity, stock = item
        if stock < quantity:
            await callback.answer(f"Ошибка! {name} осталось всего {stock} шт.", show_alert=True)
            conn.close()
            return
            
    order_text = f"🚨 <b>Новая бронь!</b>\n\n👤 <b>Клиент:</b> {user.full_name} ({username})\n🆔 ID: <code>{user.id}</code>\n\n📦 <b>Состав заказа:</b>\n"
    client_text = f"🎉 <b>Бронь успешно оформлена!</b>\n\n📦 <b>Ваш заказ:</b>\n"
    total_price = 0
    
    cancel_data_list = []
    
    for item in cart_items:
        p_id, brand, name, price, quantity, stock = item
        cost = price * quantity
        total_price += cost
        item_line = f"• {brand} — {name} ({quantity} шт.) — {cost}₽\n"
        order_text += item_line
        client_text += item_line
        
        cancel_data_list.append(f"{p_id}:{quantity}")
        
        new_stock = max(0, stock - quantity)
        cursor.execute('UPDATE products SET count = ? WHERE id = ?', (new_stock, p_id))
        
    order_text += f"\n💰 <b>Итого к оплате:</b> {total_price} text руб."
    client_text += f"\n💰 <b>Итого к оплате:</b> {total_price} руб.\n\n⚠️ Бронь держится 24 часа. Ждем вас в магазине!"
    
    cursor.execute('DELETE FROM cart WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    items_encoded = "-".join(cancel_data_list)[:35]
    admin_callback = f"cancelord_{user_id}_{items_encoded}"
    
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить бронь", callback_data=admin_callback)]
    ])
    
    try:
        target_admin = int(str(ADMIN_ID).strip())
        await bot.send_message(chat_id=target_admin, text=order_text, reply_markup=admin_kb, parse_mode="HTML")
        logging.info(f"Уведомление о заказе успешно отправлено админу {target_admin}")
    except Exception as e:
        logging.error(f" КРИТИЧЕСКАЯ ОШИБКА ОТПРАВКИ АДМИНУ: {e}")
        
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 В меню", callback_data="back_to_main")]])
    await callback.message.edit_text(client_text, reply_markup=kb, parse_mode="HTML")
    await callback.answer("Успешно забронировано!", show_alert=True)

# --- ОБРАБОТЧИК ОТМЕНЫ БРОНИ АДМИНИСТРАТОРОМ ---
@dp.callback_query(F.data.startswith("cancelord_"))
async def admin_cancel_order(callback: CallbackQuery):
    if int(callback.from_user.id) != int(str(ADMIN_ID).strip()): return
    
    parts = callback.data.split("_")
    client_id = int(parts[1])
    encoded_items = parts[2]
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    item_blocks = encoded_items.split("-")
    for block in item_blocks:
        if ":" in block:
            p_id, quantity = map(int, block.split(":"))
            cursor.execute('UPDATE products SET count = count + ? WHERE id = ?', (quantity, p_id))
            
    conn.commit()
    conn.close()
    
    try:
        await bot.send_message(
            chat_id=client_id, 
            text="⚠️ <b>Ваша бронь была отменена администратором магазина.</b>\nТовары возвращены на витрину бота.",
            parse_mode="HTML"
        )
    except Exception:
        pass
        
    updated_text = callback.message.text + "\n\n❌ <b>БРОНЬ ОТМЕНЕНА АДМИНИСТРАТОРОМ</b>"
    await callback.message.edit_text(updated_text, reply_markup=None, parse_mode="HTML")
    await callback.answer("Бронь успешно отменена, товары возвращены на склад!", show_alert=True)

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_handler(callback: CallbackQuery):
    await callback.message.edit_text("👋 Выберите категорию товара:", reply_markup=get_main_menu_kb())
    await callback.answer()

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
