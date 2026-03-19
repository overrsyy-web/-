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
API_TOKEN = ""
ADMIN_IDS = {}  # Ваш Telegram User ID

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
    def __init__(self, db_path: str = ".db"):
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
    def register_user(self, user_id: int, registered_name: str, username: Optional[str], first_name: Optional[str]):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, registered_name, is_banned)
                VALUES (?, ?, ?, ?, (SELECT COALESCE(is_banned, 0) FROM users WHERE user_id = ?) )
            ''', (user_id, username, first_name, registered_name, user_id))

    def is_registered(self, user_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT registered_name FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result is not None

    def get_user_name(self, user_id: int) -> Optional[str]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT registered_name FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result['registered_name'] if result else None

    def ban_user(self, user_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET is_banned = 1 WHERE user_id = ?', (user_id,))

    def unban_user(self, user_id: int):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET is_banned = 0 WHERE user_id = ?', (user_id,))

    def is_banned(self, user_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return bool(result['is_banned']) if result else False

    # Методы для работы с дневником
    def add_diary_entry(self, user_id: int, mood: str, symptoms: str, notes: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO diary_entries (user_id, mood, symptoms, notes)
                VALUES (?, ?, ?, ?)
            ''', (user_id, mood, symptoms, notes))

    def get_diary_entries(self, user_id: int, limit: int = 5) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM diary_entries
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (user_id, limit))
            return [dict(row) for row in cursor.fetchall()]

    # Методы для работы с напоминаниями
    def add_reminder(self, user_id: int, med_name: str, dosage: str,
                     reminder_time: str, frequency: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO reminders (user_id, med_name, dosage, reminder_time, frequency)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, med_name, dosage, reminder_time, frequency))

    def get_reminders(self, user_id: int) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM reminders
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
db = Database()

# --- Вспомогательные функции для клавиатур ---
def get_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="1️⃣ Выбрать категорию симптомов", callback_data="symptoms_category")],
        [InlineKeyboardButton(text="2️⃣ Найти лекарство/аналоги", callback_data="find_medicine")],
        [InlineKeyboardButton(text="3️⃣ Экстренная помощь", callback_data="emergency_help")],
        [InlineKeyboardButton(text="4️⃣ Дневник самочувствия", callback_data="wellbeing_diary")],
        [InlineKeyboardButton(text="5️⃣ Напоминание о приёме лекарства", callback_data="med_reminder")]
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

def get_back_to_main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu_return")]
    ])

def get_symptoms_categories_keyboard():
    categories = ["Голова", "Грудь", "Живот", "Конечности", "Общее самочувствие"]
    buttons = []
    for cat in categories:
        buttons.append([InlineKeyboardButton(
            text=cat,
            callback_data=f"sym_cat_{cat.lower().replace(' ', '_')}"
        )])
    buttons.append([InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu_return")])
    return InlineKeyboardMarkup(buttons)

def get_diary_options_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="Добавить запись", callback_data="diary_add_entry")],
        [InlineKeyboardButton(text="Просмотреть записи", callback_data="diary_view_entries")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu_return")]
    ])

def get_reminder_options_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(text="Добавить напоминание", callback_data="reminder_add_new")],
        [InlineKeyboardButton(text="Просмотреть напоминания", callback_data="reminder_view_all")],
        [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="main_menu_return")]
    ])

def get_mood_keyboard():
    moods = ["Отлично 😊", "Хорошо 🙂", "Нормально 😐", "Плохо 😟", "Очень плохо 😫"]
    buttons = []
    for i, mood in enumerate(moods, 1):
        buttons.append(InlineKeyboardButton(text=mood, callback_data=f"mood_{i}"))

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
        context.user_data.clear() # Clear any potential conversation state
        return ConversationHandler.END

    if not db.is_registered(user_id):
        await update.message.reply_text(
            "Привет! Я твой бот.\n"
            "Для регистрации введите команду /register"
        )
    else:
        user_name = db.get_user_name(user_id)
        await update.message.reply_text(
            f"С возвращением, {user_name}!\n"
            "Выберите опцию из меню:",
            reply_markup=get_main_menu_keyboard()
        )

    context.user_data.clear()
    return ConversationHandler.END

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    user_id = user.id

    if db.is_banned(user_id):
        await update.message.reply_text("Вы заблокированы и не можете пользоваться ботом.")
        context.user_data.clear()
        return ConversationHandler.END

    if db.is_registered(user_id):
        user_name = db.get_user_name(user_id)
        await update.message.reply_text(f"Вы уже зарегистрированы как {user_name}!")
        context.user_data.clear()
        return ConversationHandler.END

    await update.message.reply_text("Как тебя зовут?")
    return REGISTER_NAME

