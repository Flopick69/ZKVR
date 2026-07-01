import sqlite3
import asyncio
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.utils.markdown import html_decoration as hd
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- НАСТРОЙКИ ---
TOKEN = "8940239980:AAH1u8qqQo9MtSpv4KHLlRcr6ckm3s3_ZQI"
MY_ID = 8344626747  

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# Часовой пояс (Екатеринбург)
try:
    import zoneinfo
    yekt_tz = zoneinfo.ZoneInfo("Asia/Yekaterinburg")
except ImportError:
    from datetime import timezone, timedelta
    yekt_tz = timezone(timedelta(hours=5))

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
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER,
            name TEXT UNIQUE,
            price INTEGER,
            quantity INTEGER,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            product_id INTEGER,
            FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id TEXT PRIMARY KEY,
            hour TEXT,
            minute TEXT
        )
    """)
    
    default_cats = ["🌊 Жидкости", "🔌 Под-системы", "⚙️ Расходники / Испарители", "⚠️ Снюс"]
    for cat in default_cats:
        try: cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat,))
        except: pass
            
    conn.commit()
    conn.close()

init_db()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ГЕНЕРАЦИИ ТЕКСТА ---
def generate_stock_text(for_copy=False):
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories")
    categories = cursor.fetchall()
    
    text = "❗️ZKVR SHOP❗️\n\n"
    has_items = False
    
    for cat_id, cat_name in categories:
        if for_copy:
            cursor.execute("SELECT name, price, quantity FROM products WHERE category_id = ?", (cat_id,))
        else:
            cursor.execute("SELECT name, price, quantity FROM products WHERE category_id = ? AND quantity > 0", (cat_id,))
        items = cursor.fetchall()
        
        if not items: continue
        has_items = True
        text += f"{cat_name}:\n"
        
        prices = sorted(list(set([x[1] for x in items])))
        for pr in prices:
            cat_items = [x for x in items if x[1] == pr]
            for name, price, qty in cat_items:
                qty_str = f" — {qty} шт." if qty > 1 else ""
                icon = "✅" if qty > 0 else "❌"
                text += f"{icon}{name}{qty_str}\n"
            text += f"Цена: {pr} руб.\n\n"
            
    conn.close()
    if not has_items:
        return "🔥 Все товары временно распроданы! Ожидаем завоз."
        
    text += "По поводу покупки писать:\n👉 менеджеру @PornHub_Tag\n👉 либо в нашего бота: @zkvr_shop_bot"
    return f"`{text}`" if for_copy else text

async def send_to_top_shmot():
    post_text = generate_stock_text(for_copy=True)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 Перейти в предложку Топ Шмот", url="https://t.me/anonquebot?start=aovablu")]])
    try:
        await bot.send_message(chat_id=MY_ID, text="⏰ **Напоминание! Время выложить новый прайс-лист!**\n\nТапни по тексту ниже для копирования:", parse_mode="Markdown")
        await bot.send_message(chat_id=MY_ID, text=post_text, reply_markup=keyboard, parse_mode="Markdown")
    except Exception as e: print(f"Ошибка рассылки: {e}")

def load_reminders():
    for job in scheduler.get_jobs():
        if job.id.startswith("remind_"): scheduler.remove_job(job.id)
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, hour, minute FROM reminders")
    rows = cursor.fetchall()
    conn.close()
    for r_id, h, m in rows:
        scheduler.add_job(send_to_top_shmot, "cron", hour=h, minute=m, id=f"remind_{r_id}", timezone=yekt_tz)

# --- ГЛАВНЫЕ КНОПКИ АДМИН-ПАНЕЛИ ---
def get_admin_main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Получить прайс-лист", callback_data="admin_get_stock")],
        [InlineKeyboardButton(text="🔄 Обновить наличие (Прайсом)", callback_data="admin_req_update")],
        [InlineKeyboardButton(text="🗑 Удаление товаров", callback_data="admin_go_delete")],
        [InlineKeyboardButton(text="🔔 Настройка напоминаний", callback_data="admin_go_remind")]
    ])

# --- ОСТАЛЬНЫЕ КНОПКИ (УДАЛЕНИЕ / БУДИЛЬНИКИ / КЛИЕНТЫ) ---
def get_reminders_keyboard():
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, hour, minute FROM reminders ORDER BY hour, minute")
    active = cursor.fetchall()
    conn.close()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    if active:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔔 Активные (Нажми для удаления):", callback_data="none")])
        for r_id, h, m in active:
            keyboard.inline_keyboard.append([InlineKeyboardButton(text=f"❌ {h:0>2}:{m:0>2} (Удалить)", callback_data=f"remdel_{r_id}")])
    else:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="🔕 Напоминаний пока нет", callback_data="none")])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="➕ Быстрое добавление:", callback_data="none")])
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="09:00", callback_data="remadd_09_00"),
        InlineKeyboardButton(text="13:00", callback_data="remadd_13_00"),
        InlineKeyboardButton(text="17:00", callback_data="remadd_17_00")
    ])
    keyboard.inline_keyboard.append([
        InlineKeyboardButton(text="19:00", callback_data="remadd_19_00"),
        InlineKeyboardButton(text="21:00", callback_data="remadd_21_00"),
        InlineKeyboardButton(text="23:00", callback_data="remadd_23_00")
    ])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="admin_back_main")])
    return keyboard

def get_admin_delete_cats():
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM categories")
    cats = cursor.fetchall()
    conn.close()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for c_id, name in cats:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=name, callback_data=f"delcat_list_{c_id}"), InlineKeyboardButton(text="❌ Снести группу", callback_data=f"delcat_confirm_{c_id}")])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="admin_back_main")])
    return keyboard

def get_admin_delete_products(category_id):
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM products WHERE category_id = ?", (category_id,))
    products = cursor.fetchall()
    conn.close()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for p_id, name in products:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=f"❌ {name}", callback_data=f"delprod_{category_id}_{p_id}")])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="⬅️ К группам", callback_data="admin_go_delete")])
    return keyboard

def get_categories_keyboard():
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT c.id, c.name FROM categories c JOIN products p ON c.id = p.category_id WHERE p.quantity > 0")
    cats = cursor.fetchall()
    conn.close()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for c_id, name in cats:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=name, callback_data=f"show_cat_{c_id}")])
    return keyboard

def get_products_keyboard(category_id):
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price FROM products WHERE category_id = ? AND quantity > 0", (category_id,))
    products = cursor.fetchall()
    conn.close()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for p_id, name, price in products:
        keyboard.inline_keyboard.append([InlineKeyboardButton(text=f"🛍 {name} — {price}₽", callback_data=f"buy_{p_id}")])
    keyboard.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")])
    return keyboard


# --- ХЕНДЛЕРЫ АДМИНКИ ---

@dp.message(Command("start"))
async def start_cmd(message: Message):
    if message.from_user.id == MY_ID:
        admin_info = (
            "⚙️ **ДОБРО ПОЖАЛОВАТЬ В АДМИН-ПАНЕЛЬ ZKVR SHOP!**\n\n"
            "📖 **Шпаргалка по доступным командам:**\n"
            "▶️ `/start` — Показать эту панель управления и сбросить контекст.\n"
            "📊 `/stock` — Мгновенно выдать прайс-лист для Топ Шмот текстом.\n"
            "📥 `/update` `[текст прайса]` — Альтернативное обновление базы через текст.\n"
            "⚙️ `/delete` — Быстрый вызов интерактивного удаления товаров.\n"
            "⏰ `/remind` — Меню настройки времени авто-рассылки прайса.\n"
            "➕ `/remind_add` `[ЧЧ:ММ]` — Добавить нестандартное время напоминания.\n"
            "🗑 `/clear` — Полная очистка витрины (категории останутся).\n\n"
            "👇 **Используй кнопки ниже для удобного управления:**"
        )
        await message.answer(admin_info, parse_mode="Markdown")
        await message.answer("🎛 **Главное меню администратора:**", reply_markup=get_admin_main_keyboard())
    else:
        await message.answer(f"Привет, {message.from_user.first_name}! 👋\nВыбери интересующую тебя категорию товаров ниже:", reply_markup=get_categories_keyboard())

@dp.callback_query(F.data == "admin_back_main")
async def admin_back_main_callback(callback: CallbackQuery):
    await callback.message.edit_text("🎛 **Главное меню администратора:**", reply_markup=get_admin_main_keyboard())

@dp.callback_query(F.data == "admin_get_stock")
async def admin_get_stock_callback(callback: CallbackQuery):
    await callback.answer()
    post_text = generate_stock_text(for_copy=True)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 Перейти в предложку Топ Шмот", url="https://t.me/anonquebot?start=aovablu")]])
    await callback.message.answer("📋 **Актуальный прайс-лист получен!**\n\nТапни по тексту ниже для копирования:", parse_mode="Markdown")
    await callback.message.answer(post_text, reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query(F.data == "admin_req_update")
async def admin_req_update_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "🔄 **Обновление ассортимента**\n\n"
        "Скопируй свой прайс-лист, добавь в самый верх строчку `/update` и отправь её мне ответным сообщением.\n\n"
        "Пример:\n"
        "`/update`\n"
        "`✅Анархия V2 — Клюква`\n"
        "`Цена: 400`", 
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back_main")]])
    )

@dp.callback_query(F.data == "admin_go_delete")
async def admin_go_delete_callback(callback: CallbackQuery):
    await callback.message.edit_text("🗑 **Управление удалением**\n\nВыбери группу, чтобы посмотреть товары, или нажми «Снести группу»:", reply_markup=get_admin_delete_cats())

@dp.callback_query(F.data == "admin_go_remind")
async def admin_go_remind_callback(callback: CallbackQuery):
    await callback.message.edit_text(
        "🔔 **Настройка расписания**\n\nВыбирай готовое время кнопками или отправь команду формата `/remind_add 15:30` для своего времени.",
        reply_markup=get_reminders_keyboard()
    )

@dp.callback_query(F.data.startswith("remadd_"))
async def remadd_callback(callback: CallbackQuery):
    _, hour, minute = callback.data.split("_")
    r_id = f"{hour}_{minute}"
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO reminders (id, hour, minute) VALUES (?, ?, ?)", (r_id, hour, minute))
    conn.commit()
    conn.close()
    load_reminders()
    await callback.answer("Время добавлено!")
    await callback.message.edit_reply_markup(reply_markup=get_reminders_keyboard())

@dp.callback_query(F.data.startswith("remdel_"))
async def remdel_callback(callback: CallbackQuery):
    r_id = callback.data.split("_")[1] + "_" + callback.data.split("_")[2]
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM reminders WHERE id = ?", (r_id,))
    conn.commit()
    conn.close()
    load_reminders()
    await callback.answer("Удалено!")
    await callback.message.edit_reply_markup(reply_markup=get_reminders_keyboard())

@dp.message(F.chat.id == MY_ID, Command("stock"))
async def check_stock_cmd(message: Message): await send_to_top_shmot()

@dp.message(F.chat.id == MY_ID, Command("delete"))
async def delete_menu_cmd(message: Message): await message.answer("🛠 **Управление удалением**", reply_markup=get_admin_delete_cats())

@dp.message(F.chat.id == MY_ID, Command("remind"))
async def remind_menu_cmd(message: Message): await message.answer("🔔 **Настройка напоминаний**", reply_markup=get_reminders_keyboard())

@dp.message(F.chat.id == MY_ID, Command("clear"))
async def clear_stock_cmd(message: Message):
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products"); cursor.execute("DELETE FROM bookings")
    conn.commit(); conn.close()
    await message.answer("🗑 **Все товары удалены! Настройки расписания сохранены.**")

@dp.message(F.chat.id == MY_ID, Command(re.compile(r"remind_add")))
async def manual_remind_add(message: Message):
    time_raw = message.text.replace("/remind_add", "").strip()
    match = re.match(r"^(\d{1,2}):(\d{2})$", time_raw)
    if not match:
        await message.answer("❌ Неверный формат! Пример: `/remind_add 14:05`")
        return
    hour, minute = match.group(1), match.group(2)
    r_id = f"{hour}_{minute}"
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO reminders (id, hour, minute) VALUES (?, ?, ?)", (r_id, hour, minute))
    conn.commit(); conn.close()
    load_reminders()
    await message.answer(f"✅ Напоминание на {hour:0>2}:{minute:0>2} установлено!", reply_markup=get_reminders_keyboard())

# --- УМНЫЙ ПАРСЕР ПРАЙСА ---
@dp.message(F.chat.id == MY_ID, Command("update"))
async def update_assortment(message: Message):
    raw_text = message.text.replace("/update", "").strip()
    if not raw_text:
        await message.answer("❌ Пришли прайс-лист после команды `/update`!")
        return
    
    lines = raw_text.split("\n")
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    
    # Очищаем товары перед перезаливкой
    cursor.execute("DELETE FROM products")
    cursor.execute("DELETE FROM bookings")
    
    added_count = 0
    current_cat_id = 1
    
    cat_triggers = {
        "жидкост": "🌊 Жидкости", "жижа": "🌊 Жидкости", "🌊": "🌊 Жидкости", 
        "под-систем": "🔌 Под-системы", "под ": "🔌 Под-системы", "🔌": "🔌 Под-системы", 
        "расходник": "⚙️ Расходники / Испарители", "испарител": "⚙️ Расходники / Испарители", 
        "картридж": "⚙️ Расходники / Испарители", "⚙️": "⚙️ Расходники / Испарители", 
        "снюс": "⚠️ Снюс", "⚠️": "⚠️ Снюс"
    }
    
    temp_products = []
    
    for line in lines:
        line = line.strip()
        if not line: continue
        line_lower = line.lower()
        
        # Проверяем триггеры смены категории
        cat_changed = False
        for trigger, cat_full_name in cat_triggers.items():
            if trigger in line_lower and "цена" not in line_lower:
                cursor.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat_full_name,))
                cursor.execute("SELECT id FROM categories WHERE name = ?", (cat_full_name,))
                current_cat_id = cursor.fetchone()[0]
                cat_changed = True
                break
        if cat_changed: continue
        
        # Если встречаем строчку с ценой, закрываем блок товаров сверху
        price_match = re.search(r'(?:цена|Цена):\s*(\d+)', line)
        if price_match:
            block_price = int(price_match.group(1))
            # Присваиваем цену всем позициям выше, у которых цена ещё не определена
            for prod in temp_products:
                if prod['price'] is None:
                    prod['price'] = block_price
            continue
            
        # Считывание самого товара
        if line.startswith("✅") or line.startswith("❌"):
            is_available = line.startswith("✅")
            clean_line = line[1:].strip()
            
            qty_match = re.search(r'—\s*(\d+)\s*шт', clean_line)
            if qty_match:
                quantity = int(qty_match.group(1))
                name = clean_line[:qty_match.start()].strip()
            else:
                quantity = 1 if is_available else 0
                name = clean_line
                
            if not is_available: quantity = 0
            
            temp_products.append({
                'cat_id': current_cat_id,
                'name': name,
                'price': None, # Определится ниже по тексту строки "Цена"
                'quantity': quantity
            })

    # Пушим собранные и оцененные товары в базу
    try:
        for prod in temp_products:
            final_price = prod['price'] if prod['price'] is not None else 400
            cursor.execute(
                "INSERT OR REPLACE INTO products (category_id, name, price, quantity) VALUES (?, ?, ?, ?)",
                (prod['cat_id'], prod['name'], final_price, prod['quantity'])
            )
            added_count += 1
            
        conn.commit()
        await message.answer(f"✅ Успешно обновлено позиций: {added_count}")
        await message.answer(generate_stock_text(for_copy=False), reply_markup=get_admin_main_keyboard())
    except Exception as e: 
        await message.answer(f"❌ Ошибка при сохранении в базу: {e}")
    finally: 
        conn.close()

# Коллбэки удаления товаров
@dp.callback_query(F.data.startswith("delcat_list_"))
async def delcat_list(callback: CallbackQuery):
    cat_id = int(callback.data.split("_")[2])
    await callback.message.edit_text("Нажми на товар для его удаления:", reply_markup=get_admin_delete_products(cat_id))

@dp.callback_query(F.data.startswith("delprod_"))
async def delprod_action(callback: CallbackQuery):
    _, cat_id, p_id = callback.data.split("_")
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (p_id,))
    conn.commit(); conn.close()
    await callback.answer("Товар удален!")
    await callback.message.edit_reply_markup(reply_markup=get_admin_delete_products(int(cat_id)))

@dp.callback_query(F.data.startswith("delcat_confirm_"))
async def delcat_confirm(callback: CallbackQuery):
    cat_id = int(callback.data.split("_")[2])
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE category_id = ?", (cat_id,))
    cursor.execute("DELETE FROM categories WHERE id = ?", (cat_id,))
    conn.commit(); conn.close()
    await callback.answer("Группа и товары удалены!")
    await callback.message.edit_reply_markup(reply_markup=get_admin_delete_cats())

# Кнопки админа для обработки заказов
@dp.callback_query(F.data.startswith("admin_"))
async def handle_admin_buttons(callback: CallbackQuery):
    action, booking_id = callback.data.split("_")[1:]
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    if action == "sold":
        cursor.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
        conn.commit()
        await callback.message.edit_text(f"{callback.message.text}\n\n✅ Продано.", parse_mode="HTML")
    elif action == "cancel":
        cursor.execute("SELECT product_id FROM bookings WHERE id = ?", (booking_id,))
        res = cursor.fetchone()
        if res:
            cursor.execute("UPDATE products SET quantity = quantity + 1 WHERE id = ?", (res[0],))
            cursor.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
            conn.commit()
            await callback.message.edit_text(f"{callback.message.text}\n\n❌ Отменено.", parse_mode="HTML")
    conn.close()


# --- ХЕНДЛЕРЫ КЛИЕНТОВ ---
@dp.callback_query(F.data == "main_menu")
async def client_main_menu(callback: CallbackQuery): await callback.message.edit_text("Выбери категорию товара:", reply_markup=get_categories_keyboard())

@dp.callback_query(F.data.startswith("show_cat_"))
async def client_show_cat(callback: CallbackQuery):
    cat_id = int(callback.data.split("_")[2])
    await callback.message.edit_text("Выбирай позицию для брони:", reply_markup=get_products_keyboard(cat_id))

@dp.callback_query(F.data.startswith("buy_"))
async def handle_purchase(callback: CallbackQuery):
    product_id = callback.data.split("_")[1]
    user_id = callback.from_user.id
    raw_username = callback.from_user.username or "без_юзернейма"
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, quantity FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    if not product or product[2] <= 0:
        await callback.answer("Извини, товар уже закончился! 😢", show_alert=True)
        conn.close(); return
    p_name, p_price, _ = product
    cursor.execute("UPDATE products SET quantity = quantity - 1 WHERE id = ?", (product_id,))
    cursor.execute("INSERT INTO bookings (user_id, username, product_id) VALUES (?, ?, ?)", (user_id, raw_username, product_id))
    conn.commit(); booking_id = cursor.lastrowid; conn.close()
    await callback.message.answer(f"✅ <b>Забронировано:</b> {hd.quote(p_name)} ({p_price}₽).", parse_mode="HTML")
    await callback.answer()
    admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Продано", callback_data=f"admin_sold_{booking_id}"), InlineKeyboardButton(text="❌ Отмена", callback_data=f"admin_cancel_{booking_id}")]])
    client_link = f"https://t.me/{raw_username}" if raw_username != "без_юзернейма" else f"tg://user?id={user_id}"
    await bot.send_message(chat_id=MY_ID, text=f"🚨 <b>НОВЫЙ ЗАКАЗ!</b>\n\n📦 <b>Товар:</b> {p_name}\n👤 <b>Покупатель:</b> @{raw_username}\n\n🔗 <a href='{client_link}'>НАПИСАТЬ КЛИЕНТУ</a>", reply_markup=admin_keyboard, parse_mode="HTML")

# --- ЗАПУСК ---
async def main():
    load_reminders()
    scheduler.start()
    print("Робот запущен! Админ-меню на кнопках готово.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
