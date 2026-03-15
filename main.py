import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, time
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
    ConversationHandler,
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


PEAK_FLOW, MEDICINE, EXTRA_INFO = range(3)
ADD_MEDICINE_NAME, ADD_MEDICINE_DOSE = range(3, 5)


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
    #  User Table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT,
            surname TEXT,
            birth_date date
        )
    """
    )

    # Medicine Table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS medicine (
            medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
            medicine_name TEXT,
            dose TEXT
        )
    """
    )

    # Taken Medicine table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS taken_medicine (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            medicine_id INTEGER,
            user_id INTEGER,
            doses INTEGER,
            date DATE,
            FOREIGN KEY(user_id) REFERENCES users(user_id),
            FOREIGN KEY(medicine_id) REFERENCES medicine(medicine_id)
        )
    """
    )

    # Extra Info Table
    c.execute(
        """
            CREATE TABLE IF NOT EXISTS extra_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                Date timestamp,
                Sport BOOLEAN,
                Sickness BOOLEAN,
                Stress BOOLEAN,
                Allergy BOOLEAN,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """
    )

    # Readings Table
    c.execute(
        """
            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                Date timestamp,
                "First try" REAL,
                "Second try" REAL,
                "Third try" REAL,
                Maximum REAL,
                "Green zone" REAL,
                "Yellow zone" REAL,
                "Red zone" REAL,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """
    )

    c.execute(
        """
            CREATE TRIGGER IF NOT EXISTS set_peak_flow_zones
            AFTER INSERT ON readings
            BEGIN
                -- Calculate the Maximum value from the last 20 readings for the user
                UPDATE readings
                SET
                    "Green zone" = (
                        SELECT MAX(Maximum) * 0.8
                        FROM (
                            SELECT Maximum
                            FROM readings
                            WHERE user_id = NEW.user_id
                            ORDER BY Date DESC
                            LIMIT 20
                        )
                    ),
                    "Yellow zone" = (
                        SELECT MAX(Maximum) * 0.5
                        FROM (
                            SELECT Maximum
                            FROM readings
                            WHERE user_id = NEW.user_id
                            ORDER BY Date DESC
                            LIMIT 20
                        )
                    ),
                    "Red zone" = 0
                WHERE user_id = NEW.user_id AND id = NEW.id;
            END;
        """
    )

    conn.commit()
    conn.close()


# Main reply keyboard
def main_reply_keyboard():
    keyboard = [
        [KeyboardButton("📝 Log Reading"), KeyboardButton("📊 Analysis")],
        [KeyboardButton("📈 Plot"), KeyboardButton("🔮 Predict")],
        [KeyboardButton("⏰ Set Reminder"), KeyboardButton("📤 Upload Data")],
        [KeyboardButton("💊 Add Medicine")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def main_inline_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📝 Log Reading", callback_data="📝 Log Reading"),
            InlineKeyboardButton("📊 Analysis", callback_data="📊 Analysis"),
        ],
        [
            InlineKeyboardButton("📈 Plot", callback_data="📈 Plot"),
            InlineKeyboardButton("🔮 Predict", callback_data="🔮 Predict"),
        ],
        [InlineKeyboardButton("⏰ Set Reminder", callback_data="⏰ Set Reminder")],
        [InlineKeyboardButton("📤 Upload Data", callback_data="📤 Upload Data")],
        [InlineKeyboardButton("💊 Add Medicine", callback_data="💊 Add Medicine")],
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
    first_name = update.message.from_user.first_name
    last_name = update.message.from_user.last_name

    conn = sqlite3.connect("peak_flow.db")
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO users (user_id, username, name, surname) VALUES (?, ?, ?, ?)",
        (user_id, username, first_name, last_name),
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"Добро пожаловать в Peak Flow Bot, {update.message.from_user.first_name}!\n"
        "Пожалуйста, выберите действие:",
        reply_markup=main_reply_keyboard(),
    )

    await set_daily_notification(update, context)


# Handle text messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "📝 Log Reading":
        await update.message.reply_text(
            "Пожалуйста, отправьте ваши показания пикфлоуметра, лечение и заметки в одном сообщении, разделяя "
            "пробелами.\nПример: `450 сальбутамол занимался спортом`"
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

    elif text == "📤 Upload Data":
        await update.message.reply_text(
            "Пожалуйста, загрузите файл с данными (CSV или Excel)."
        )
    elif text == "📝 Log Reading":
        return await start_entry(update, context)
    elif text == "💊 Add Medicine":
        return await start_add_medicine(update, context)


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
        await query.edit_message_text(
            "Главное меню:", reply_markup=main_inline_keyboard()
        )


# Start the conversation for adding medicine
async def start_add_medicine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please enter the name of the medicine:")
    return ADD_MEDICINE_NAME


# Handle medicine name input
async def handle_medicine_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    medicine_name = update.message.text
    context.user_data["medicine_name"] = medicine_name
    await update.message.reply_text(
        "Please enter the dose of the medicine (e.g., 100mg, 1 puff):"
    )
    return ADD_MEDICINE_DOSE


# Handle medicine dose input
async def handle_medicine_dose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dose = update.message.text

    # Save medicine to database
    medicine_name = context.user_data["medicine_name"]

    conn = sqlite3.connect("peak_flow.db")
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO medicine (medicine_name, dose)
        VALUES (?, ?)
    """,
        (medicine_name, dose),
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"Medicine saved successfully!\n" f"Name: {medicine_name}\n" f"Dose: {dose}\n"
    )

    # Clear user data
    context.user_data.clear()

    return ConversationHandler.END