async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    user_id = user.id

    # Проверка доступа здесь не нужна, т.к. это регистрация.
    # Но если пользователь в процессе регистрации пытается что-то другое
    # то ConversationHandler отловит и завершит/вернет в fallback.
    # Если же он уже забанен и сюда попал - это странно, но тогда is_banned вернет True.

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

    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id

    # check_access здесь может быть лишним, так как cancel - это команда, которая
    # должна работать даже если пользователь не зарегистрирован или забанен,
    # чтобы завершить любой диалог.
    # Если пользователь забанен, то check_access уже отправит ему сообщение о бане.
    # Если не зарегистрирован, то отправит сообщение о регистрации.
    # В обоих случаях вернет ConversationHandler.END.
    # Если access True, то он просто отменит и вернет в главное меню.
    if not await check_access(update, context):
        return ConversationHandler.END # check_access will handle the message

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
        await update.message.reply_text("Использование: /ban <user_id>")
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
        await update.message.reply_text("Использование: /unban <user_id>")
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
    if query:
        await query.answer()

    if not await check_access(update, context):
        return ConversationHandler.END

    context.user_data.clear()

    if query:
        await query.edit_message_text(
            "Вы вернулись в главное меню. Выберите опцию:",
            reply_markup=get_main_menu_keyboard()
        )
    else: # Fallback from a message handler
        await update.message.reply_text(
            "Вы вернулись в главное меню. Выберите опцию:",
            reply_markup=get_main_menu_keyboard()
        )
    return ConversationHandler.END


