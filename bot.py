import os
import logging
import sqlite3
from datetime import datetime, date, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

DB_PATH = "fleet.db"

CARS = ["Авто 1", "Авто 2", "Авто 3", "Авто 4", "Авто 5"]

# Conversation states
(SELECT_CAR, SELECT_ACTION, 
 FUEL_LITERS, FUEL_PRICE, FUEL_STATION, FUEL_COUNTRY,
 DOC_TYPE, DOC_DATE,
 EXPENSE_TYPE, EXPENSE_AMOUNT, EXPENSE_DESC,
 ROUTE_DEST, ROUTE_CARGO, ROUTE_FREIGHT, ROUTE_END,
 MILEAGE_KM) = range(16)

DOC_TYPES = {
    "insurance_ua": "🇺🇦 Страховка UA",
    "insurance_eu": "🇪🇺 Страховка EU (Зелена карта)",
    "tech_check": "🔧 Техогляд",
    "tacho": "📟 Тахограф",
    "rmpd": "📄 РМПД",
    "cert_eur": "📋 Сертифікат EUR",
}

EXPENSE_TYPES = {
    "fuel": "⛽ Паливо",
    "repair": "🔧 Ремонт",
    "fine": "⚠️ Штраф",
    "wash": "🚿 Мийка",
    "other": "📦 Інше",
}

