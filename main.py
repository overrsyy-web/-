import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Union
import sqlite3
from contextlib import contextmanager

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes
)
from telegram.constants import ParseMode

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
API_TOKEN = "8199732388:AAGx4q9OJwuoBKNCc8IdqFF0MIaq7syPoME" # Вернул snake_case
ADMIN_IDS = {5354171824}  # Ваш Telegram User ID

# Состояния для ConversationHandler
(
    REGISTER_NAME,
    SYMPTOMS_CHOOSING_CATEGORY,
    SYMPTOMS_DESCRIPTION,
    MEDICINE_NAME,
    DIARY_MOOD,
    DIARY_SYMPTOMS,
    DIARY_NOTES,
    REMINDER_MED_NAME,
    REMINDER_DOSAGE,
    REMINDER_TIME,
    REMINDER_FREQUENCY,
    ADMIN_PANEL_CHOICE,
    ADMIN_USER_ID_INPUT
) = range(13)

class Database:
    def __init__(self, db_path: str = "health_bot.db"):
        self.db_path = db_path
        self.init_db()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            logger.error(f"Database transaction failed: {e}")
            conn.rollback()
            raise e
        finally:
            conn.close()

    def init_db(self):
        """Инициализация таблиц базы данных"""
        with self.get_connection() as conn:
            cursor = conn.cursor()


            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    registered_name TEXT,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_banned INTEGER DEFAULT 0
                )
            ''')


            cursor.execute('''
                CREATE TABLE IF NOT EXISTS diary_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    mood TEXT,
                    symptoms TEXT,
                    notes TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')


            cursor.execute('''
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    med_name TEXT NOT NULL,
                    dosage TEXT,
                    reminder_time TEXT,
                    frequency TEXT,
                    is_enabled INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')



    # Методы для работы с пользователями
    def register_user(self, user_id: int, registered_name: str, username: Optional[str], first_name: Optional[str]): # Вернул snake_case
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, registered_name, is_banned)
                VALUES (?, ?, ?, ?, (SELECT COALESCE(is_banned, 0) FROM users WHERE user_id = ?) )
            ''', (user_id, username, first_name, registered_name, user_id))


    def is_registered(self, user_id: int) -> bool: # Вернул snake_case
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT registered_name FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result is not None

    def get_user_name(self, user_id: int) -> Optional[str]: # Вернул snake_case
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT registered_name FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result['registered_name'] if result else None

    def ban_user(self, user_id: int): # Вернул snake_case
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))

    def unban_user(self, user_id: int): # Вернул snake_case
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))

    def is_banned(self, user_id: int) -> bool: # Вернул snake_case
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return bool(result['is_banned']) if result else False

    # Методы для работы с дневником
    def add_diary_entry(self, user_id: int, mood: str, symptoms: str, notes: str): # Вернул snake_case
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO diary_entries (user_id, mood, symptoms, notes)
                VALUES (?, ?, ?, ?)
            ''', (user_id, mood, symptoms, notes))

    def get_diary_entries(self, user_id: int, limit: int = 5) -> List[Dict]: # Вернул snake_case
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM diary_entries -- Исправлено: добавлено *
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    # Методы для работы с напоминаниями
    def add_reminder(self, user_id: int, med_name: str, dosage: str, # Вернул snake_case
                     reminder_time: str, frequency: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO reminders (user_id, med_name, dosage, reminder_time, frequency)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, med_name, dosage, reminder_time, frequency))

    def get_reminders(self, user_id: int) -> List[Dict]: # Вернул snake_case
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM reminders -- Исправлено: добавлено *
                WHERE user_id = ?
                ORDER BY reminder_time
            ''', (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_all_users(self, limit: int = 10) -> List[Dict]:
        """Возвращает список последних зарегистрированных пользователей."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, username, first_name, registered_name, registered_at, is_banned
                FROM users
                ORDER BY registered_at DESC
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_user_info(self, user_id: int) -> Optional[Dict]:
        """Возвращает полную информацию о конкретном пользователе."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, username, first_name, registered_name, registered_at, is_banned
                FROM users
                WHERE user_id = ?
            ''', (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None



# Инициализация базы данных
db = Database() # Перемещено сюда, чтобы был доступ

# --- Вспомогательные функции для клавиатур ---
def get_main_menu_keyboard(): # Вернул snake_case
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="1️⃣ Выбрать категорию симптомов", callback_data="symptoms_category")], # Вернул snake_case
        [InlineKeyboardButton(text="2️⃣ Найти лекарство/аналоги", callback_data="find_medicine")], # Вернул snake_case
        [InlineKeyboardButton(text="3️⃣ Экстренная помощь", callback_data="emergency_help")], # Вернул snake_case
        [InlineKeyboardButton(text="4️⃣ Дневник самочувствия", callback_data="wellbeing_diary")], # Вернул snake_case
        [InlineKeyboardButton(text="5️⃣ Напоминание о приёме лекарства", callback_data="med_reminder")] # Вернул snake_case
    ])

def get_admin_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="Список пользователей", callback_data="admin_users_list")],
        [InlineKeyboardButton(text="Забанить пользователя", callback_data="admin_ban_user")],
        [InlineKeyboardButton(text="Разбанить пользователя", callback_data="admin_unban_user")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu_return")]
    ])

def get_admin_back_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="⬅️ Назад в админ-меню", callback_data="admin_menu_return")]
    ])

def get_back_to_main_menu_keyboard(): # Вернул snake_case
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu_return")] # Вернул snake_case
    ])

def get_symptoms_categories_keyboard(): # Вернул snake_case
    categories = ["Голова", "Грудь", "Живот", "Конечности", "Общее самочувствие"]
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(
            text=cat,
            callback_data=f"sym_cat_{cat.lower().replace(' ', '_')}" # Вернул sym_cat_
        )])
    buttons.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu_return")]) # Вернул snake_case
    return InlineKeyboardMarkup(buttons)

def get_diary_options_keyboard(): # Вернул snake_case
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="Добавить запись", callback_data="diary_add_entry")], # Вернул snake_case
        [InlineKeyboardButton(text="Просмотреть записи", callback_data="diary_view_entries")], # Вернул snake_case
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu_return")] # Вернул snake_case
    ])

def get_reminder_options_keyboard(): # Вернул snake_case
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="Добавить напоминание", callback_data="reminder_add_new")], # Вернул snake_case
        [InlineKeyboardButton(text="Просмотреть напоминания", callback_data="reminder_view_all")], # Вернул snake_case
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu_return")] # Вернул snake_case
    ])

def get_mood_keyboard():
    moods = ["Отлично ", "Хорошо ", "Нормально ", "Плохо ", "Очень плохо "]
    buttons = []
    for i, mood in enumerate(moods, 1):
        buttons.append(InlineKeyboardButton(text=mood, callback_data=f"mood_{i}")) # Вернул mood_

    return InlineKeyboardMarkup([
        buttons,
        [InlineKeyboardButton(text="Отмена", callback_data="main_menu_return")]
    ])

# --- Проверка доступа (общая для всех обработчиков) ---
async def check_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    user_id = user.id

    if db.is_banned(user_id):
        if update.callback_query:
            await update.callback_query.answer("Вы заблокированы и не можете пользоваться ботом.", show_alert=True)
            await update.callback_query.edit_message_text("Вы заблокированы и не можете пользоваться ботом.")
        else:
            await update.message.reply_text("Вы заблокированы и не можете пользоваться ботом.")
        context.user_data.clear()
        return False

    if not db.is_registered(user_id):
        if update.callback_query:
            await update.callback_query.answer("Вы не зарегистрированы. Используйте /register.", show_alert=True)
            await update.callback_query.edit_message_text(
                "Вы не зарегистрированы. Чтобы пользоваться ботом, начните с команды /register."
            )
        else:
            await update.message.reply_text(
                "Вы не зарегистрированы. Чтобы пользоваться ботом, начните с команды /register."
            )
        context.user_data.clear()
        return False

    return True

# --- Обработчики команд ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    user_id = user.id

    if db.is_banned(user_id):
        await update.message.reply_text("Вы заблокированы и не можете пользоваться ботом.")
        return ConversationHandler.END

    if not db.is_registered(user_id):
        await update.message.reply_text(
            "Привет! Я твой бот.\n"
            "Для регистрации введите команду /register"
        )
    else:
        user_name = db.get_user_name(user_id) # Вернул snake_case
        await update.message.reply_text(
            f"С возвращением, {user_name}!\n"
            "Выберите опцию из меню:",
            reply_markup=get_main_menu_keyboard() # Вернул snake_case
        )

    context.user_data.clear()
    return ConversationHandler.END

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: # Убрал REGISTER_NAME=None
    user = update.effective_user
    user_id = user.id

    if db.is_banned(user_id):
        await update.message.reply_text("Вы заблокированы и не можете пользоваться ботом.")
        return ConversationHandler.END

    if db.is_registered(user_id):
        user_name = db.get_user_name(user_id)
        await update.message.reply_text(f"Вы уже зарегистрированы как {user_name}!")
        return ConversationHandler.END

    await update.message.reply_text("Как тебя зовут?")
    return REGISTER_NAME # Вернул глобальную константу

async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: # Убрал REGISTER_NAME=None
    user = update.effective_user
    user_id = user.id

    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Имя не может быть пустым. Пожалуйста, введите ваше имя.")
        return REGISTER_NAME

    db.register_user(
        user_id=user_id,
        registered_name=name,
        username=user.username,
        first_name=user.first_name
    )

    logger.info(f"User {user_id} registered as {name}")

    await update.message.reply_text(
        f"Спасибо, {name}, вы зарегистрированы!\n"
        "Выберите опцию из меню:",
        reply_markup=get_main_menu_keyboard()
    )

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id

    if not await check_access(update, context):
        return ConversationHandler.END

    await update.message.reply_text(
        "Действие отменено. Выберите опцию:",
        reply_markup=get_main_menu_keyboard()
    )

    context.user_data.clear()
    return ConversationHandler.END

# Админ-команды
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет прав для этой команды.")
        return

    if not context.args:
        await update.message.reply_text("Использование: /ban <user_id>") # Добавил <user_id> для ясности
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Ошибка: user_id должен быть числом.")
        return

    if target_id == user_id:
        await update.message.reply_text("Вы не можете заблокировать самого себя.")
        return

    db.ban_user(target_id)
    logger.info(f"User {target_id} banned by admin {user_id}")
    await update.message.reply_text(f"Пользователь {target_id} заблокирован.")

    try:
        await context.bot.send_message(
            target_id,
            "Вы были заблокированы администратором и не можете пользоваться ботом."
        )
    except Exception as e:
        logger.warning(f"Could not notify banned user {target_id}: {e}")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет прав для этой команды.")
        return

    if not context.args:
        await update.message.reply_text("Использование: /unban <user_id>") # Добавил <user_id> для ясности
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Ошибка: user_id должен быть числом.")
        return

    if db.is_banned(target_id):
        db.unban_user(target_id)
        logger.info(f"User {target_id} unbanned by admin {user_id}")
        await update.message.reply_text(f"Пользователь {target_id} разблокирован.")
        try:
            await context.bot.send_message(
                target_id,
                "Вы были разблокированы и можете снова пользоваться ботом. Используйте /start."
            )
        except Exception as e:
            logger.warning(f"Could not notify unbanned user {target_id}: {e}")
    else:
        await update.message.reply_text("Этот пользователь не заблокирован.")


async def main_menu_return(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return ConversationHandler.END

    context.user_data.clear()

    await query.edit_message_text(
        "Вы вернулись в главное меню. Выберите опцию:",
        reply_markup=get_main_menu_keyboard()
    )
    return ConversationHandler.END

# 1. Категории симптомов
async def symptoms_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int: # Убрал SYMPTOMS_CHOOSING_CATEGORY=None
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return ConversationHandler.END

    await query.edit_message_text(
        "Пожалуйста, выберите категорию симптомов, которая вас беспокоит, "
        "или опишите свои симптомы.",
        reply_markup=get_symptoms_categories_keyboard()
    )
    return SYMPTOMS_CHOOSING_CATEGORY

async def symptoms_category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return ConversationHandler.END

    category = query.data.replace("sym_cat_", "").replace("_", " ").capitalize() # Исправлено sym_cat_
    context.user_data["chosen_category"] = category # Вернул snake_case

    await query.edit_message_text(
        f"Вы выбрали категорию: <b>{category}</b>.\n" # Добавил HTML-теги для жирного шрифта
        "Теперь, пожалуйста, подробно опишите ваши симптомы в текстовом сообщении. "
        "Например: 'У меня болит голова уже 2 дня, пульсирующая боль в висках'.",
        parse_mode=ParseMode.HTML, # Исправлено
        reply_markup=get_back_to_main_menu_keyboard()
    )
    return SYMPTOMS_DESCRIPTION

async def symptoms_description_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id

    if not await check_access(update, context):
        return ConversationHandler.END

    symptoms = update.message.text.strip()
    category = context.user_data.get("chosen_category", "не указана")

    logger.info(f"User {user_id} in category '{category}' described symptoms: {symptoms}")

    await update.message.reply_text(
        f"Спасибо за описание! Ваши симптомы в категории <b>'{category}'</b>: " # Добавил HTML-теги
        f"<i>'{symptoms}'</i> были приняты к рассмотрению.\n\n" # Добавил HTML-теги
        "На данный момент функционал анализа находится в разработке. "
        "Пожалуйста, обратитесь к врачу для точного диагноза.",
        parse_mode=ParseMode.HTML, # Исправлено
        reply_markup=get_main_menu_keyboard()
    )

    context.user_data.clear()
    return ConversationHandler.END

# 2. Поиск лекарств
async def find_medicine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return ConversationHandler.END

    await query.edit_message_text(
        "Вы выбрали 'Найти лекарство/аналоги'.\n"
        "Пожалуйста, введите название лекарства, которое хотите найти:",
        reply_markup=get_back_to_main_menu_keyboard()
    )
    return MEDICINE_NAME

async def medicine_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_access(update, context):
        return ConversationHandler.END

    medicine_name = update.message.text.strip()
    response_text = ""

    # Простая имитация поиска
    if "парацетамол" in medicine_name.lower():
        response_text = (
            f"Найдены данные для <b>{medicine_name.capitalize()}</b>:\n" # Добавил HTML-теги
            "Действующее вещество: Парацетамол\n"
            "Показания: Жаропонижающее, обезболивающее.\n"
            "Аналоги: Панадол, Эффералган, Цефекон Д."
        )
    elif "ибупрофен" in medicine_name.lower():
        response_text = (
            f"Найдены данные для <b>{medicine_name.capitalize()}</b>:\n" # Добавил HTML-теги
            "Действующее вещество: Ибупрофен\n"
            "Показания: Противовоспалительное, обезболивающее, жаропонижающее.\n"
            "Аналоги: Нурофен, Миг, Фаспик."
        )
    else:
        response_text = (
            f"К сожалению, информация по лекарству '<b>{medicine_name}</b>' не найдена в нашей базе.\n" # Добавил HTML-теги
            "Попробуйте другое название или проверьте орфографию."
        )

    await update.message.reply_text(
        response_text,
        parse_mode=ParseMode.HTML, # Исправлено
        reply_markup=get_main_menu_keyboard()
    )

    context.user_data.clear()
    return ConversationHandler.END

# 3. Экстренная помощь
async def emergency_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return

    await query.edit_message_text(
        "Вы выбрали 'Экстренная помощь'.\n\n"
        "🚨 <b>ВНИМАНИЕ! В случае реальной угрозы жизни или здоровья, " # Добавил HTML-теги
        "немедленно обратитесь к врачу или вызовите скорую помощь!</b>\n" # Добавил HTML-теги
        "🚑 <b>Телефоны экстренных служб:</b>\n" # Добавил HTML-теги
        "- Скорая помощь: <b>103</b> (или 112)\n" # Добавил HTML-теги
        "- Пожарная служба: <b>101</b>\n" # Добавил HTML-теги
        "- Полиция: <b>102</b>\n\n" # Добавил HTML-теги
        "ℹ️ Здесь также может быть информация о первой помощи при различных состояниях.",
        parse_mode=ParseMode.HTML, # Исправлено
        reply_markup=get_main_menu_keyboard()
    )

# 4. Дневник самочувствия
async def wellbeing_diary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return ConversationHandler.END

    await query.edit_message_text(
        "Добро пожаловать в Дневник самочувствия! Что бы вы хотели сделать?",
        reply_markup=get_diary_options_keyboard()
    )
    return DIARY_MOOD

async def diary_add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return ConversationHandler.END

    await query.edit_message_text(
        "Как ваше самочувствие сегодня? Выберите настроение:",
        reply_markup=get_mood_keyboard()
    )
    return DIARY_MOOD

async def diary_mood_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return ConversationHandler.END

    mood_index = int(query.data.split('_')[1]) # Исправлено mood_
    moods_map = {1: "Отлично 😊", 2: "Хорошо 🙂", 3: "Нормально 😐", 4: "Плохо 😟", 5: "Очень плохо 😫"}
    selected_mood = moods_map.get(mood_index, "Не указано")

    context.user_data["diary_mood"] = selected_mood

    await query.edit_message_text(
        f"Вы выбрали настроение: <b>{selected_mood}</b>.\n" # Добавил HTML-теги
        "Теперь опишите, какие симптомы вы испытываете (или напишите 'нет', если их нет):",
        parse_mode=ParseMode.HTML, # Исправлено
        reply_markup=get_back_to_main_menu_keyboard()
    )
    return DIARY_SYMPTOMS

async def diary_symptoms_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_access(update, context):
        return ConversationHandler.END

    symptoms = update.message.text.strip()
    context.user_data["diary_symptoms"] = symptoms

    await update.message.reply_text(
        "Есть ли какие-либо дополнительные заметки или комментарии, которые вы хотите добавить? "
        "(Напишите 'нет', если их нет)",
        reply_markup=get_back_to_main_menu_keyboard()
    )
    return DIARY_NOTES

async def diary_notes_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id

    if not await check_access(update, context):
        return ConversationHandler.END

    notes = update.message.text.strip()

    mood = context.user_data.get("diary_mood", "не указано")
    symptoms = context.user_data.get("diary_symptoms", "не указаны")

    db.add_diary_entry(
        user_id=user_id,
        mood=mood,
        symptoms=symptoms,
        notes=notes if notes.lower() != "нет" else ""
    )

    logger.info(f"Added diary entry for user {user_id}")

    await update.message.reply_text(
        "✅ Запись успешно добавлена в ваш дневник самочувствия!\n\n"
        "Что-то еще?",
        reply_markup=get_main_menu_keyboard()
    )

    context.user_data.clear()
    return ConversationHandler.END

async def diary_view_entries(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return ConversationHandler.END

    user_id = update.effective_user.id

    entries = db.get_diary_entries(user_id)

    if not entries:
        await query.edit_message_text(
            "У вас пока нет записей в дневнике самочувствия.",
            reply_markup=get_diary_options_keyboard()
        )
        return DIARY_MOOD

    entries_text = "<b>Ваши записи в дневнике самочувствия:</b>\n\n" # Добавил HTML-теги

    for i, entry in enumerate(entries, 1):
        entries_text += (
            f"<b>Запись #{i} ({entry['timestamp'][:16]}):</b>\n" # Добавил HTML-теги
            f"Настроение: {entry['mood']}\n"
            f"Симптомы: {entry['symptoms'] if entry['symptoms'].lower() != 'нет' else 'нет'}\n"
            f"Заметки: {entry['notes'] if entry['notes'] else 'нет'}\n\n"
        )

    await query.edit_message_text(
        entries_text,
        parse_mode=ParseMode.HTML, # Исправлено
        reply_markup=get_diary_options_keyboard()
    )
    return DIARY_MOOD

# 5. Напоминания о лекарствах
async def med_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return ConversationHandler.END

    await query.edit_message_text(
        "Напоминания о приёме лекарств. Что бы вы хотели сделать?",
        reply_markup=get_reminder_options_keyboard()
    )
    return REMINDER_MED_NAME # Используем REMINDER_MED_NAME как вход в этот Conv.Handler

async def reminder_add_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return ConversationHandler.END

    await query.edit_message_text(
        "Введите название лекарства, для которого нужно установить напоминание:",
        reply_markup=get_back_to_main_menu_keyboard()
    )
    return REMINDER_MED_NAME

async def reminder_med_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_access(update, context):
        return ConversationHandler.END

    med_name = update.message.text.strip()
    context.user_data["reminder_med_name"] = med_name

    await update.message.reply_text(
        f"Отлично, <b>{med_name}</b>.\n" # Добавил HTML-теги
        "Теперь введите дозировку (например, '1 таблетка', '5 мг', '10 мл'):",
        parse_mode=ParseMode.HTML, # Исправлено
        reply_markup=get_back_to_main_menu_keyboard()
    )
    return REMINDER_DOSAGE

async def reminder_dosage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_access(update, context):
        return ConversationHandler.END

    dosage = update.message.text.strip()
    context.user_data["reminder_dosage"] = dosage

    await update.message.reply_text(
        "Введите время приёма в формате ЧЧ:ММ (например, 09:00, 21:30):",
        reply_markup=get_back_to_main_menu_keyboard()
    )
    return REMINDER_TIME

async def reminder_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not await check_access(update, context):
        return ConversationHandler.END

    time_str = update.message.text.strip()

    try:
        datetime.strptime(time_str, "%H:%M")
        context.user_data["reminder_time"] = time_str

        await update.message.reply_text(
            f"Время приёма: <b>{time_str}</b>.\n" # Добавил HTML-теги
            "Как часто напоминать? (Например: 'Ежедневно', 'Каждый день', 'Через день', '1 раз в неделю')",
            parse_mode=ParseMode.HTML, # Исправлено
            reply_markup=get_back_to_main_menu_keyboard()
        )
        return REMINDER_FREQUENCY

    except ValueError:
        await update.message.reply_text(
            "Неверный формат времени. Пожалуйста, введите время в формате ЧЧ:ММ (например, 09:00):",
            reply_markup=get_back_to_main_menu_keyboard()
        )
        return REMINDER_TIME

async def reminder_frequency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id

    if not await check_access(update, context):
        return ConversationHandler.END

    frequency = update.message.text.strip()

    med_name = context.user_data.get("reminder_med_name", "лекарство")
    dosage = context.user_data.get("reminder_dosage", "дозировка")
    time = context.user_data.get("reminder_time", "время")

    db.add_reminder(
        user_id=user_id,
        med_name=med_name,
        dosage=dosage,
        reminder_time=time,
        frequency=frequency
    )

    logger.info(f"Added reminder for user {user_id}")

    await update.message.reply_text(
        f"✅ Напоминание для <b>{med_name}</b> ({dosage}) в <b>{time}</b> " # Добавил HTML-теги
        f"({frequency}) успешно добавлено!",
        parse_mode=ParseMode.HTML, # Исправлено
        reply_markup=get_main_menu_keyboard()
    )

    context.user_data.clear()
    return ConversationHandler.END

async def reminder_view_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return ConversationHandler.END

    user_id = update.effective_user.id

    reminders = db.get_reminders(user_id)

    if not reminders:
        await query.edit_message_text(
            "У вас пока нет установленных напоминаний.",
            reply_markup=get_reminder_options_keyboard()
        )
        return REMINDER_MED_NAME

    reminders_text = "<b>Ваши напоминания о приёме лекарств:</b>\n\n" # Добавил HTML-теги

    for i, reminder in enumerate(reminders, 1):
        status = "✅ Вкл." if reminder['is_enabled'] else "❌ Выкл." # Вернул snake_case в БД
        reminders_text += (
            f"<b>{i}. {reminder['med_name']}</b>\n" # Добавил HTML-теги
            f"   Дозировка: {reminder['dosage']}\n"
            f"   Время: {reminder['reminder_time']}\n"
            f"   Частота: {reminder['frequency']}\n"
            f"   Статус: {status}\n\n"
        )

    reminders_text += "<i>В будущем здесь будет возможность редактировать или удалять напоминания.</i>"

    await query.edit_message_text(
        reminders_text,
        parse_mode=ParseMode.HTML, # Исправлено
        reply_markup=get_reminder_options_keyboard()
    )
    return REMINDER_MED_NAME

# Обработчик неизвестных сообщений
async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    if db.is_banned(user_id):
        await update.message.reply_text("Вы заблокированы и не можете пользоваться ботом.")
        return

    if not db.is_registered(user_id):
        await update.message.reply_text(
            "Вы не зарегистрированы. Пожалуйста, начните с команды /register."
        )
        return

    if update.message.text and update.message.text.startswith('/'):
        await update.message.reply_text(
            "Неизвестная команда. Выберите опцию из меню:",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            "Я вас не понял. Выберите опцию из меню:",
            reply_markup=get_main_menu_keyboard()
        )

async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет прав для доступа к админ-панели.")
        return ConversationHandler.END

    await update.message.reply_text(
        "Добро пожаловать в админ-панель! Выберите действие:",
        reply_markup=get_admin_menu_keyboard()
    )
    return ADMIN_PANEL_CHOICE

async def admin_menu_return(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if update.effective_user.id not in ADMIN_IDS:
        await query.edit_message_text("У вас нет прав.")
        return ConversationHandler.END

    context.user_data.clear() # Очищаем данные админа после использования

    await query.edit_message_text(
        "Вы вернулись в админ-меню. Выберите действие:",
        reply_markup=get_admin_menu_keyboard()
    )
    return ADMIN_PANEL_CHOICE

async def admin_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if update.effective_user.id not in ADMIN_IDS:
        await query.edit_message_text("У вас нет прав.")
        return ConversationHandler.END

    users = db.get_all_users(limit=10)
    if not users:
        text = "Список пользователей пуст."
    else:
        text = "<b>Последние 10 зарегистрированных пользователей:</b>\n\n"
        for u in users:
            banned_status = " (Забанен)" if u['is_banned'] else ""
            text += f"ID: <code>{u['user_id']}</code>\n" \
                    f"Имя: {u['registered_name']} ({u['first_name'] or 'N/A'})\n" \
                    f"@{u['username'] or 'N/A'}\n" \
                    f"Рег: {u['registered_at'][:16]}{banned_status}\n\n"

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_back_keyboard()
    )
    return ADMIN_PANEL_CHOICE # Возвращаемся в состояние админ-панели

async def admin_request_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if update.effective_user.id not in ADMIN_IDS:
        await query.edit_message_text("У вас нет прав.")
        return ConversationHandler.END

    action = query.data.replace("admin_", "") # Например, "user_info", "user_diary"
    context.user_data["admin_action_type"] = action

    await query.edit_message_text(
        f"Пожалуйста, введите User ID для действия '{action.replace('_', ' ')}':",
        reply_markup=get_admin_back_keyboard()
    )
    return ADMIN_USER_ID_INPUT

async def admin_process_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id_str = update.message.text.strip()
    try:
        target_user_id = int(user_id_str)
    except ValueError:
        await update.message.reply_text(
            "Неверный формат User ID. Пожалуйста, введите число.",
            reply_markup=get_admin_back_keyboard()
        )
        return ADMIN_USER_ID_INPUT

    action_type = context.user_data.get("admin_action_type")
    response_text = "Ошибка: неизвестное действие."

    if action_type == "user_info":
        info = db.get_user_info(target_user_id)
        if info:
            banned_status = "Да" if info['is_banned'] else "Нет"
            response_text = (
                f"<b>Информация о пользователе ID: {target_user_id}</b>\n"
                f"Имя: {info['registered_name']} ({info['first_name'] or 'N/A'})\n"
                f"Username: @{info['username'] or 'N/A'}\n"
                f"Зарегистрирован: {info['registered_at'][:16]}\n"
                f"Забанен: {banned_status}"
            )
        else:
            response_text = f"Пользователь с ID {target_user_id} не найден."

    elif action_type == "user_diary":
        entries = db.get_diary_entries(target_user_id, limit=5)
        if entries:
            response_text = f"<b>Последние 5 записей дневника пользователя ID: {target_user_id}</b>\n\n"
            for i, entry in enumerate(entries, 1):
                response_text += (
                    f"<b>Запись #{i} ({entry['timestamp'][:16]}):</b>\n"
                    f"Настроение: {entry['mood']}\n"
                    f"Симптомы: {entry['symptoms'] if entry['symptoms'].lower() != 'нет' else 'нет'}\n"
                    f"Заметки: {entry['notes'] if entry['notes'] else 'нет'}\n\n"
                )
        else:
            response_text = f"У пользователя ID {target_user_id} нет записей в дневнике."

    elif action_type == "user_reminders":
        reminders = db.get_reminders(target_user_id)
        if reminders:
            response_text = f"<b>Напоминания пользователя ID: {target_user_id}</b>\n\n"
            for i, reminder in enumerate(reminders, 1):
                status = "✅ Вкл." if reminder['is_enabled'] else "❌ Выкл."
                response_text += (
                    f"<b>{i}. {reminder['med_name']}</b>\n"
                    f"   Дозировка: {reminder['dosage']}\n"
                    f"   Время: {reminder['reminder_time']}\n"
                    f"   Частота: {reminder['frequency']}\n"
                    f"   Статус: {status}\n\n"
                )
        else:
            response_text = f"У пользователя ID {target_user_id} нет напоминаний."

    elif action_type == "ban_user":
        if target_user_id == update.effective_user.id:
            response_text = "Вы не можете заблокировать самого себя."
        elif db.is_banned(target_user_id):
            response_text = f"Пользователь ID {target_user_id} уже заблокирован."
        else:
            db.ban_user(target_user_id)
            logger.info(f"User {target_user_id} banned by admin {update.effective_user.id}")
            response_text = f"Пользователь ID {target_user_id} заблокирован."
            try:
                await context.bot.send_message(
                    target_user_id,
                    "Вы были заблокированы администратором и не можете пользоваться ботом."
                )
            except Exception as e:
                logger.warning(f"Could not notify banned user {target_user_id}: {e}")

    elif action_type == "unban_user":
        if not db.is_banned(target_user_id):
            response_text = f"Пользователь ID {target_user_id} не заблокирован."
        else:
            db.unban_user(target_user_id)
            logger.info(f"User {target_user_id} unbanned by admin {update.effective_user.id}")
            response_text = f"Пользователь ID {target_user_id} разблокирован."
            try:
                await context.bot.send_message(
                    target_user_id,
                    "Вы были разблокированы и можете снова пользоваться ботом. Используйте /start."
                )
            except Exception as e:
                logger.warning(f"Could not notify unbanned user {target_user_id}: {e}")
    else:
        response_text = f"Неизвестное действие админа: {action_type}"


    await update.message.reply_text(
        response_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_back_keyboard()
    )
    context.user_data.clear() # Очищаем временные данные, чтобы избежать повторного использования
    return ADMIN_PANEL_CHOICE



def main():
    """Запуск бота"""


    application = Application.builder().token(API_TOKEN).build()

    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_PANEL_CHOICE: [
                CallbackQueryHandler(admin_users_list, pattern="^admin_users_list$"),
                CallbackQueryHandler(admin_request_user_id, pattern="^admin_ban_user$"),
                CallbackQueryHandler(admin_request_user_id, pattern="^admin_unban_user$"),
                CallbackQueryHandler(admin_menu_return, pattern="^admin_menu_return$")
            ],
            ADMIN_USER_ID_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_user_id)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(main_menu_return, pattern="^main_menu_return$"),
            CallbackQueryHandler(admin_menu_return, pattern="^admin_menu_return$")
        ],
        allow_reentry=True
    )

    register_conv = ConversationHandler(
        entry_points=[CommandHandler("register", register_start)],
        states={
            REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )


    symptoms_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(symptoms_category, pattern="^symptoms_category$"),
            CallbackQueryHandler(symptoms_category_selected, pattern="^sym_cat_")
        ],
        states={
            SYMPTOMS_CHOOSING_CATEGORY: [
                CallbackQueryHandler(symptoms_category_selected, pattern="^sym_cat_")
            ],
            SYMPTOMS_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, symptoms_description_received)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(main_menu_return, pattern="^main_menu_return$")
        ],
        allow_reentry=True
    )


    medicine_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(find_medicine, pattern="^find_medicine$")],
        states={
            MEDICINE_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, medicine_name_input)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(main_menu_return, pattern="^main_menu_return$")
        ],
        allow_reentry=True
    )


    diary_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(wellbeing_diary, pattern="^wellbeing_diary$"),
            CallbackQueryHandler(diary_add_entry, pattern="^diary_add_entry$"),
            CallbackQueryHandler(diary_view_entries, pattern="^diary_view_entries$")
        ],
        states={
            DIARY_MOOD: [
                CallbackQueryHandler(diary_mood_selected, pattern="^mood_"),
                CallbackQueryHandler(diary_add_entry, pattern="^diary_add_entry$"),
                CallbackQueryHandler(diary_view_entries, pattern="^diary_view_entries$")
            ],
            DIARY_SYMPTOMS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, diary_symptoms_input)
            ],
            DIARY_NOTES: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, diary_notes_input)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(main_menu_return, pattern="^main_menu_return$")
        ],
        allow_reentry=True
    )


    reminder_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(med_reminder, pattern="^med_reminder$"),
            CallbackQueryHandler(reminder_add_new, pattern="^reminder_add_new$"),
            CallbackQueryHandler(reminder_view_all, pattern="^reminder_view_all$")
        ],
        states={
            REMINDER_MED_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_med_name),
                CallbackQueryHandler(reminder_add_new, pattern="^reminder_add_new$"),
                CallbackQueryHandler(reminder_view_all, pattern="^reminder_view_all$")
            ],
            REMINDER_DOSAGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_dosage)
            ],
            REMINDER_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_time)
            ],
            REMINDER_FREQUENCY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_frequency)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(main_menu_return, pattern="^main_menu_return$")
        ],
        allow_reentry=True
    )


    application.add_handler(CommandHandler("start", start))
    application.add_handler(register_conv)

    application.add_handler(symptoms_conv)
    application.add_handler(medicine_conv)
    application.add_handler(diary_conv)
    application.add_handler(reminder_conv)
    application.add_handler(admin_conv)


    application.add_handler(CallbackQueryHandler(emergency_help, pattern="^emergency_help$"))
    application.add_handler(CallbackQueryHandler(main_menu_return, pattern="^main_menu_return$"))


    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_message))


    logger.info("Starting Telegram bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Telegram bot stopped.")

if __name__ == "__main__":
    main()