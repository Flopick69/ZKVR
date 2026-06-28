import sqlite3
import asyncio
import re
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.utils.markdown import html_decoration as hd
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- НАСТРОЙКИ ---
TOKEN = "8940239980:AAH1u8qqQo9MtSpv4KHLlRcr6ckm3s3_ZQI"
MY_ID = 8344626747  # Твой Telegram ID вшит

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ ---
def init_db():
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            price INTEGER,
            quantity INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            product_id INTEGER,
            FOREIGN KEY(product_id) REFERENCES products(id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# --- УМНАЯ ГЕНЕРАЦИЯ ТЕКСТА НАЛИЧИЯ ПО ТВОЕМУ ШАБЛОНУ ---
def generate_stock_text(for_copy=False):
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    if for_copy:
        cursor.execute("SELECT name, price, quantity FROM products")
    else:
        cursor.execute("SELECT name, price, quantity FROM products WHERE quantity > 0")
    items = cursor.fetchall()
    conn.close()
    
    if not items:
        return "🔥 Все товары временно распроданы! Ожидаем завоз."
        
    vapes_400 = []
    vapes_450 = []
    cartridges = []
    boosters = []
    other = []
    
    for name, price, qty in items:
        qty_str = f" — {qty} шт." if qty > 1 else ""
        icon = "✅" if qty > 0 else "❌"
        item_line = f"{icon}{name}{qty_str}"
        
        name_lower = name.lower()
        if "картридж" in name_lower or "xros" in name_lower or "vaporesso" in name_lower:
            cartridges.append((item_line, price, qty))
        elif "бустер" in name_lower or "никобустер" in name_lower:
            boosters.append((item_line, price, qty))
        elif price == 400:
            vapes_400.append((item_line, qty))
        elif price == 450:
            vapes_450.append((item_line, qty))
        else:
            other.append((item_line, price, qty))

    text = "❗️ZKVR SHOP❗️\n\n"
    
    # Жижи по 400
    if vapes_400:
        for line, qty in vapes_400:
            if not for_copy and qty == 0: continue
            text += f"{line}\n"
        text += "\nЦена: 400 руб. \n\n"
        
    # Жижи по 450
    if vapes_450:
        for line, qty in vapes_450:
            if not for_copy and qty == 0: continue
            text += f"{line}\n"
        text += "\nЦена: 450 руб. \n\n"
        
    # Другие жижи
    if other:
        for line, pr, qty in other:
            if not for_copy and qty == 0: continue
            text += f"{line}\n"
        text += f"\nЦена: {other[0][1]} руб. \n\n"
        
    # Картриджи
    if cartridges:
        text += "Картриджи:\n"
        for line, pr, qty in cartridges:
            if not for_copy and qty == 0: continue
            text += f"{line} (Цена: {pr} руб.)\n"
        text += "\n"
            
    # Никобустеры
    if boosters:
        for line, pr, qty in boosters:
            if not for_copy and qty == 0: continue
            text += f"{line} (Цена: {pr} руб.)\n"
        text += "\n"
        
    text += "По поводу покупки писать:\n"
    text += "👉 менеджеру @PornHub_Tag\n"
    text += "👉 либо в нашего бота для моментальной брони: @zkvr_shop_bot"
    
    if for_copy:
        return f"`{text}`"
    return text

# Функция рассылки прайса по будильникам
async def send_to_top_shmot():
    post_text = generate_stock_text(for_copy=True)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📥 Перейти в предложку Топ Шмот", url="https://t.me/anonquebot?start=aovablu")
        ]
    ])
    
    try:
        await bot.send_message(
            chat_id=MY_ID, 
            text="⏰ **Актуальный прайс-лист!**\n\n"
                 "Нажми (тапни) на текст ниже, чтобы он автоматически скопировался, затем переходи по кнопке в предложку и отправь его туда 👇",
            parse_mode="Markdown"
        )
        await bot.send_message(
            chat_id=MY_ID,
            text=post_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Ошибка при отправке: {e}")

# --- КНОПКИ ДЛЯ КЛИЕНТОВ ---
def get_products_keyboard():
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price FROM products WHERE quantity > 0")
    products = cursor.fetchall()
    conn.close()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])
    for p_id, name, price in products:
        safe_name = hd.quote(name)
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=f"🛍 {safe_name} — {price}₽", callback_data=f"buy_{p_id}")
        ])
    return keyboard

# --- ХЕНДЛЕРЫ ДЛЯ АДМИНА ---

@dp.message(F.chat.id == MY_ID, Command("stock"))
async def check_stock_cmd(message: Message):
    await send_to_top_shmot()

# УМНЫЙ ПАРСЕР ПРАЙС-ЛИСТОВ ЛЮБОГО ФОРМАТА
@dp.message(F.chat.id == MY_ID, Command("update"))
async def update_assortment(message: Message):
    raw_text = message.text.replace("/update", "").strip()
    if not raw_text:
        await message.answer("❌ Пришли прайс-лист или список товаров после команды `/update`!")
        return

    lines = raw_text.split("\n")
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    
    added_count = 0
    current_price = None
    
    try:
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            price_match = re.search(r'(?:цена|Цена):\s*(\d+)', line)
            if price_match:
                current_price = int(price_match.group(1))
                continue

            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) == 3:
                    name, price, quantity = parts[0], int(parts[1]), int(parts[2])
                    cursor.execute("INSERT OR REPLACE INTO products (name, price, quantity) VALUES (?, ?, ?)", 
                                   (name, price, quantity))
                    added_count += 1
                continue

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

                if not is_available:
                    quantity = 0

                price = current_price if current_price is not None else 400
                
                cursor.execute("INSERT OR REPLACE INTO products (name, price, quantity) VALUES (?, ?, ?)", 
                               (name, price, quantity))
                added_count += 1

        conn.commit()
        await message.answer(f"✅ Успешно обработано и обновлено позиций: {added_count}")
        await message.answer(generate_stock_text(for_copy=False))
        
    except Exception as e:
        await message.answer(f"❌ Ошибка при обработке текста: {e}\nПроверь формат прайса.")
    finally:
        conn.close()

