import json
import logging
import os

import nest_asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (Application, CallbackContext, CallbackQueryHandler,
                          CommandHandler, PollAnswerHandler)

# Необходим для работы asyncio в Jupyter или в других средах, где уже запущен цикл событий
nest_asyncio.apply()

# Получаем текущую рабочую директорию и создаем путь для файла лога
log_directory = os.getcwd()
log_path = os.path.join(log_directory, "app.log")

# Настройка логгера для записи в файл и вывода на экран
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_path, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)
logger.info("This log will be written in the current directory.")

# Токен для подключения к боту Telegram
TOKEN = '6004824929:AAH_CKkh20J9VLc-O9koE2Af7fHVZzmQ1DU'

# Сопоставление категорий с файлами JSON и ключами категорий
file_mapping = {
    '1': ('bot_Hogan/hpi.json', 'categories_hpi'),
    '2': ('bot_Hogan/hds.json', 'categories_hds'),
    '3': ('bot_Hogan/mvpi.json', 'categories_mvpi'),
}

class UserState:
    """
    Класс для хранения состояния пользователя, включая текущую категорию, шкалу и индекс вопроса.
    """
    def __init__(self):
        self.category_id = None
        self.category_name = None
        self.scales = []
        self.scale_index = 0
        self.question_index = 0

    def load_category(self, category_id):
        """
        Загружает категорию по идентификатору и инициализирует шкалы и вопросы.
        """
        self.category_id = category_id
        self.category_name, self.scales = load_scales_and_questions(category_id)
        self.scale_index = 0
        self.question_index = 0

    def get_current_scale(self):
        """
        Возвращает текущую шкалу.
        """
        return self.scales[self.scale_index]

    def get_current_question(self):
        """
        Возвращает текущий вопрос.
        """
        return self.get_current_scale()['questions'][self.question_index]

    def next_question(self):
        """
        Переходит к следующему вопросу, если все вопросы текущей шкалы пройдены, переходит к следующей шкале.
        """
        self.question_index += 1
        if self.question_index >= len(self.get_current_scale()['questions']):
            self.question_index = 0
            self.scale_index += 1
            if self.scale_index >= len(self.scales):
                return False
        return True

def main_menu_keyboard():
    """
    Создает клавиатуру главного меню с кнопками для выбора категорий.
    """
    keyboard = [
        [InlineKeyboardButton('HPI: Адаптация', callback_data='cat_1')],
        [InlineKeyboardButton('HDS: Эмоциональный', callback_data='cat_2')],
        [InlineKeyboardButton('MVPI: Признание', callback_data='cat_3')],
    ]
    return InlineKeyboardMarkup(keyboard)

def start_menu_keyboard():
    """
    Создает клавиатуру стартового меню с кнопками "Узнать больше" и "Начать тест".
    """
    keyboard = [
        [InlineKeyboardButton('Узнать больше', callback_data='learn_more')],
        [InlineKeyboardButton('Начать тест', callback_data='start_test')],
    ]
    return InlineKeyboardMarkup(keyboard)

def back_to_menu_keyboard():
    """
    Создает клавиатуру для возврата в главное меню.
    """
    keyboard = [
        [InlineKeyboardButton('Вернуться в меню', callback_data='back_to_menu')],
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: CallbackContext) -> None:
    """
    Обработчик команды /start, инициализирует состояние пользователя и отображает стартовое меню.
    """
    user = update.effective_user
    context.user_data['state'] = UserState()
    await update.message.reply_text(
        f'Привет, {user.full_name}! Добро пожаловать в наш тест. Что вы хотите сделать?',
        reply_markup=start_menu_keyboard(),
    )

async def button(update: Update, context: CallbackContext) -> None:
    """
    Обработчик выбора категории, загружает соответствующие вопросы и отправляет первый вопрос.
    """
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
    """
    Отправляет текущий вопрос пользователю в виде опроса.
    """
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

    # Сохраняем id опроса, чтобы потом обработать ответ
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
    """
    Обрабатывает ответ пользователя на опрос.
    """
    answer = update.poll_answer
    poll_id = answer.poll_id
    selected_option = answer.option_ids[0]  # Вариант ответа пользователя
    payload = context.bot_data[poll_id]
    state = payload["state"]

    current_question = state.get_current_question()
    selected_option_text = current_question['options'][selected_option]['text']

    logger.info(f'Received option: {selected_option_text} for question index: {state.question_index}')
    record_answer(state.category_name, state.get_current_scale()['title'], current_question, selected_option_text)
    logger.debug('Answer recorded successfully')

    if state.next_question():
        # Получение следующего вопроса и отправка его пользователю
        next_question = state.get_current_question()
        await send_question_by_id(payload["chat_id"], context, next_question)
    else:
        await context.bot.send_message(
            chat_id=payload["chat_id"],
            text='Вы завершили этот раздел!',
            reply_markup=main_menu_keyboard(),
        )

async def send_question_by_id(chat_id, context, question):
    """
    Отправляет текущий вопрос пользователю в виде опроса.
    """
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

    # Сохраняем id опроса, чтобы потом обработать ответ
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
    """
    Записывает ответ пользователя в файл.
    """
    filename = f'category_{category_name}_answers.txt'
    logger.info(f'Recording answer to {filename}')
    try:
        with open(filename, 'a', encoding='utf-8') as file:
            file.write(f"{scale_title} - {question['text']} - {selected_option_text}\n")
            logger.info(f"Recorded: {scale_title} - {question['text']} - {selected_option_text}")
    except Exception as e:
        logger.error(f"Error writing to file {filename}: {e}")

def load_scales_and_questions(category_id):
    """
    Загружает шкалы и вопросы из файла JSON для указанной категории.
    """
    filename, category_key = file_mapping[category_id]
    with open(filename, encoding='utf-8') as file:
        data = json.load(file)
    category_data = data[category_key]
    category_name = category_key
    scales = category_data
    logger.debug(f'Loaded scales and questions for category {category_id}: {scales}')
    return category_name, scales

async def error_handler(update: Update, context: CallbackContext) -> None:
    """
    Логирует и обрабатывает ошибки.
    """
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Произошла ошибка. Попробуйте еще раз позже.",
        )
    except Exception as e:
        logger.error(f"Failed to send error message: {e}")

async def learn_more(update: Update, context: CallbackContext) -> None:
    """
    Отправляет информацию о тесте и кнопку для возврата в главное меню.
    """
    query = update.callback_query
    await query.edit_message_text(
        text='Этот тест предназначен для оценки ваших личностных качеств. Ответьте на вопросы, чтобы узнать больше о себе.',
        reply_markup=back_to_menu_keyboard(),
    )

async def start_test(update: Update, context: CallbackContext) -> None:
    """
    Отправляет пользователю меню выбора категории для начала теста.
    """
    query = update.callback_query
    await query.edit_message_text(
        text='Выберите категорию для начала теста:',
        reply_markup=main_menu_keyboard(),
    )

def main() -> None:
    """
    Основная функция запуска бота, добавляет обработчики команд и запускает цикл обработки событий.
    """
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(PollAnswerHandler(receive_poll_answer))
    application.add_error_handler(error_handler)
    application.run_polling()

if __name__ == '__main__':
    main()