# 1. Категории симптомов
async def symptoms_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

    category = query.data.replace("sym_cat_", "").replace("_", " ").capitalize()
    context.user_data["chosen_category"] = category

    await query.edit_message_text(
        f"Вы выбрали категорию: <b>{category}</b>.\n"
        "Теперь, пожалуйста, подробно опишите ваши симптомы в текстовом сообщении. "
        "Например: 'У меня болит голова уже 2 дня, пульсирующая боль в висках'.",
        parse_mode=ParseMode.HTML,
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
        f"✅ Ваши симптомы в категории <b>'{category}'</b> сохранены: "
        f"<i>'{symptoms}'</i>\n\n"
        "Эта информация будет полезна для отслеживания вашего состояния в дневнике самочувствия.",
        parse_mode=ParseMode.HTML,
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

    # Реальная база лекарств (упрощенная версия)
    medicine_database = {
        "парацетамол": {
            "name": "Парацетамол",
            "substance": "Парацетамол",
            "indications": "Жаропонижающее, обезболивающее",
            "analogs": ["Панадол", "Эффералган", "Цефекон Д"]
        },
        "ибупрофен": {
            "name": "Ибупрофен",
            "substance": "Ибупрофен",
            "indications": "Противовоспалительное, обезболивающее, жаропонижающее",
            "analogs": ["Нурофен", "Миг", "Фаспик"]
        },
        "аспирин": {
            "name": "Аспирин",
            "substance": "Ацетилсалициловая кислота",
            "indications": "Жаропонижающее, противовоспалительное, антиагрегантное",
            "analogs": ["Аспирин-Кардио", "Тромбо АСС"]
        },
        "амоксициллин": {
            "name": "Амоксициллин",
            "substance": "Амоксициллин",
            "indications": "Антибиотик широкого спектра действия",
            "analogs": ["Флемоксин Солютаб", "Амосин"]
        }
    }

    medicine_lower = medicine_name.lower()
    found = False
    response_text = ""

    # Поиск в базе
    for key, medicine_info in medicine_database.items():
        if key in medicine_lower or medicine_lower in key:
            found = True
            analogs_text = ", ".join(medicine_info["analogs"])
            response_text = (
                f"✅ <b>Найдено лекарство:</b> {medicine_info['name']}\n\n"
                f"<b>Действующее вещество:</b> {medicine_info['substance']}\n"
                f"<b>Показания:</b> {medicine_info['indications']}\n"
                f"<b>Аналоги:</b> {analogs_text}\n\n"
                f"<i>Важно: Перед применением проконсультируйтесь с врачом!</i>"
            )
            break

    if not found:
        response_text = (
            f"❌ Лекарство '<b>{medicine_name}</b>' не найдено в базе.\n\n"
            "Попробуйте:\n"
            "1. Проверить орфографию\n"
            "2. Использовать международное непатентованное название (МНН)\n"
            "3. Обратиться к фармацевту"
        )

    await update.message.reply_text(
        response_text,
        parse_mode=ParseMode.HTML,
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

    emergency_info = """
   🚨 <b>ЭКСТРЕННАЯ ПОМОЩЬ</b> 🚨

   <b>ВНИМАНИЕ!</b> В случае реальной угрозы жизни или здоровья немедленно обратитесь к врачу или вызовите скорую помощь!

   <b>📞 Телефоны экстренных служб:</b>
   • Скорая помощь: <b>103</b> (или 112)
   • Пожарная служба: <b>101</b>
   • Полиция: <b>102</b>
   • Газовая служба: <b>104</b>

   <b>🆘 Первая помощь при распространенных состояниях:</b>

   <b>1. Остановка сердца (реанимация):</b>
   • Проверьте сознание и дыхание
   • Вызовите скорую (103)
   • Начните непрямой массаж сердца (100-120 нажатий в минуту)
   • При наличии навыков - искусственное дыхание

   <b>2. Кровотечение:</b>
   • Прижмите рану чистой тканью
   • Поднимите поврежденную конечность выше сердца
   • При артериальном кровотечении (алая кровь фонтаном) - наложите жгут

   <b>3. Ожоги:</b>
   • Охладите место ожога проточной водой 15-20 минут
   • Накройте чистой тканью
   • Не вскрывайте пузыри

   <b>4. Отравление:</b>
   • Вызовите скорую
   • Сохраните упаковку от вещества
   • Не вызывайте рвоту при отравлении кислотами/щелочами

   <b>5. Инсульт (тест УДАР):</b>
   • У - улыбка (кривая)
   • Д - движение (поднять обе руки)
   • А - артикуляция (невнятная речь)
   • Р - решение (вызвать скорую)

   <i>Эта информация носит ознакомительный характер. Для получения квалифицированной медицинской помощи обратитесь к специалисту.</i>
   """

    await query.edit_message_text(
        emergency_info,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_menu_keyboard()
    )

# 4. Дневник самочувствия
async def wellbeing_diary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return ConversationHandler.END

    await query.edit_message_text(
        "📓 <b>Дневник самочувствия</b>\n\n"
        "Здесь вы можете отслеживать свое состояние, симптомы и настроение.",
        parse_mode=ParseMode.HTML,
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

    mood_index = int(query.data.split('_')[1])
    # Moods are already defined with emojis in get_mood_keyboard, use those
    moods_map = {
        1: "Отлично 😊",
        2: "Хорошо 🙂",
        3: "Нормально 😐",
        4: "Плохо 😟",
        5: "Очень плохо 😫"
    }
    selected_mood = moods_map.get(mood_index, "Не указано")

    context.user_data["diary_mood"] = selected_mood

    await query.edit_message_text(
        f"Вы выбрали настроение: <b>{selected_mood}</b>.\n"
        "Теперь опишите, какие симптомы вы испытываете (или напишите 'нет', если их нет):",
        parse_mode=ParseMode.HTML,
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
        parse_mode=ParseMode.HTML, # Added parse mode for consistency
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
            "📭 У вас пока нет записей в дневнике самочувствия.",
            reply_markup=get_diary_options_keyboard(),
            parse_mode=ParseMode.HTML # Added parse mode
        )
        return DIARY_MOOD # Stay in diary options

    entries_text = "<b>📓 Ваши записи в дневнике самочувствия:</b>\n\n"

    for i, entry in enumerate(entries, 1):
        timestamp = entry['timestamp'][:16] if 'timestamp' in entry else "дата неизвестна"
        mood = entry.get('mood', 'не указано')
        symptoms = entry.get('symptoms', 'не указаны')
        notes = entry.get('notes', 'нет')

        entries_text += (
            f"<b>Запись #{i} ({timestamp}):</b>\n"
            f"• Настроение: {mood}\n"
            f"• Симптомы: {symptoms if symptoms.lower() != 'нет' else 'нет'}\n"
            f"• Заметки: {notes if notes else 'нет'}\n\n"
        )

    await query.edit_message_text(
        entries_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_diary_options_keyboard()
    )
    return DIARY_MOOD # Stay in diary options

# 5. Напоминания о лекарствах
async def med_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return ConversationHandler.END

    await query.edit_message_text(
        "⏰ <b>Напоминания о приёме лекарств</b>\n\n"
        "Установите напоминания, чтобы не пропускать прием лекарств.",
        parse_mode=ParseMode.HTML,
        reply_markup=get_reminder_options_keyboard()
    )
    return REMINDER_MED_NAME


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
        f"Отлично, <b>{med_name}</b>.\n"
        "Теперь введите дозировку (например, '1 таблетка', '5 мг', '10 мл'):",
        parse_mode=ParseMode.HTML,
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
            f"Время приёма: <b>{time_str}</b>.\n"
            "Как часто напоминать? (Например: 'Ежедневно', 'Каждый день', 'Через день', '1 раз в неделю')",
            parse_mode=ParseMode.HTML,
            reply_markup=get_back_to_main_menu_keyboard()
        )
        return REMINDER_FREQUENCY

    except ValueError:
        await update.message.reply_text(
            "Неверный формат времени. Пожалуйста, введите время в формате ЧЧ:ММ (например, 09:00):",
            reply_markup=get_back_to_main_menu_keyboard()
        )
        return REMINDER_TIME

# FIX: Unindent these two functions from reminder_time
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
        f"✅ Напоминание для <b>{med_name}</b> ({dosage}) в <b>{time}</b> "
        f"({frequency}) успешно добавлено!",
        parse_mode=ParseMode.HTML,
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
            "⏰ У вас пока нет установленных напоминаний.",
            reply_markup=get_reminder_options_keyboard(),
            parse_mode=ParseMode.HTML # Added parse mode
        )
        return REMINDER_MED_NAME # Stay in reminder options menu

    reminders_text = "<b>⏰ Ваши напоминания о приёме лекарств:</b>\n\n"

    for i, reminder in enumerate(reminders, 1):
        status = "✅ Вкл." if reminder['is_enabled'] else "❌ Выкл."
        reminders_text += (
            f"<b>{i}. {reminder['med_name']}</b>\n"
            f"   Дозировка: {reminder['dosage']}\n"
            f"   Время: {reminder['reminder_time']}\n"
            f"   Частота: {reminder['frequency']}\n"
            f"   Статус: {status}\n\n"
        )

    reminders_text += "<i>В будущем здесь будет возможность редактировать или удалять напоминания.</i>"

    await query.edit_message_text(
        reminders_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_reminder_options_keyboard()
    )
    return REMINDER_MED_NAME # Stay in reminder options menu

# Обработчик неизвестных сообщений
async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id

    # Using check_access here to cover banned/unregistered users.
    # It will send the appropriate message and return False if access is denied.
    if not await check_access(update, context):
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
        context.user_data.clear()
        return ConversationHandler.END

    await update.message.reply_text(
        "👨‍💼 <b>Добро пожаловать в админ-панель!</b>\n\n"
        "Выберите действие:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_menu_keyboard()
    )
    return ADMIN_PANEL_CHOICE

async def admin_menu_return(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if update.effective_user.id not in ADMIN_IDS:
        await query.edit_message_text("У вас нет прав.")
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data.clear()

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
        context.user_data.clear()
        return ConversationHandler.END

    users = db.get_all_users(limit=10)
    if not users:
        text = "📭 Список пользователей пуст."
    else:
        text = "<b>👥 Последние 10 зарегистрированных пользователей:</b>\n\n"
        for u in users:
            banned_status = " 🔴 (Забанен)" if u['is_banned'] else " 🟢 (Активен)"
            text += f"<b>ID:</b> <code>{u['user_id']}</code>\n" \
                    f"<b>Имя:</b> {u['registered_name']} ({u['first_name'] or 'N/A'})\n" \
                    f"<b>Username:</b> @{u['username'] or 'N/A'}\n" \
                    f"<b>Регистрация:</b> {u['registered_at'][:16]}{banned_status}\n\n"

    await query.edit_message_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_back_keyboard()
    )
    return ADMIN_PANEL_CHOICE

async def admin_request_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if update.effective_user.id not in ADMIN_IDS:
        await query.edit_message_text("У вас нет прав.")
        context.user_data.clear()
        return ConversationHandler.END

    action = query.data.replace("admin_", "")
    context.user_data["admin_action_type"] = action

    action_names = {
        "ban_user": "заблокировать пользователя",
        "unban_user": "разблокировать пользователя"
    }

    action_name = action_names.get(action, action.replace('_', ' '))

    await query.edit_message_text(
        f"Пожалуйста, введите User ID для действия '{action_name}':",
        reply_markup=get_admin_back_keyboard()
    )
    return ADMIN_USER_ID_INPUT

async def admin_process_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id_str = update.message.text.strip()
    try:
        target_user_id = int(user_id_str)
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат User ID. Пожалуйста, введите число.",
            reply_markup=get_admin_back_keyboard()
        )
        return ADMIN_USER_ID_INPUT

    action_type = context.user_data.get("admin_action_type")
    response_text = "❌ Ошибка: неизвестное действие."

    if action_type == "ban_user":
        if target_user_id == update.effective_user.id:
            response_text = "❌ Вы не можете заблокировать самого себя."
        elif db.is_banned(target_user_id):
            response_text = f"⚠️ Пользователь ID <code>{target_user_id}</code> уже заблокирован."
        else:
            db.ban_user(target_user_id)
            logger.info(f"User {target_user_id} banned by admin {update.effective_user.id}")
            response_text = f"✅ Пользователь ID <code>{target_user_id}</code> заблокирован."
            try:
                await context.bot.send_message(
                    target_user_id,
                    "🚫 Вы были заблокированы администратором и не можете пользоваться ботом."
                )
            except Exception as e:
                logger.warning(f"Could not notify banned user {target_user_id}: {e}")

    elif action_type == "unban_user":
        if not db.is_banned(target_user_id):
            response_text = f"⚠️ Пользователь ID <code>{target_user_id}</code> не заблокирован."
        else:
            db.unban_user(target_user_id)
            logger.info(f"User {target_user_id} unbanned by admin {update.effective_user.id}")
            response_text = f"✅ Пользователь ID <code>{target_user_id}</code> разблокирован."
            try:
                await context.bot.send_message(
                    target_user_id,
                    "✅ Вы были разблокированы и можете снова пользоваться ботом. Используйте /start."
                )
            except Exception as e:
                logger.warning(f"Could not notify unbanned user {target_user_id}: {e}")
    else:
        response_text = f"❌ Неизвестное действие админа: {action_type}"

    await update.message.reply_text(
        response_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_back_keyboard()
    )
    context.user_data.clear()
    return ADMIN_PANEL_CHOICE

