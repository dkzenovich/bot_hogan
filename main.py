import json
import logging
import os

from flask import Flask, request
from telegram import Update
from telegram.ext import (Application, CallbackContext, CallbackQueryHandler,
                          CommandHandler, PollAnswerHandler)

app = Flask(__name__)

# Telegram bot token
TOKEN = os.getenv('TELEGRAM_TOKEN')

# Webhook URL
WEBHOOK_URL = f'{os.getenv("WEBHOOK_URL")}/{TOKEN}'

# Setting up the logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Только запись в консоль
    ]
)
logger = logging.getLogger(__name__)
logger.info("This log will be written in the console.")

file_mapping = {
    '1': ('bot_Hogan/hpi.json', 'categories_hpi'),
    '2': ('bot_Hogan/hds.json', 'categories_hds'),
    '3': ('bot_Hogan/mvpi.json', 'categories_mvpi'),
}

class UserState:
    def __init__(self):
        self.category_id = None
        self.category_name = None
        self.scales = []
        self.scale_index = 0
        self.question_index = 0

    def load_category(self, category_id):
        self.category_id = category_id
        self.category_name, self.scales = load_scales_and_questions(category_id)
        self.scale_index = 0
        self.question_index = 0

    def get_current_scale(self):
        return self.scales[self.scale_index]

    def get_current_question(self):
        return self.get_current_scale()['questions'][self.question_index]

    def next_question(self):
        self.question_index += 1
        if self.question_index >= len(self.get_current_scale()['questions']):
            self.question_index = 0
            self.scale_index += 1
            if self.scale_index >= len(self.scales):
                return False
        return True

def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton('HPI: Адаптация', callback_data='cat_1')],
        [InlineKeyboardButton('HDS: Эмоциональный', callback_data='cat_2')],
        [InlineKeyboardButton('MVPI: Признание', callback_data='cat_3')],
    ]
    return InlineKeyboardMarkup(keyboard)

def start_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton('Узнать больше', callback_data='learn_more')],
        [InlineKeyboardButton('Начать тест', callback_data='start_test')],
    ]
    return InlineKeyboardMarkup(keyboard)

def back_to_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton('Вернуться в меню', callback_data='back_to_menu')],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    context.user_data['state'] = UserState()
    await update.message.reply_text(
        f'Привет, {user.full_name}! Добро пожаловать в наш тест. Что вы хотите сделать?',
        reply_markup=start_menu_keyboard(),
    )

async def button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    callback_data = query.data.split('_')
    action = callback_data[0]
    category_id = callback_data[1] if len(callback_data) > 1 else None

    if action == 'cat' and category_id in file_mapping:
        state: UserState = context.user_data['state']
        state.load_category(category_id)
        logger.info(f'Starting questions for category {state.category_name}')
        await send_question(update, context, state.get_current_question())
    elif action == 'learn':
        await learn_more(update, context)
    elif action == 'start':
        await start_test(update, context)
    elif action == 'back':
        await start(update, context)

async def send_question(update, context, question):
    chat_id = update.effective_chat.id
    question_text = question['text']
    options = [option['text'] for option in question['options']]
    logger.info(f'Question: {question_text}, Options: {options}')

    message = await context.bot.send_poll(
        chat_id,
        question_text,
        options,
        is_anonymous=False,
        allows_multiple_answers=False
    )

    payload = {
        message.poll.id: {
            "questions": options,
            "message_id": message.message_id,
            "chat_id": chat_id,
            "state": context.user_data['state']
        }
    }
    context.bot_data.update(payload)

async def receive_poll_answer(update: Update, context: CallbackContext) -> None:
    answer = update.poll_answer
    poll_id = answer.poll_id
    selected_option = answer.option_ids[0]
    payload = context.bot_data[poll_id]
    state = payload["state"]

    current_question = state.get_current_question()
    selected_option_text = current_question['options'][selected_option]['text']

    logger.info(f'Received option: {selected_option_text} for question index: {state.question_index}')
    record_answer(state.category_name, state.get_current_scale()['title'], current_question, selected_option_text)
    logger.debug('Answer recorded successfully')

    if state.next_question():
        next_question = state.get_current_question()
        await send_question_by_id(payload["chat_id"], context, next_question)
    else:
        await context.bot.send_message(
            chat_id=payload["chat_id"],
            text='Вы завершили этот раздел!',
            reply_markup=main_menu_keyboard(),
        )

async def send_question_by_id(chat_id, context, question):
    question_text = question['text']
    options = [option['text'] for option in question['options']]
    logger.info(f'Next Question: {question_text}, Options: {options}')

    message = await context.bot.send_poll(
        chat_id,
        question_text,
        options,
        is_anonymous=False,
        allows_multiple_answers=False
    )

    payload = {
        message.poll.id: {
            "questions": options,
            "message_id": message.message_id,
            "chat_id": chat_id,
            "state": context.user_data['state']
        }
    }
    context.bot_data.update(payload)

def record_answer(category_name, scale_title, question, selected_option_text):
    logger.info(f'Recorded: {scale_title} - {question["text"]} - {selected_option_text}')

def load_scales_and_questions(category_id):
    filename, category_key = file_mapping[category_id]
    with open(filename, encoding='utf-8') as file:
        data = json.load(file)
    category_data = data[category_key]
    category_name = category_key
    scales = category_data
    logger.debug(f'Loaded scales and questions for category {category_id}: {scales}')
    return category_name, scales

async def error_handler(update: Update, context: CallbackContext) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Произошла ошибка. Попробуйте еще раз позже.",
        )
    except Exception as e:
        logger.error(f"Failed to send error message: {e}")

async def learn_more(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.edit_message_text(
        text='Этот тест предназначен для оценки ваших личностных качеств. Ответьте на вопросы, чтобы узнать больше о себе.',
        reply_markup=back_to_menu_keyboard(),
    )

async def start_test(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.edit_message_text(
        text='Выберите категорию для начала теста:',
        reply_markup=main_menu_keyboard(),
    )

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(), application.bot)
    application.update_queue.put(update)
    return 'ok'

@app.route('/')
def index():
    return 'Hello, this is the bot webhook!'

def main() -> None:
    global application
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(PollAnswerHandler(receive_poll_answer))
    application.add_error_handler(error_handler)

    application.bot.set_webhook(url=WEBHOOK_URL)

if __name__ == '__main__':
    main()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8443)))