# ─── DATABASE ────────────────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute("""CREATE TABLE IF NOT EXISTS fuel (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        car TEXT, date TEXT, liters REAL, price_per_liter REAL,
        total REAL, station TEXT, country TEXT, mileage INTEGER
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        car TEXT, doc_type TEXT, expiry_date TEXT,
        UNIQUE(car, doc_type)
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        car TEXT, date TEXT, expense_type TEXT,
        amount REAL, description TEXT
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS routes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        car TEXT, start_date TEXT, end_date TEXT,
        destination TEXT, cargo TEXT, freight REAL,
        mileage INTEGER, status TEXT DEFAULT 'active'
    )""")
    
    c.execute("""CREATE TABLE IF NOT EXISTS mileage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        car TEXT, date TEXT, km INTEGER
    )""")
    
    conn.commit()
    conn.close()

def db():
    return sqlite3.connect(DB_PATH)

# ─── KEYBOARDS ───────────────────────────────────────────────────────

def main_keyboard():
    buttons = [
        ["⛽ Заправка", "📋 Документи"],
        ["💰 Витрати", "🗺 Рейс"],
        ["📊 Зведення", "⚠️ Дедлайни"],
        ["🚗 Пробіг", "❓ Допомога"],
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def cars_keyboard(action=""):
    buttons = []
    row = []
    for i, car in enumerate(CARS):
        row.append(InlineKeyboardButton(car, callback_data=f"car_{i}_{action}"))
        if len(row) == 2 or i == len(CARS) - 1:
            buttons.append(row)
            row = []
    return InlineKeyboardMarkup(buttons)

def doc_types_keyboard(car_idx):
    buttons = []
    for key, label in DOC_TYPES.items():
        buttons.append([InlineKeyboardButton(label, callback_data=f"doc_{car_idx}_{key}")])
    buttons.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)

def expense_types_keyboard(car_idx):
    buttons = []
    row = []
    for key, label in EXPENSE_TYPES.items():
        row.append(InlineKeyboardButton(label, callback_data=f"exp_{car_idx}_{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Скасувати", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)

# ─── HELPERS ─────────────────────────────────────────────────────────

def days_until(date_str):
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        return (d - date.today()).days
    except:
        return None

def format_days(days):
    if days is None:
        return "❓ не вказано"
    if days < 0:
        return f"🔴 ПРОСТРОЧЕНО ({abs(days)} дн. тому)"
    if days <= 7:
        return f"🔴 {days} дн."
    if days <= 14:
        return f"🟡 {days} дн."
    if days <= 30:
        return f"🟠 {days} дн."
    return f"🟢 {days} дн."

def is_admin(user_id):
    return ADMIN_ID == 0 or user_id == ADMIN_ID

# ─── COMMAND HANDLERS ────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Немає доступу.")
        return
    
    text = (
        "🚛 *Fleet Tracker Bot*\n"
        "Гданськ — Київ — Гданськ\n\n"
        "Вибери дію в меню нижче 👇"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=main_keyboard())

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Команди бота:*\n\n"
        "⛽ *Заправка* — записати заправку\n"
        "📋 *Документи* — оновити дату документа\n"
        "💰 *Витрати* — записати витрату\n"
        "🗺 *Рейс* — почати або завершити рейс\n"
        "📊 *Зведення* — статистика по авто\n"
        "⚠️ *Дедлайни* — документи що закінчуються\n"
        "🚗 *Пробіг* — записати пробіг\n\n"
        "💡 Щодня о 9:00 бот сам перевіряє дедлайни."
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ─── FUEL FLOW ───────────────────────────────────────────────────────

async def fuel_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⛽ *Нова заправка*\nВибери авто:",
        parse_mode="Markdown",
        reply_markup=cars_keyboard("fuel")
    )

async def fuel_car_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    car_idx = int(parts[1])
    ctx.user_data["fuel_car"] = CARS[car_idx]
    ctx.user_data["fuel_car_idx"] = car_idx
    
    await query.edit_message_text(
        f"⛽ Заправка — *{CARS[car_idx]}*\n\nСкільки літрів залив? (наприклад: 150)",
        parse_mode="Markdown"
    )
    return FUEL_LITERS

async def fuel_liters(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        liters = float(update.message.text.replace(",", "."))
        ctx.user_data["fuel_liters"] = liters
        await update.message.reply_text(f"✅ {liters} л\n\nЦіна за літр? (наприклад: 52.5)")
        return FUEL_PRICE
    except:
        await update.message.reply_text("❌ Введи число, наприклад: 150")
        return FUEL_LITERS

async def fuel_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.replace(",", "."))
        ctx.user_data["fuel_price"] = price
        liters = ctx.user_data["fuel_liters"]
        total = liters * price
        ctx.user_data["fuel_total"] = total
        await update.message.reply_text(
            f"✅ {price} грн/л → Сума: *{total:.0f} грн*\n\nНазва АЗС? (або напиши `-` щоб пропустити)",
            parse_mode="Markdown"
        )
        return FUEL_STATION
    except:
        await update.message.reply_text("❌ Введи число, наприклад: 52.5")
        return FUEL_PRICE

async def fuel_station(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    station = update.message.text
    ctx.user_data["fuel_station"] = "" if station == "-" else station
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇺🇦 Україна", callback_data="country_UA"),
         InlineKeyboardButton("🇵🇱 Польща", callback_data="country_PL")],
        [InlineKeyboardButton("🇩🇪 Німеччина", callback_data="country_DE"),
         InlineKeyboardButton("🌍 Інша", callback_data="country_Other")]
    ])
    await update.message.reply_text("Країна заправки?", reply_markup=kb)
    return FUEL_COUNTRY

async def fuel_country(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    country = query.data.replace("country_", "")
    ctx.user_data["fuel_country"] = country
    
    car = ctx.user_data["fuel_car"]
    liters = ctx.user_data["fuel_liters"]
    price = ctx.user_data["fuel_price"]
    total = ctx.user_data["fuel_total"]
    station = ctx.user_data.get("fuel_station", "")
    
    conn = db()
    conn.execute(
        "INSERT INTO fuel (car, date, liters, price_per_liter, total, station, country) VALUES (?,?,?,?,?,?,?)",
        (car, date.today().isoformat(), liters, price, total, station, country)
    )
    conn.commit()
    conn.close()
    
    await query.edit_message_text(
        f"✅ *Заправка збережена!*\n\n"
        f"🚗 {car}\n"
        f"⛽ {liters} л × {price} грн = *{total:.0f} грн*\n"
        f"📍 {station or '—'} | {country}\n"
        f"📅 {date.today().strftime('%d.%m.%Y')}",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ─── DOCUMENTS FLOW ──────────────────────────────────────────────────

async def docs_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *Документи*\nВибери авто:",
        parse_mode="Markdown",
        reply_markup=cars_keyboard("doc")
    )

async def doc_car_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    car_idx = int(query.data.split("_")[1])
    ctx.user_data["doc_car"] = CARS[car_idx]
    ctx.user_data["doc_car_idx"] = car_idx
    
    await query.edit_message_text(
        f"📋 *{CARS[car_idx]}*\nВибери документ:",
        parse_mode="Markdown",
        reply_markup=doc_types_keyboard(car_idx)
    )

async def doc_type_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    car_idx = int(parts[1])
    doc_type = parts[2]
    ctx.user_data["doc_type"] = doc_type
    ctx.user_data["doc_car"] = CARS[car_idx]
    
    label = DOC_TYPES.get(doc_type, doc_type)
    await query.edit_message_text(
        f"📋 *{CARS[car_idx]}* — {label}\n\n"
        f"Введи дату закінчення у форматі *ДД.ММ.РРРР*\n"
        f"Наприклад: 15.08.2025",
        parse_mode="Markdown"
    )
    return DOC_DATE

async def doc_date_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        d = datetime.strptime(text, "%d.%m.%Y").date()
        car = ctx.user_data["doc_car"]
        doc_type = ctx.user_data["doc_type"]
        label = DOC_TYPES.get(doc_type, doc_type)
        
        conn = db()
        conn.execute(
            "INSERT OR REPLACE INTO documents (car, doc_type, expiry_date) VALUES (?,?,?)",
            (car, doc_type, d.isoformat())
        )
        conn.commit()
        conn.close()
        
        days = days_until(d.isoformat())
        await update.message.reply_text(
            f"✅ *Збережено!*\n\n"
            f"🚗 {car}\n"
            f"📄 {label}\n"
            f"📅 Дійсний до: *{text}*\n"
            f"⏳ Залишилось: {format_days(days)}",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("❌ Невірний формат. Введи як: 15.08.2025")
        return DOC_DATE

# ─── EXPENSES FLOW ───────────────────────────────────────────────────

async def expense_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "💰 *Нова витрата*\nВибери авто:",
        parse_mode="Markdown",
        reply_markup=cars_keyboard("exp")
    )

async def expense_car_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    car_idx = int(query.data.split("_")[1])
    ctx.user_data["exp_car"] = CARS[car_idx]
    
    await query.edit_message_text(
        f"💰 *{CARS[car_idx]}*\nВибери тип витрати:",
        parse_mode="Markdown",
        reply_markup=expense_types_keyboard(car_idx)
    )

async def expense_type_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    exp_type = parts[2]
    ctx.user_data["exp_type"] = exp_type
    label = EXPENSE_TYPES.get(exp_type, exp_type)
    
    await query.edit_message_text(
        f"💰 {label}\n\nСума в гривнях?",
        parse_mode="Markdown"
    )
    return EXPENSE_AMOUNT

async def expense_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.replace(",", "."))
        ctx.user_data["exp_amount"] = amount
        await update.message.reply_text(
            f"✅ {amount:.0f} грн\n\nКороткий опис (або `-` щоб пропустити):"
        )
        return EXPENSE_DESC
    except:
        await update.message.reply_text("❌ Введи число, наприклад: 3500")
        return EXPENSE_AMOUNT

async def expense_desc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    desc = update.message.text
    car = ctx.user_data["exp_car"]
    exp_type = ctx.user_data["exp_type"]
    amount = ctx.user_data["exp_amount"]
    label = EXPENSE_TYPES.get(exp_type, exp_type)
    
    conn = db()
    conn.execute(
        "INSERT INTO expenses (car, date, expense_type, amount, description) VALUES (?,?,?,?,?)",
        (car, date.today().isoformat(), exp_type, amount, "" if desc == "-" else desc)
    )
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"✅ *Витрата збережена!*\n\n"
        f"🚗 {car}\n"
        f"{label}: *{amount:.0f} грн*\n"
        f"📝 {desc if desc != '-' else '—'}\n"
        f"📅 {date.today().strftime('%d.%m.%Y')}",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    return ConversationHandler.END

# ─── ROUTES FLOW ─────────────────────────────────────────────────────

async def route_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = db()
    active = conn.execute("SELECT car, destination, start_date FROM routes WHERE status='active'").fetchall()
    conn.close()
    
    if active:
        text = "🗺 *Активні рейси:*\n\n"
        for r in active:
            text += f"🚗 {r[0]} → {r[1]} (з {r[2]})\n"
        text += "\nЩо зробити?"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🆕 Новий рейс", callback_data="route_new"),
             InlineKeyboardButton("✅ Завершити рейс", callback_data="route_end")]
        ])
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(
            "🗺 *Новий рейс*\nВибери авто:",
            parse_mode="Markdown",
            reply_markup=cars_keyboard("route")
        )

async def route_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🗺 *Новий рейс*\nВибери авто:",
        parse_mode="Markdown",
        reply_markup=cars_keyboard("route")
    )

async def route_car_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    car_idx = int(query.data.split("_")[1])
    ctx.user_data["route_car"] = CARS[car_idx]
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🇵🇱 Гданськ → 🇺🇦 Київ", callback_data="dest_Гданськ→Київ"),
         InlineKeyboardButton("🇺🇦 Київ → 🇵🇱 Гданськ", callback_data="dest_Київ→Гданськ")]
    ])
    await query.edit_message_text(
        f"🗺 *{CARS[car_idx]}*\nМаршрут:",
        parse_mode="Markdown",
        reply_markup=kb
    )

async def route_dest_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    dest = query.data.replace("dest_", "")
    ctx.user_data["route_dest"] = dest
    
    await query.edit_message_text(
        f"🗺 Маршрут: *{dest}*\n\nЩо везеш? (вантаж або `-`)",
        parse_mode="Markdown"
    )
    return ROUTE_CARGO

async def route_cargo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["route_cargo"] = update.message.text
    await update.message.reply_text("Сума фрахту в грн? (або `-` якщо невідомо)")
    return ROUTE_FREIGHT

async def route_freight(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    freight = 0
    if text != "-":
        try:
            freight = float(text.replace(",", "."))
        except:
            pass
    
    car = ctx.user_data["route_car"]
    dest = ctx.user_data["route_dest"]
    cargo = ctx.user_data["route_cargo"]
    
    conn = db()
    conn.execute(
        "INSERT INTO routes (car, start_date, destination, cargo, freight) VALUES (?,?,?,?,?)",
        (car, date.today().isoformat(), dest, cargo, freight)
    )
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"✅ *Рейс розпочато!*\n\n"
        f"🚗 {car}\n"
        f"🗺 {dest}\n"
        f"📦 {cargo}\n"
        f"💰 {freight:.0f} грн\n"
        f"📅 {date.today().strftime('%d.%m.%Y')}",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )
    return ConversationHandler.END

async def route_end_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    conn = db()
    active = conn.execute("SELECT id, car, destination, start_date FROM routes WHERE status='active'").fetchall()
    conn.close()
    
    if not active:
        await query.edit_message_text("Немає активних рейсів.")
        return ConversationHandler.END
    
    buttons = []
    for r in active:
        buttons.append([InlineKeyboardButton(
            f"{r[1]} → {r[2]}",
            callback_data=f"endroute_{r[0]}"
        )])
    await query.edit_message_text(
        "Який рейс завершити?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def route_end_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    route_id = int(query.data.split("_")[1])
    
    conn = db()
    conn.execute("UPDATE routes SET status='done', end_date=? WHERE id=?",
                 (date.today().isoformat(), route_id))
    r = conn.execute("SELECT car, destination FROM routes WHERE id=?", (route_id,)).fetchone()
    conn.commit()
    conn.close()
    
    await query.edit_message_text(
        f"✅ *Рейс завершено!*\n\n🚗 {r[0]} → {r[1]}\n📅 {date.today().strftime('%d.%m.%Y')}",
        parse_mode="Markdown"
    )

# ─── MILEAGE FLOW ────────────────────────────────────────────────────

async def mileage_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚗 *Пробіг*\nВибери авто:",
        parse_mode="Markdown",
        reply_markup=cars_keyboard("km")
    )

async def mileage_car_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    car_idx = int(query.data.split("_")[1])
    ctx.user_data["km_car"] = CARS[car_idx]
    
    conn = db()
    last = conn.execute(
        "SELECT km, date FROM mileage WHERE car=? ORDER BY id DESC LIMIT 1",
        (CARS[car_idx],)
    ).fetchone()
    conn.close()
    
    hint = f"\nОстанній запис: *{last[0]:,} км* ({last[1]})" if last else ""
    await query.edit_message_text(
        f"🚗 *{CARS[car_idx]}*{hint}\n\nВведи поточний пробіг (км):",
        parse_mode="Markdown"
    )
    return MILEAGE_KM

async def mileage_km(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        km = int(update.message.text.replace(" ", "").replace(",", ""))
        car = ctx.user_data["km_car"]
        
        conn = db()
        last = conn.execute(
            "SELECT km FROM mileage WHERE car=? ORDER BY id DESC LIMIT 1", (car,)
        ).fetchone()
        conn.execute(
            "INSERT INTO mileage (car, date, km) VALUES (?,?,?)",
            (car, date.today().isoformat(), km)
        )
        conn.commit()
        conn.close()
        
        diff = f" (+{km - last[0]:,} км з минулого разу)" if last else ""
        await update.message.reply_text(
            f"✅ *Пробіг збережено!*\n\n🚗 {car}\n📏 *{km:,} км*{diff}",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
        return ConversationHandler.END
    except:
        await update.message.reply_text("❌ Введи ціле число, наприклад: 245000")
        return MILEAGE_KM

# ─── DEADLINES ───────────────────────────────────────────────────────

async def deadlines(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = db()
    docs = conn.execute("SELECT car, doc_type, expiry_date FROM documents ORDER BY car, doc_type").fetchall()
    conn.close()
    
    if not docs:
        await update.message.reply_text(
            "📋 Документи ще не внесені.\n\nВибери *📋 Документи* щоб додати дати.",
            parse_mode="Markdown"
        )
        return
    
    text = "⚠️ *СТАТУС ДОКУМЕНТІВ*\n\n"
    current_car = None
    
    for doc in docs:
        car, doc_type, expiry = doc
        if car != current_car:
            text += f"\n🚗 *{car}*\n"
            current_car = car
        
        label = DOC_TYPES.get(doc_type, doc_type)
        days = days_until(expiry)
        expiry_fmt = datetime.strptime(expiry, "%Y-%m-%d").strftime("%d.%m.%Y")
        text += f"  {label}: {expiry_fmt} — {format_days(days)}\n"
    
    # Missing docs
    all_cars_docs = {(d[0], d[1]) for d in docs}
    missing = []
    for car in CARS:
        for doc_type in DOC_TYPES:
            if (car, doc_type) not in all_cars_docs:
                missing.append(f"  🚗 {car} — {DOC_TYPES[doc_type]}")
    
    if missing:
        text += f"\n❓ *Не внесені:*\n" + "\n".join(missing[:10])
    
    await update.message.reply_text(text, parse_mode="Markdown")

# ─── SUMMARY ─────────────────────────────────────────────────────────

async def summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📊 *Зведення*\nВибери авто:",
        parse_mode="Markdown",
        reply_markup=cars_keyboard("summary")
    )

async def summary_car(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    car_idx = int(query.data.split("_")[1])
    car = CARS[car_idx]
    
    conn = db()
    
    # Current month
    month = date.today().strftime("%Y-%m")
    
    fuel = conn.execute(
        "SELECT SUM(liters), SUM(total) FROM fuel WHERE car=? AND date LIKE ?",
        (car, f"{month}%")
    ).fetchone()
    
    expenses = conn.execute(
        "SELECT expense_type, SUM(amount) FROM expenses WHERE car=? AND date LIKE ? GROUP BY expense_type",
        (car, f"{month}%")
    ).fetchall()
    
    mileage_last = conn.execute(
        "SELECT km FROM mileage WHERE car=? ORDER BY id DESC LIMIT 1", (car,)
    ).fetchone()
    
    routes_count = conn.execute(
        "SELECT COUNT(*) FROM routes WHERE car=? AND status='done' AND start_date LIKE ?",
        (car, f"{month}%")
    ).fetchone()
    
    docs = conn.execute(
        "SELECT doc_type, expiry_date FROM documents WHERE car=?", (car,)
    ).fetchall()
    
    conn.close()
    
    now = date.today().strftime("%m.%Y")
    text = f"📊 *{car}* — {now}\n\n"
    
    text += "⛽ *Паливо:*\n"
    if fuel[0]:
        text += f"  {fuel[0]:.0f} л | {fuel[1]:.0f} грн\n"
    else:
        text += "  немає записів\n"
    
    text += "\n💰 *Витрати:*\n"
    total_exp = 0
    if expenses:
        for exp_type, amount in expenses:
            label = EXPENSE_TYPES.get(exp_type, exp_type)
            text += f"  {label}: {amount:.0f} грн\n"
            total_exp += amount
        text += f"  ─────────\n  Разом: *{total_exp:.0f} грн*\n"
    else:
        text += "  немає записів\n"
    
    text += f"\n🗺 *Рейсів цього місяця:* {routes_count[0]}\n"
    
    if mileage_last:
        text += f"📏 *Поточний пробіг:* {mileage_last[0]:,} км\n"
    
    if docs:
        text += "\n📋 *Документи:*\n"
        for doc_type, expiry in docs:
            label = DOC_TYPES.get(doc_type, doc_type)
            days = days_until(expiry)
            text += f"  {label}: {format_days(days)}\n"
    
    await query.edit_message_text(text, parse_mode="Markdown")

# ─── AUTO NOTIFICATIONS ──────────────────────────────────────────────

async def check_deadlines_job(ctx: ContextTypes.DEFAULT_TYPE):
    if ADMIN_ID == 0:
        return
    
    conn = db()
    docs = conn.execute("SELECT car, doc_type, expiry_date FROM documents").fetchall()
    conn.close()
    
    urgent = []
    for car, doc_type, expiry in docs:
        days = days_until(expiry)
        if days is not None and days <= 30:
            label = DOC_TYPES.get(doc_type, doc_type)
            expiry_fmt = datetime.strptime(expiry, "%Y-%m-%d").strftime("%d.%m.%Y")
            urgent.append((days, car, label, expiry_fmt))
    
    if urgent:
        urgent.sort()
        text = "🔔 *Перевірка дедлайнів*\n\n"
        for days, car, label, expiry in urgent:
            text += f"🚗 {car} — {label}\n  📅 {expiry} — {format_days(days)}\n\n"
        
        await ctx.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="Markdown")

# ─── CANCEL ──────────────────────────────────────────────────────────

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("❌ Скасовано.")
    else:
        await update.message.reply_text("❌ Скасовано.", reply_markup=main_keyboard())
    ctx.user_data.clear()
    return ConversationHandler.END

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    text = update.message.text
    if text == "⛽ Заправка":
        await fuel_start(update, ctx)
    elif text == "📋 Документи":
        await docs_start(update, ctx)
    elif text == "💰 Витрати":
        await expense_start(update, ctx)
    elif text == "🗺 Рейс":
        await route_start(update, ctx)
    elif text == "📊 Зведення":
        await summary(update, ctx)
    elif text == "⚠️ Дедлайни":
        await deadlines(update, ctx)
    elif text == "🚗 Пробіг":
        await mileage_start(update, ctx)
    elif text == "❓ Допомога":
        await help_cmd(update, ctx)

# ─── MAIN ────────────────────────────────────────────────────────────

def main():
    init_db()
    
    app = Application.builder().token(TOKEN).build()
    
    # Fuel conversation
    fuel_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(fuel_car_selected, pattern=r"^car_\d+_fuel$")],
        states={
            FUEL_LITERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, fuel_liters)],
            FUEL_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, fuel_price)],
            FUEL_STATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, fuel_station)],
            FUEL_COUNTRY: [CallbackQueryHandler(fuel_country, pattern=r"^country_")],
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern="^cancel$"),
                   CommandHandler("cancel", cancel)],
    )
    
    # Documents conversation
    doc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(doc_type_selected, pattern=r"^doc_\d+_")],
        states={
            DOC_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, doc_date_input)],
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern="^cancel$"),
                   CommandHandler("cancel", cancel)],
    )
    
    # Expenses conversation
    exp_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(expense_type_selected, pattern=r"^exp_\d+_")],
        states={
            EXPENSE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, expense_amount)],
            EXPENSE_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, expense_desc)],
        },
        fallbacks=[CallbackQueryHandler(cancel, pattern="^cancel$"),
                   CommandHandler("cancel", cancel)],
    )
    
    # Routes conversation
    route_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(route_car_selected, pattern=r"^car_\d+_route$"),
            CallbackQueryHandler(route_new, pattern="^route_new$"),
        ],
        states={
            ROUTE_CARGO: [MessageHandler(filters.TEXT & ~filters.COMMAND, route_cargo)],
            ROUTE_FREIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, route_freight)],
        },
        fallbacks=[
            CallbackQueryHandler(route_dest_selected, pattern=r"^dest_"),
            CallbackQueryHandler(cancel, pattern="^cancel$"),
            CommandHandler("cancel", cancel)
        ],
    )
    
    # Mileage conversation
    km_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(mileage_car_selected, pattern=r"^car_\d+_km$")],
        states={
            MILEAGE_KM: [MessageHandler(filters.TEXT & ~filters.COMMAND, mileage_km)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(fuel_conv)
    app.add_handler(doc_conv)
    app.add_handler(exp_conv)
    app.add_handler(route_conv)
    app.add_handler(km_conv)
    
    # Car selection handlers
    app.add_handler(CallbackQueryHandler(fuel_car_selected, pattern=r"^car_\d+_fuel$"))
    app.add_handler(CallbackQueryHandler(doc_car_selected, pattern=r"^car_\d+_doc$"))
    app.add_handler(CallbackQueryHandler(expense_car_selected, pattern=r"^car_\d+_exp$"))
    app.add_handler(CallbackQueryHandler(route_car_selected, pattern=r"^car_\d+_route$"))
    app.add_handler(CallbackQueryHandler(mileage_car_selected, pattern=r"^car_\d+_km$"))
    app.add_handler(CallbackQueryHandler(summary_car, pattern=r"^car_\d+_summary$"))
    
    # Route handlers
    app.add_handler(CallbackQueryHandler(route_end_select, pattern="^route_end$"))
    app.add_handler(CallbackQueryHandler(route_end_confirm, pattern=r"^endroute_\d+$"))
    app.add_handler(CallbackQueryHandler(route_dest_selected, pattern=r"^dest_"))
    app.add_handler(CallbackQueryHandler(cancel, pattern="^cancel$"))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Daily deadline check at 9:00
    if ADMIN_ID != 0:
        app.job_queue.run_daily(
            check_deadlines_job,
            time=datetime.strptime("09:00", "%H:%M").time()
        )
    
    logger.info("Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