def main():
    """Запуск бота"""
    application = Application.builder().token(API_TOKEN).build()

    # Админ ConversationHandler
    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_PANEL_CHOICE: [
                CallbackQueryHandler(admin_users_list, pattern="^admin_users_list$"),
                CallbackQueryHandler(admin_request_user_id, pattern="^admin_ban_user$"),
                CallbackQueryHandler(admin_request_user_id, pattern="^admin_unban_user$"),
                CallbackQueryHandler(admin_menu_return, pattern="^admin_menu_return$"),
                CallbackQueryHandler(main_menu_return, pattern="^main_menu_return$") # Allow returning to main menu from admin panel
            ],
            ADMIN_USER_ID_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_user_id),
                CallbackQueryHandler(admin_menu_return, pattern="^admin_menu_return$"), # Allow returning from ID input
                CallbackQueryHandler(main_menu_return, pattern="^main_menu_return$")
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(main_menu_return, pattern="^main_menu_return$"),
            CallbackQueryHandler(admin_menu_return, pattern="^admin_menu_return$") # Fallback for unknown callbacks in admin conv
        ],
        allow_reentry=True
    )

    # Регистрация ConversationHandler
    register_conv = ConversationHandler(
        entry_points=[CommandHandler("register", register_start)],
        states={
            REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(main_menu_return, pattern="^main_menu_return$") # Allow to cancel registration
        ],
        allow_reentry=True # Useful if a user types /register again during registration
    )

    # Симптомы ConversationHandler
    symptoms_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(symptoms_category, pattern="^symptoms_category$"),
            CallbackQueryHandler(symptoms_category_selected, pattern="^sym_cat_") # Direct entry via category button
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

    # Лекарства ConversationHandler
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

    # Дневник ConversationHandler
    diary_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(wellbeing_diary, pattern="^wellbeing_diary$"),
            CallbackQueryHandler(diary_add_entry, pattern="^diary_add_entry$"),
            CallbackQueryHandler(diary_view_entries, pattern="^diary_view_entries$")
        ],
        states={
            DIARY_MOOD: [
                CallbackQueryHandler(diary_mood_selected, pattern="^mood_"),
                # Keep these entries here to allow user to jump between add/view from diary menu
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
            CallbackQueryHandler(main_menu_return, pattern="^main_menu_return$"),
            # Allow returning to diary options from sub-steps
            CallbackQueryHandler(wellbeing_diary, pattern="^wellbeing_diary$")
        ],
        allow_reentry=True
    )

    # Напоминания ConversationHandler
    reminder_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(med_reminder, pattern="^med_reminder$"),
            CallbackQueryHandler(reminder_add_new, pattern="^reminder_add_new$"),
            CallbackQueryHandler(reminder_view_all, pattern="^reminder_view_all$")
        ],
        states={
            REMINDER_MED_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, reminder_med_name),
                # Keep these entries here to allow user to jump between add/view from reminder menu
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
            CallbackQueryHandler(main_menu_return, pattern="^main_menu_return$"),
            # Allow returning to reminder options from sub-steps
            CallbackQueryHandler(med_reminder, pattern="^med_reminder$")
        ],
        allow_reentry=True
    )

    # Добавление обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(register_conv)
    application.add_handler(symptoms_conv)
    application.add_handler(medicine_conv)
    application.add_handler(diary_conv)
    application.add_handler(reminder_conv)
    application.add_handler(admin_conv)

    # Добавление прямых обработчиков команд (для админа)
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))

    # Добавление глобальных обработчиков callback-запросов, которые не начинают Conversation
    application.add_handler(CallbackQueryHandler(emergency_help, pattern="^emergency_help$"))
    # The main_menu_return should be a global handler as well, to allow exiting any conversation
    # if a main_menu_return button is clicked in a fallback or at any stage.
    application.add_handler(CallbackQueryHandler(main_menu_return, pattern="^main_menu_return$"))


    # Обработчики неизвестных сообщений - всегда в конце
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_message))

    # Запуск бота
    logger.info("Starting Telegram bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Telegram bot stopped.")

if __name__ == "__main__":
    main()