# Start the conversation
async def start_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Please enter your 3 peak flow measurements separated by spaces (e.g., 450 460 470):"
    )
    return PEAK_FLOW


# Handle peak flow input
async def handle_peak_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.split()
    if len(user_input) != 3:
        await update.message.reply_text(
            "Invalid input. Please enter 3 peak flow measurements and the date (e.g., 450 460 470):"
        )
        return PEAK_FLOW

    try:
        user_id = update.message.from_user.id
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        peak_flow_1, peak_flow_2, peak_flow_3 = user_input
        maximum = max(float(peak_flow_1), float(peak_flow_2), float(peak_flow_3))
        context.user_data["peak_flow"] = {
            "first_try": float(peak_flow_1),
            "second_try": float(peak_flow_2),
            "third_try": float(peak_flow_3),
            "maximum": maximum,
            "date": date,
        }

        conn = sqlite3.connect("peak_flow.db")
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO readings (
                user_id, "First try", "Second try", "Third try", Maximum, Date
            ) VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                user_id,
                peak_flow_1,
                peak_flow_2,
                peak_flow_3,
                maximum,
                date,
            ),
        )
        conn.commit()

        # Check for low reading
        c.execute(
            """SELECT
                           "Green zone", "Yellow Zone"
                           FROM readings
                           WHERE user_id=?
                           ORDER BY Date desc""",
            (user_id,),
        )
        threshold = c.fetchone()

        if threshold and threshold[1] < maximum <= threshold[0]:
            await update.message.reply_text(
                f"⚠️ Внимание: Ваш пикфлоу ({maximum}) в жёлтой зоне (<{threshold[0]}). Необходимо наблюдение"
            )
        elif threshold and maximum <= threshold[1]:
            await update.message.reply_text(
                f"⚠️ Внимание: Ваш пикфлоу ({maximum}) в красной зоне (<{threshold[1]}). Необходимо консультация врача"
            )
        else:
            await update.message.reply_text(
                f"Ваш пикфлоу ({maximum}) в зелёной зоне (>{threshold[0]}). Состояние стабильно"
            )
        await update.message.reply_text(f"Сохранено: Максимальный пикфлоу={maximum}")

        c.execute(
            """SELECT medicine_name
                     FROM medicine
                 """,
        )
        medicines = [medicine[0] for medicine in c.fetchall()]

        conn.close()

    except ValueError:
        await update.message.reply_text(
            "Invalid input. Please enter 3 peak flow measurements(e.g., 450 460 470):"
        )
        return PEAK_FLOW

    await update.message.reply_text(
        f"Which medicine of the following: {', '.join(medicines)}, did you take today?"
    )
    return MEDICINE


