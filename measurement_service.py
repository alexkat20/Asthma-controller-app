import logging

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from dotenv import load_dotenv
import os
from repositories.daily_measurement_repo import save_daily_measurements
from repositories.medicine_repo import save_medicine

load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

CHOOSING, MEASUREMENTS_REPLY, TYPING_CHOICE, MEDICINE_CHOICE, MEDICINE_REPLY = range(5)

reply_keyboard = [
    ["Enter daily measurements", "Get graphics for a period of time"],
    ["Additional info"],
    ["Done"],
]

medicine_keyboard = [["Symbicort Turbuhaler", "Salbutamol 1 inhale"],
                     ["Relvar Ellipta 22/184", "Pulmicort"],
                     ["Done"]]

medicines = []
for meds in medicine_keyboard[:len(medicine_keyboard)-1]:
    medicines += meds

medicines_str = "|".join(medicines)

markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)

medicine_markup = ReplyKeyboardMarkup(medicine_keyboard, one_time_keyboard=True)


def facts_to_str(user_data: dict[str, str]) -> str:
    """Helper function for formatting the gathered user info."""
    facts = [f"{key} - {value}" for key, value in user_data.items()]
    return "\n".join(facts).join(["\n", "\n"])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask user for input."""
    await update.message.reply_text(
        "Hi! I am Asthma controller bot. Here you can log your daily measurements,"
        " get notifications and see graphics and facts about your state",
        reply_markup=markup,
    )

    return CHOOSING


async def log_daily_measurements(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ask the user for info about the selected predefined choice."""
    text = update.message.text
    context.user_data["choice"] = text
    await update.message.reply_text("Let's log in your daily measurements in the following order:"
                                    "First measurement, second measurement, third measurement")

    return MEASUREMENTS_REPLY


async def received_information(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store info provided by user and ask for the next category."""
    user_data = context.user_data

    text = update.message.text
    category = user_data["choice"]
    user_data[category] = text
    del user_data["choice"]

    data = [int(measurement) for measurement in text.split()]

    #  await save_daily_measurements(username="test123", measurements=data)

    await update.message.reply_text(
        "Your today's data:"
        f" {data}. Next, press the button for medicine",
        reply_markup=medicine_markup,
    )

    return MEDICINE_CHOICE


async def choose_medicine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text

    #  await save_medicine(medicine=text)
    await update.message.reply_text(
        f"You have logged {text}. If you want to log more, press the according medicine again",
        reply_markup=medicine_markup,
    )
    return MEDICINE_CHOICE


async def finish_daily_logging(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask user for input."""
    await update.message.reply_text(
        "Let's go back",
        reply_markup=markup,
    )

    return CHOOSING


async def done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display the gathered info and end the conversation."""
    user_data = context.user_data
    if "choice" in user_data:
        del user_data["choice"]

    await update.message.reply_text(
        f"I learned these facts about you: {facts_to_str(user_data)}Until next time!",
        reply_markup=ReplyKeyboardRemove(),
    )

    user_data.clear()
    return ConversationHandler.END


def main() -> None:
    """Run the bot."""
    application = Application.builder().token(os.environ["TOKEN"]).build()

    # Add conversation handler with the states CHOOSING, TYPING_CHOICE and TYPING_REPLY
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING: [
                MessageHandler(
                    filters.Regex("^(Enter daily measurements)$"), log_daily_measurements
                ),
            ],
            MEASUREMENTS_REPLY: [
                MessageHandler(
                    filters.TEXT & ~(filters.COMMAND | filters.Regex("^Done$")),
                    received_information,
                )
            ],
            MEDICINE_CHOICE: [
                MessageHandler(
                    filters.Regex(f"^({medicines_str})$"), choose_medicine
                ),
                MessageHandler(filters.Regex("^Done$"), finish_daily_logging)
            ],
            MEDICINE_REPLY: [
                MessageHandler(
                    filters.TEXT & ~(filters.COMMAND | filters.Regex("^Done$")),
                    received_information,
                )
            ],
        },
        fallbacks=[MessageHandler(filters.Regex("^Done$"), done)],
    )

    application.add_handler(conv_handler)

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
