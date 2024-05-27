import json
import logging
import os

import nest_asyncio
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (Application, CallbackContext, CallbackQueryHandler,
                          CommandHandler)

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

def escape_markdown_v2(text):
    """
    Экранирует специальные символы для MarkdownV2.
    """
    escape_chars = r'\_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

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
    category_id = query.data.split('_')[1]
    state: UserState = context.user_data['state']
    state.load_category(category_id)
    logger.info(f'Starting questions for category {state.category_name}')
    await send_question(update, context, state.get_current_question())

async def send_question(update, context, question):
    """
    Отправляет текущий вопрос пользователю.
    """
    query = update.callback_query
    new_text = question['text']
    options = question['options']
    logger.info(f'Question: {new_text}, Options: {options}')

    new_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton(option['text'], callback_data=f"ans_{option['id']}")] for option in options]
    )

    try:
        await query.edit_message_text(text=new_text, reply_markup=new_markup)
        logger.info(f'Sent question: {new_text}')
    except BadRequest as e:
        logger.error(f'Failed to edit message text due to BadRequest: {e}')

async def handle_callback(update: Update, context: CallbackContext) -> None:
    """
    Обработчик всех колбэков, разделяет обработку по типу колбэка (категория или ответ).
    """
    query = update.callback_query
    await query.answer()
    callback_data = query.data

    if callback_data.startswith('cat_'):
        logger.info(f'Handling button callback for category: {callback_data}')
        await button(update, context)
    elif callback_data == 'learn_more':
        logger.info('Handling learn more callback')
        await learn_more(update, context)
    elif callback_data == 'start_test':
        logger.info('Handling start test callback')
        await start_test(update, context)
    elif callback_data == 'back_to_menu':
        logger.info('Handling back to menu callback')
        # Используем query.message вместо update.message
        user = query.message.chat  # Получаем пользователя из сообщения
        await query.message.reply_text(
            f'Привет, {user.full_name}! Добро пожаловать в наш тест. Что вы хотите сделать?',
            reply_markup=start_menu_keyboard(),
        )
    elif callback_data.startswith('ans_'):
        logger.info(f'Handling response callback with data: {callback_data}')
        await handle_response(update, context)
    else:
        logger.error(f'Unexpected callback data: {callback_data}')


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

async def handle_response(update: Update, context: CallbackContext) -> None:
    """
    Обрабатывает ответ пользователя на вопрос, записывает ответ и отправляет следующий вопрос.
    """
    query = update.callback_query
    await query.answer()
    state: UserState = context.user_data['state']
    selected_option = query.data.split('_')[1]

    current_question = state.get_current_question()
    options = current_question['options']
    logger.info(f'Options for current question: {options}')

    selected_option = str(selected_option)
    try:
        selected_option_text = next(option['text'] for option in options if str(option['id']) == selected_option)
    except StopIteration:
        logger.error(f'Option id {selected_option} not found for question {current_question["text"]}')
        await query.message.reply_text('An error occurred while processing your response. Please try again.')
        return

    logger.info(f'Received option: {selected_option_text} for question index: {state.question_index}')
    record_answer(state.category_name, state.get_current_scale()['title'], current_question, selected_option_text)
    logger.debug('Answer recorded successfully')

    if state.next_question():
        await send_question(update, context, state.get_current_question())
    else:
        await query.edit_message_text(text='You have completed this category!')
        await query.message.reply_text(
            'Choose another category or type /start to restart.',
            reply_markup=main_menu_keyboard(),
        )

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

def main() -> None:
    """
    Основная функция запуска бота, добавляет обработчики команд и запускает цикл обработки событий.
    """
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_error_handler(error_handler)
    application.run_polling()

if __name__ == '__main__':
    main()