# Handle medicine input
async def handle_medicine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    medicine = update.message.text.lower()
    user_id = update.message.from_user.id
    context.user_data["medicine"] = medicine

    conn = sqlite3.connect("peak_flow.db")
    c = conn.cursor()

    c.execute(
        """SELECT medicine_id
                 FROM medicine
                 WHERE medicine_name=?
             """,
        (medicine,),
    )

    medicine_id = c.fetchone()[0]

    c.execute(
        """
        INSERT INTO taken_medicine (
            medicine_id, user_id, doses, Date
        ) VALUES (?, ?, ?, ?)
    """,
        (
            medicine_id,
            user_id,
            "1",
            context.user_data["peak_flow"]["date"],
        ),
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        "Please enter any extra info (e.g., sport, stress, sickness, allergy, none):"
    )
    return EXTRA_INFO


# Handle extra info input
async def handle_extra_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    extra_info = update.message.text
    context.user_data["extra_info"] = extra_info

    # Save data to database
    user_id = update.message.from_user.id
    peak_flow_data = context.user_data["peak_flow"]
    medicine = context.user_data["medicine"]

    conn = sqlite3.connect("peak_flow.db")
    c = conn.cursor()

    c.execute(
        f"""
        INSERT INTO extra_info (
            user_id, Date, {extra_info.capitalize()}
        ) VALUES (?, ?, ?)
    """,
        (user_id, peak_flow_data["date"], True),
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"Data saved successfully!\n"
        f"Peak Flow: {peak_flow_data['first_try']}, {peak_flow_data['second_try']}, {peak_flow_data['third_try']}\n"
        f"Date: {peak_flow_data['date']}\n"
        f"Medicine: {medicine}\n"
        f"Extra Info: {extra_info}"
    )

    # Clear user data
    context.user_data.clear()

    return ConversationHandler.END


# Cancel and end conversation
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END


