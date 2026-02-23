import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
import os
import logging
import seaborn as sns
from dotenv import load_dotenv

load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def get_season_name(month):
    if month in ["January", "February", "December"]:
        return "Winter"
    elif month in ["March", "April", "May"]:
        return "Spring"
    elif month in ["June", "July", "August"]:
        return "Summer"
    else:
        return "Autumn"


# Initialize SQLite database
def init_db():
    conn = sqlite3.connect("peak_flow.db")
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            threshold REAL DEFAULT 300
        )
    """
    )
    # Create the new readings table with updated schema
    c.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                first_try REAL,
                second_try REAL,
                third_try REAL,
                maximum REAL,
                date DATE,
                'symbicort turbuhaler' INTEGER,
                salbutamol INTEGER,
                'relvar ellipta' INTEGER,
                pulmicort INTEGER,
                green_zone REAL,
                yellow_zone REAL,
                red_zone REAL,
                'extra info' TEXT,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)
    conn.commit()
    conn.close()


# Main reply keyboard
def main_reply_keyboard():
    keyboard = [
        [KeyboardButton("📝 Log Reading"), KeyboardButton("📊 Analysis")],
        [KeyboardButton("📈 Plot"), KeyboardButton("🔮 Predict")],
        [KeyboardButton("⏰ Set Reminder"), KeyboardButton("⚠️ Set Threshold")],
        [KeyboardButton("📤 Upload Data")],  # New button for uploading data
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def main_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("📝 Log Reading", callback_data="📝 Log Reading"),
         InlineKeyboardButton("📊 Analysis", callback_data="📊 Analysis")],
        [InlineKeyboardButton("📈 Plot", callback_data="📈 Plot"),
         InlineKeyboardButton("🔮 Predict", callback_data="🔮 Predict")],
        [InlineKeyboardButton("⏰ Set Reminder", callback_data="⏰ Set Reminder"),
         InlineKeyboardButton("⚠️ Set Threshold", callback_data="⚠️ Set Threshold")],
        [InlineKeyboardButton("📤 Upload Data", callback_data="📤 Upload Data")],  # New button for uploading data
    ]
    return InlineKeyboardMarkup(keyboard)


# Period selection inline keyboard
def period_inline_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("Week", callback_data="period_week"),
            InlineKeyboardButton("Month", callback_data="period_month"),
        ],
        [InlineKeyboardButton("3 Months", callback_data="period_3months")],
        [InlineKeyboardButton("Back", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(keyboard)


# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    conn = sqlite3.connect("peak_flow.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

    await update.message.reply_text(
        "Добро пожаловать в Peak Flow Bot, Александр!\n"
        "Пожалуйста, выберите действие:",
        reply_markup=main_reply_keyboard(),
    )


# Handle text messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id

    if text == "📝 Log Reading":
        await update.message.reply_text(
            "Пожалуйста, отправьте ваши показания пикфлоуметра, лечение и заметки в одном сообщении, разделяя пробелами.\n"
            "Пример: `450 сальбутамол занимался спортом`"
        )
        context.user_data["awaiting_log"] = True

    elif text == "📊 Analysis":
        await update.message.reply_text(
            "Выберите период для анализа:",
            reply_markup=period_inline_keyboard(),
        )
        context.user_data["awaiting_period"] = "analysis"

    elif text == "📈 Plot":
        await update.message.reply_text(
            "Выберите период для графика:",
            reply_markup=period_inline_keyboard(),
        )
        context.user_data["awaiting_period"] = "plot"

    elif text == "🔮 Predict":
        await handle_predict(update, context)

    elif text == "⏰ Set Reminder":
        await handle_set_reminder(update, context)

    elif text == "⚠️ Set Threshold":
        await update.message.reply_text("Пожалуйста, отправьте значение порога (например, `300`).")
        context.user_data["awaiting_threshold"] = True

    elif text == "📤 Upload Data":
        await update.message.reply_text("Пожалуйста, загрузите файл с данными (CSV или Excel).")

    elif context.user_data.get("awaiting_log"):
        try:  # Add more data and a model to parse data
            args = update.message.text.split()
            peak_flow_metry = [int(args[0]), int(args[1]), int(args[2])]
            treatment = args[3] if len(args) > 3 else None
            notes = " ".join(args[4:]) if len(args) > 4 else None
            await handle_log_reading(update, context, peak_flow_metry, treatment, notes)
        except (ValueError, IndexError):
            await update.message.reply_text("Некорректный ввод. Пример: `450 сальбутамол занимался спортом`")
        context.user_data["awaiting_log"] = False

    elif context.user_data.get("awaiting_threshold"):
        try:
            threshold = float(update.message.text)
            await handle_set_threshold(update, context, threshold)
        except ValueError:
            await update.message.reply_text("Некорректное значение порога. Пожалуйста, введите число.")
        context.user_data["awaiting_threshold"] = False


# Handle button presses
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("period_"):
        period = query.data.split("_")[1]
        if context.user_data.get("awaiting_period") == "analysis":
            await handle_analysis(query, context, period)
        elif context.user_data.get("awaiting_period") == "plot":
            await handle_plot(query, context, period)

    elif query.data == "back_to_main":
        await query.edit_message_text("Главное меню:", reply_markup=main_inline_keyboard())


# Log a peak flow reading
async def handle_log_reading(update: Update, context: ContextTypes.DEFAULT_TYPE, peak_flow: list[int], treatment: str,
                             notes: str):
    user_id = update.message.from_user.id
    maximum = max(peak_flow)

    # Parse treatment and notes to extract medication and zone info
    symbicort = salbutamol = relvar = pulmicort = 0
    green_zone = yellow_zone = red_zone = None
    extra_info = notes

    # Example parsing logic (customize as needed)
    if treatment:
        if "symbicort" in treatment.lower():
            symbicort = 1
        if "salbutamol" in treatment.lower():
            salbutamol = 1
        if "relvar" in treatment.lower():
            relvar = 1
        if "pulmicort" in treatment.lower():
            pulmicort = 1

    # Get current date
    date = datetime.now().strftime("%m/%d/%Y")

    conn = sqlite3.connect('peak_flow.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO readings (
            user_id, first_try, second_try, third_try, maximum, date,
            'symbicort turbuhaler', salbutamol, 'relvar ellipta', pulmicort, green_zone,
            yellow_zone, red_zone, 'extra info'
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        user_id, peak_flow[0], peak_flow[1], peak_flow[2], maximum, date,
        symbicort, salbutamol, relvar, pulmicort, green_zone,
        yellow_zone, red_zone, extra_info
    ))

    conn.commit()

    # Check for low reading
    c.execute("SELECT threshold FROM users WHERE user_id=?", (user_id,))
    threshold = c.fetchone()
    if threshold and maximum < threshold[0]:
        await update.message.reply_text(
            f"⚠️ Внимание: Ваш пикфлоу ({maximum}) ниже порога ({threshold[0]})."
        )
    else:
        await update.message.reply_text(
            f"Сохранено: Максимальный пикфлоу={maximum}, Лечение={treatment}, Заметки={extra_info}"
        )
    conn.close()
    await update.message.reply_text("Главное меню:", reply_markup=main_reply_keyboard())


# Get analysis for a period
async def handle_analysis(query, context: ContextTypes.DEFAULT_TYPE, period: str):
    user_id = query.from_user.id
    period_map = {"week": "1 week", "month": "1 month", "3months": "3 months"}

    conn = sqlite3.connect("peak_flow.db")
    df = pd.read_sql(
        f"""
        SELECT maximum, "symbicort turbuhaler", salbutamol, "relvar ellipta", "extra info", pulmicort, date
        FROM readings
        WHERE user_id=? AND date >= datetime('now', '-{period_map[period]}') AND  maximum <> 0 and maximum is not null
        ORDER BY date
    """,
        conn,
        params=(user_id,),
    )
    conn.close()

    if df.empty:
        await query.edit_message_text(f"Нет данных за последние {period_map[period]}.")
        return

    df['Date'] = pd.to_datetime(df['Date'])
    df["Extra info"] = df["Extra info"].str.lower()
    df['day_name'] = df['Date'].dt.day_name()
    df["Month"] = df["Date"].dt.month_name()
    df["Season"] = df["Month"].apply(get_season_name)

    avg = df["Maximum"].mean()
    min_val = df["Maximum"].min()
    max_val = df["Maximum"].max()

    df_encoded = pd.get_dummies(df, columns=["Extra info", "day_name", "Month", "Season"])

    final_df = pd.concat([df, df_encoded], ignore_index=False)
    final_df = final_df.drop(columns=["Extra info", "day_name", "Month", "Season", "Date"])
    corr_matrix = final_df.corr()["Maximum"].to_frame()
    plt.figure(figsize=(6, 10))  # Fix size
    sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', fmt=".2f")
    plt.title("Correlation matrix")
    plot_path = "correlation_plot.png"
    plt.savefig(plot_path)
    plt.close()

    await context.bot.send_photo(chat_id=query.message.chat_id, photo=open(plot_path, "rb"))
    os.remove(plot_path)

    await query.edit_message_text(
        f"Анализ за последние {period_map[period]}:\n"
        f"Среднее: {avg:.1f}, Минимум: {min_val}, Максимум: {max_val}\n"
        f"Тренд: {'Улучшение' if df['Maximum'].iloc[-1] > df['Maximum'].iloc[0] else 'Ухудшение'}",
        reply_markup=main_inline_keyboard(),
    )


# Generate and send a plot
async def handle_plot(query, context: ContextTypes.DEFAULT_TYPE, period: str):
    user_id = query.from_user.id
    period_map = {"week": "1 week", "month": "1 month", "3months": "3 months"}

    conn = sqlite3.connect("peak_flow.db")
    df = pd.read_sql(
        f"""
        SELECT maximum, date
        FROM readings
        WHERE user_id=? AND date >= date('now', '-{period_map[period]}') AND  maximum <> 0 and maximum is not null
        ORDER BY date
    """,
        conn,
        params=(user_id,),
    )
    conn.close()

    if df.empty:
        await query.edit_message_text(f"Нет данных за последние {period_map[period]}.")
        return

    plt.figure(figsize=(8, 4))
    plt.plot(df["Date"], df["Maximum"], marker="o")
    plt.title(f"Динамика пикфлоу ({period_map[period]})")
    plt.xlabel("Дата")
    plt.ylabel("Пикфлоу")
    plt.grid()
    plot_path = "plot.png"
    plt.savefig(plot_path)
    plt.close()

    await context.bot.send_photo(chat_id=query.message.chat_id, photo=open(plot_path, "rb"))
    os.remove(plot_path)
    await query.edit_message_text(f"График за последние {period_map[period]}:", reply_markup=main_reply_keyboard())


# Predict today's peak flow
async def handle_predict(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    conn = sqlite3.connect("peak_flow.db")
    df = pd.read_sql(
        """
        SELECT Maximum, date
        FROM readings
        WHERE user_id=? AND Maximum <> 0 AND Maximum is not null
        ORDER BY date DESC
        LIMIT 31
    """,
        conn,
        params=(user_id,),
    )
    conn.close()

    if df.empty:
        await update.message.reply_text("Недостаточно данных для прогноза.")
        return

    prediction = df["Maximum"].mean() # Fix for a better prediction
    await update.message.reply_text(f"Прогноз пикфлоу на сегодня: {prediction:.1f}", reply_markup=main_reply_keyboard())


# Set up daily reminders
async def handle_set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.job_queue.run_daily(
        send_reminder,
        time=datetime.now().replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1),
        chat_id=update.message.chat_id,
    )
    await update.message.reply_text("Напоминание установлено на 9 утра каждый день!",
                                    reply_markup=main_reply_keyboard())


async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(context.job.chat_id,
                                   text="📢 Напоминание: Не забудьте записать показания пикфлоуметра сегодня!")


# Set alert threshold
async def handle_set_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE, threshold: float):
    user_id = update.message.from_user.id

    conn = sqlite3.connect("peak_flow.db")
    c = conn.cursor()
    c.execute("UPDATE users SET threshold=? WHERE user_id=?", (threshold, user_id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"Пороговое значение установлено: {threshold}", reply_markup=main_reply_keyboard())


# Handle document uploads
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    document = update.message.document

    # Download the file
    file = await context.bot.get_file(document.file_id)
    file_path = f"user_{user_id}_upload.{document.file_name.split('.')[-1]}"
    await file.download_to_drive(file_path)

    # Process the file
    try:
        if file_path.endswith('.csv'):
            data = pd.read_csv(file_path)
        elif file_path.endswith(('.xls', '.xlsx')):
            data = pd.read_excel(file_path)
        else:
            await update.message.reply_text("Unsupported file format. Please upload a CSV or Excel file.")
            return

        data['Date'] = pd.to_datetime(data["Date"], format='%m/%d/%Y')
        data["user_id"] = [user_id] * data.shape[0]
        # Insert data into the database
        conn = sqlite3.connect('peak_flow.db')

        data.to_sql("readings", conn, if_exists="replace")

        conn.commit()
        conn.close()

        await update.message.reply_text("Data uploaded successfully!")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {e}")

    # Remove the temporary file
    os.remove(file_path)


# Main function
def main():
    init_db()
    application = Application.builder().token(os.environ["TOKEN"]).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    application.run_polling()


if __name__ == "__main__":
    main()