@dp.message(F.chat.id == MY_ID, Command("clear"))
async def clear_stock_cmd(message: Message):
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products")
    cursor.execute("DELETE FROM bookings")
    conn.commit()
    conn.close()
    await message.answer("🗑 **База данных полностью очищена!**")

@dp.callback_query(F.data.startswith("admin_"))
async def handle_admin_buttons(callback: CallbackQuery):
    action, booking_id = callback.data.split("_")[1:]
    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()

    if action == "sold":
        cursor.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
        conn.commit()
        await callback.message.edit_text(f"{callback.message.text}\n\n✅ <b>Статус: Продано! Товар списан.</b>", parse_mode="HTML")
        
    elif action == "cancel":
        cursor.execute("SELECT product_id FROM bookings WHERE id = ?", (booking_id,))
        res = cursor.fetchone()
        if res:
            product_id = res[0]
            cursor.execute("UPDATE products SET quantity = quantity + 1 WHERE id = ?", (product_id,))
            cursor.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
            conn.commit()
            await callback.message.edit_text(f"{callback.message.text}\n\n❌ <b>Статус: Бронь отменена.</b>", parse_mode="HTML")
            
    conn.close()

# --- ХЕНДЛЕРЫ СТАРТА ---
@dp.message(Command("start"))
async def start_cmd(message: Message):
    if message.from_user.id == MY_ID:
        admin_help_text = (
            f"Привет, босс! 👋\n"
            f"Ты в админке **ZKVR SHOP**.\n\n"
            f"🛠 **Твои команды:**\n"
            f"1️⃣ `/stock` — Посмотреть актуальный прайс.\n"
            f"2️⃣ `/update` — Обновить базу. Просто вставь весь свой прайс-лист сразу под командой!\n"
            f"3️⃣ `/clear` — Полная очистка базы.\n\n"
            f"⬇️ Текущая витрина для клиентов:"
        )
        await message.answer(admin_help_text, parse_mode="Markdown")
        await message.answer("Витрина для клиентов:", reply_markup=get_products_keyboard())
    else:
        await message.answer(
            f"Привет, {message.from_user.first_name}! 👋\n"
            f"Вот наше актуальное наличие на сегодня. Выбирай нужную позицию для моментальной брони!",
            reply_markup=get_products_keyboard()
        )

# Клик по кнопке товара клиентом
@dp.callback_query(F.data.startswith("buy_"))
async def handle_purchase(callback: CallbackQuery):
    product_id = callback.data.split("_")[1]
    user_id = callback.from_user.id
    raw_username = callback.from_user.username or "без_юзернейма"
    username = hd.quote(raw_username)

    conn = sqlite3.connect("shop_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, quantity FROM products WHERE id = ?", (product_id,))
    product = cursor.fetchone()
    
    if not product or product[2] <= 0:
        await callback.answer("Извини, этот вкус только что закончился! 😢", show_alert=True)
        await callback.message.edit_reply_markup(reply_markup=get_products_keyboard())
        conn.close()
        return

    p_name_raw, p_price, p_qty = product
    p_name = hd.quote(p_name_raw)

    cursor.execute("UPDATE products SET quantity = quantity - 1 WHERE id = ?", (product_id,))
    cursor.execute("INSERT INTO bookings (user_id, username, product_id) VALUES (?, ?, ?)", 
                   (user_id, raw_username, product_id))
    conn.commit()
    booking_id = cursor.lastrowid
    conn.close()

    await callback.message.answer(
        f"✅ <b>Отлично! Забронировано:</b> {p_name} ({p_price}₽).\n\n"
        f"Менеджер получил уведомление и скоро напишет тебе!",
        parse_mode="HTML"
    )
    await callback.answer()

    admin_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Продано", callback_data=f"admin_sold_{booking_id}"),
            InlineKeyboardButton(text="❌ Отмена брони", callback_data=f"admin_cancel_{booking_id}")
        ]
    ])
    
    client_link = f"https://t.me/{raw_username}" if raw_username != "без_юзернейма" else f"tg://user?id={user_id}"
    
    await bot.send_message(
        chat_id=MY_ID,
        text=f"🚨 <b>НОВЫЙ ЗАКАЗ!</b>\n\n"
             f"📦 <b>Товар:</b> {p_name} ({p_price}₽)\n"
             f"👤 <b>Покупатель:</b> @{username}\n\n"
             f"🔗 <a href='{client_link}'>НАЖМИ СЮДА, ЧТОБЫ НАПИСАТЬ КЛИЕНТУ</a>",
        reply_markup=admin_keyboard,
        parse_mode="HTML"
    )

# --- ЗАПУСК ---
async def main():
    try:
        import zoneinfo
        yekt_tz = zoneinfo.ZoneInfo("Asia/Yekaterinburg")
    except ImportError:
        from datetime import timezone, timedelta
        yekt_tz = timezone(timedelta(hours=5))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_to_top_shmot, "cron", hour=8, minute=0, timezone=yekt_tz)
    scheduler.add_job(send_to_top_shmot, "cron", hour=13, minute=0, timezone=yekt_tz)
    scheduler.add_job(send_to_top_shmot, "cron", hour=23, minute=0, timezone=yekt_tz)
    scheduler.start()

    print("Робот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())