# Get analysis for a period
async def handle_analysis(query, context: ContextTypes.DEFAULT_TYPE, period: str):
    user_id = query.from_user.id
    period_map = {"week": "7 days", "month": "1 month", "3months": "3 months"}

    conn = sqlite3.connect("peak_flow.db")
    df = pd.read_sql(
        f"""
        SELECT Maximum, "symbicort turbuhaler", salbutamol, "relvar ellipta", "extra info", pulmicort, date
        FROM readings
        WHERE user_id=? AND date >= datetime('now', '-{period_map[period]}') AND  Maximum <> 0 and Maximum is not null
        ORDER BY date
    """,
        conn,
        params=(user_id,),
    )
    conn.close()

    if df.empty:
        await query.edit_message_text(f"Нет данных за последние {period_map[period]}.")
        return

    df["Date"] = pd.to_datetime(df["Date"], format="%Y-%m-%d %H:%M:%S")
    df["Extra info"] = df["Extra info"].str.lower()
    df["day_name"] = df["Date"].dt.day_name()
    df["Month"] = df["Date"].dt.month_name()
    df["Season"] = df["Month"].apply(get_season_name)

    avg = df["Maximum"].mean()
    min_val = df["Maximum"].min()
    max_val = df["Maximum"].max()

    df_encoded = pd.get_dummies(
        df, columns=["Extra info", "day_name", "Month", "Season"]
    )

    final_df = pd.concat([df, df_encoded], ignore_index=False)
    final_df = final_df.drop(
        columns=["Extra info", "day_name", "Month", "Season", "Date"]
    )
    corr_matrix = final_df.corr()["Maximum"].to_frame()
    plt.figure(figsize=(6, 10))  # Fix size
    sns.heatmap(corr_matrix, annot=True, cmap="coolwarm", fmt=".2f")
    plt.title("Correlation matrix")
    plot_path = "correlation_plot.png"
    plt.savefig(plot_path)
    plt.close()

    await context.bot.send_photo(
        chat_id=query.message.chat_id, photo=open(plot_path, "rb")
    )
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
    period_map = {"week": "7 days", "month": "1 month", "3months": "3 months"}

    conn = sqlite3.connect("peak_flow.db")
    df = pd.read_sql(
        f"""
        SELECT Maximum, date
        FROM readings
        WHERE user_id=? AND date >= date('now', '-{period_map[period]}') AND  Maximum <> 0 and Maximum is not null
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

    await context.bot.send_photo(
        chat_id=query.message.chat_id, photo=open(plot_path, "rb")
    )
    os.remove(plot_path)
    await query.edit_message_text(
        f"График за последние {period_map[period]}:",
        reply_markup=main_inline_keyboard(),
    )


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

    prediction = df["Maximum"].mean()  # Fix for a better prediction
    await update.message.reply_text(
        f"Прогноз пикфлоу на сегодня: {prediction:.1f}",
        reply_markup=main_reply_keyboard(),
    )


# Set up daily reminders
async def handle_set_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.job_queue.run_daily(
        send_reminder,
        time=time(hour=int(os.environ["NOTIFICATION_CRON_HOUR"]), minute=0),
        chat_id=update.message.chat_id,
    )
    await update.message.reply_text(
        "Напоминание установлено на 9 утра каждый день!",
        reply_markup=main_reply_keyboard(),
    )


async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        context.job.chat_id,
        text="📢 Напоминание: Не забудьте записать показания пикфлоуметра сегодня!",
    )


async def save_taken_medicine_from_xlsx(df, user_id, conn):
    c = conn.cursor()

    c.execute(
        "SELECT medicine_id, medicine_name FROM medicine",
    )
    medicines = {medicine[1]: medicine[0] for medicine in c.fetchall()}
    medicines_cols = list(medicines.keys()) + ["Date"]

    # Iterate over each row in the Excel file
    for _, row in df[medicines_cols].iterrows():
        # Get the date from the row
        date = row["Date"].date()

        # Iterate over each medicine column
        for medicine_name, doses in row.items():
            if medicine_name == "Date":
                continue  # Skip the date column

            if pd.isna(doses) or doses == 0:
                continue  # Skip if no doses were taken

            # Get the medicine_id from the medicine table
            medicine_id = medicines[medicine_name]

            if medicine_id is None:
                continue

            # Insert data into the taken_medicine table
            c.execute(
                """
                INSERT INTO taken_medicine (medicine_id, user_id, doses, date)
                VALUES (?, ?, ?, ?)
            """,
                (medicine_id, user_id, doses, date),
            )
            conn.commit()


async def save_extra_info_from_file(df, user_id, conn):
    extra_info_df = df[df["Extra info"].notna()][["Extra info", "Date"]]
    extra_info_df["Extra info"] = extra_info_df["Extra info"].str.capitalize()
    extra_info_df["Extra info"] = extra_info_df["Extra info"].str.replace(
        "Sick", "Sickness"
    )
    extra_info_df["Extra info"] = extra_info_df["Extra info"].str.split(",")
    c = conn.cursor()

    extra_info_cols = ["Sport", "Sickness", "Stress", "Allergy"]

    # Iterate over each row in the Excel file
    for _, row in extra_info_df.iterrows():
        # Get the date from the row
        date = row["Date"].date()
        extra_info = row["Extra info"]

        for e_i in extra_info:
            current_cols = {col: False for col in extra_info_cols}
            if e_i in extra_info_cols:
                current_cols[e_i] = True

            sql_query = f"""
                INSERT INTO extra_info (user_id, {", ".join(extra_info_cols)}, date)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            # Insert data into the extra_info table
            c.execute(
                sql_query,
                (
                    user_id,
                    current_cols["Sport"],
                    current_cols["Sickness"],
                    current_cols["Stress"],
                    current_cols["Allergy"],
                    date,
                ),
            )

            conn.commit()


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
        if file_path.endswith(".csv"):
            data = pd.read_csv(file_path)
        elif file_path.endswith((".xls", ".xlsx")):
            data = pd.read_excel(file_path)
        else:
            await update.message.reply_text(
                "Unsupported file format. Please upload a CSV or Excel file."
            )
            return

        data["Date"] = pd.to_datetime(data["Date"], format="%m/%d/%Y")
        data["user_id"] = [user_id] * data.shape[0]

        # Insert data into the database
        conn = sqlite3.connect("peak_flow.db")

        readings_cols = [
            "user_id",
            "Date",
            "First try",
            "Second try",
            "Third try",
            "Maximum",
            "Green zone",
            "Yellow zone",
            "Red zone",
            "Extra info",
        ]

        data[readings_cols].to_sql(
            "readings", conn, if_exists="append", index_label="id"
        )
        await save_taken_medicine_from_xlsx(data, user_id, conn)
        await save_extra_info_from_file(data, user_id, conn)
        conn.commit()
        conn.close()

        await update.message.reply_text("Data uploaded successfully!")
    except Exception as e:
        await update.message.reply_text(f"An error occurred: {e}")

    # Remove the temporary file
    os.remove(file_path)


# Function to send daily notifications
async def daily_notification(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    user_id = job.chat_id

    # Fetch user's peak flow data from the database
    conn = sqlite3.connect("peak_flow.db")
    df = pd.read_sql(
        f"""
        SELECT Maximum, date
        FROM readings
        WHERE user_id=? AND Maximum <> 0 AND Maximum is not Null
        ORDER BY date DESC
        LIMIT 30
    """,
        conn,
        params=(user_id,),
    )
    conn.close()

    if df.empty:
        await context.bot.send_message(
            chat_id=user_id, text="Нет достаточных данных для анализа."
        )
        return

    # Calculate statistics
    avg_peak_flow = df["Maximum"].mean()
    yesterday_peak_flow = df.iloc[0]["Maximum"] if len(df) > 0 else avg_peak_flow
    trend = (
        "лучше"
        if df["Maximum"].iloc[0] > df["Maximum"].iloc[-1]
        else "хуже"
        if len(df) > 1
        else "стабильно"
    )

    # Send the notification
    message = (
        f"📊 Ежедневный отчет:\n"
        f"Ожидаемое значение пикфлоу сегодня: {avg_peak_flow:.1f}\n"
        f"Вчерашнее значение: {yesterday_peak_flow:.1f}\n"
        f"Тренд: Сегодня ожидается {trend}, чем вчера."
    )
    await context.bot.send_message(chat_id=user_id, text=message)


# Command to set up daily notifications
async def set_daily_notification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    context.job_queue.run_daily(
        daily_notification,
        time=time(hour=int(os.environ["NOTIFICATION_CRON_HOUR"]), minute=0),
        chat_id=chat_id,
        name=str(chat_id),
    )
    await update.message.reply_text(
        f"Ежедневные уведомления настроены на {os.environ['NOTIFICATION_CRON_HOUR']}:00."
    )


# Main function
def main():
    init_db()
    application = Application.builder().token(os.environ["TOKEN"]).build()

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(r"^📝 Log Reading$"), start_entry)],
        states={
            PEAK_FLOW: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_peak_flow)
            ],
            MEDICINE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_medicine)
            ],
            EXTRA_INFO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_extra_info)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    add_medicine_conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^💊 Add Medicine$"), start_add_medicine)
        ],
        states={
            ADD_MEDICINE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_medicine_name)
            ],
            ADD_MEDICINE_DOSE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_medicine_dose)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(add_medicine_conv_handler)
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(CommandHandler("setnotification", set_daily_notification))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    application.run_polling()


if __name__ == "__main__":
    main()
