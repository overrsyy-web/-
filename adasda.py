import logging
from datetime import datetime
from typing import Dict, List, Optional
import json
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters
)

# ===== КОНФИГУРАЦИЯ =====
TOKEN = os.getenv('')

# Настройки
EMERGENCY_PHONES = {
    'скорая': '103',
    'полиция': '102',
    'мчс': '101',
    'единый': '112'
}

DISCLAIMER = """
⚠️ *ВАЖНО: Бот не заменяет врача!*

Информация предоставляется только в справочных целях.
При серьезных симптомах немедленно обратитесь к врачу или вызовите скорую помощь.
"""

# ===== СОСТОЯНИЯ ДЛЯ ConversationHandler =====
SYMPTOM_CATEGORY, SYMPTOM_DETAILS = range(2)
DIARY_SYMPTOMS, DIARY_TEMP, DIARY_PRESSURE = range(2, 4)
MEDICINE_NAME, MEDICINE_INFO = range(4, 6)

# ===== ЛОГИРОВАНИЕ =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(name)

# ===== БАЗА ДАННЫХ (В ПАМЯТИ) =====
class MemoryStorage:
    """Простое хранилище в памяти"""
    
    def init(self):
        self.users = {}
        self.health_records = {}
        self.medications = {}
        self.symptoms_history = {}
    
    def add_user(self, user_id: int, username: str, first_name: str):
        if user_id not in self.users:
            self.users[user_id] = {
                'id': user_id,
                'username': username,
                'first_name': first_name,
                'joined': datetime.now().isoformat()
            }
            self.health_records[user_id] = []
            self.medications[user_id] = []
            self.symptoms_history[user_id] = []
    
    def add_health_record(self, user_id: int, symptom: str, temperature: float = None, pressure: str = None):
        if user_id not in self.health_records:
            self.health_records[user_id] = []
        
        record = {
            'timestamp': datetime.now().isoformat(),
            'symptom': symptom,
            'temperature': temperature,
            'pressure': pressure
        }
        self.health_records[user_id].append(record)
        return record

# Инициализация хранилища
storage = MemoryStorage()

# База знаний симптомов
SYMPTOMS_KB = {
    "головная боль": {
        "description": "Боль в области головы различной интенсивности",
        "causes": ["Мигрень", "Напряжение", "Стресс", "Обезвоживание", "Гипертония"],
        "self_care": ["Отдых в тихом месте", "Прием обезболивающего (по инструкции)", "Холодный компресс на лоб", "Массаж висков"],
        "see_doctor": "Если боль сильная, внезапная, сопровождается тошнотой или нарушением зрения"
    },
    "температура": {
        "description": "Повышение температуры тела выше 37°C",
        "causes": ["Инфекция (вирусная/бактериальная)", "Воспалительный процесс", "Перегрев", "Реакция на прививку"],
        "self_care": ["Обильное теплое питье", "Отдых", "Жаропонижающее при температуре выше 38.5°C", "Прохладные компрессы"],
        "see_doctor": "Если температура выше 39°C, держится более 3 дней или есть другие симптомы"
    },
    "кашель": {
        "description": "Рефлекторное очищение дыхательных путей",
        "causes": ["Простуда", "Бронхит", "Аллергия", "COVID-19", "Курение"],
        "self_care": ["Теплое питье (чай с медом)", "Увлажнение воздуха", "Пастилки от кашля", "Ингаляции"],
        "see_doctor": "Если кашель длится более 2 недель, с кровью, сопровождается одышкой"
        },
    "боль в горле": {
        "description": "Дискомфорт, першение или боль при глотании",
        "causes": ["Фарингит", "Тонзиллит", "Ларингит", "Аллергия", "Перенапряжение связок"],
        "self_care": ["Полоскание соленой водой", "Теплое питье", "Пастилки", "Увлажнение воздуха"],
        "see_doctor": "Если боль сильная, затруднено дыхание или глотание, высокая температура"
    },
    "тошнота": {
        "description": "Ощущение подступающей рвоты",
        "causes": ["Расстройство ЖКТ", "Пищевое отравление", "Мигрень", "Укачивание", "Беременность"],
        "self_care": ["Небольшие глотки воды", "Свежий воздух", "Имбирный чай", "Отдых в положении полусидя"],
        "see_doctor": "Если сопровождается сильной болью, рвотой, обезвоживанием"
    }
}

# ===== КЛАВИАТУРЫ =====
def get_main_keyboard() -> List[List[KeyboardButton]]:
    """Главное меню"""
    return [
        [KeyboardButton("🩺 Симптомы"), KeyboardButton("💊 Лекарства")],
        [KeyboardButton("🚨 Экстренная помощь"), KeyboardButton("📋 Дневник")],
        [KeyboardButton("⏰ Напоминания"), KeyboardButton("ℹ️ Помощь")]
    ]

def get_symptoms_keyboard() -> List[List[KeyboardButton]]:
    """Клавиатура симптомов"""
    return [
        [KeyboardButton("Головная боль"), KeyboardButton("Температура")],
        [KeyboardButton("Кашель"), KeyboardButton("Боль в горле")],
        [KeyboardButton("Тошнота"), KeyboardButton("Другое")],
        [KeyboardButton("⬅️ Назад")]
    ]

def get_emergency_keyboard() -> List[List[KeyboardButton]]:
    """Клавиатура экстренной помощи"""
    return [
        [KeyboardButton("🚑 Вызвать скорую")],
        [KeyboardButton("📞 Телефоны"), KeyboardButton("🆘 Первая помощь")],
        [KeyboardButton("🔍 Проверить симптомы"), KeyboardButton("⬅️ Назад")]
    ]

def get_diary_keyboard() -> List[List[KeyboardButton]]:
    """Клавиатура дневника"""
    return [
        [KeyboardButton("➕ Новая запись"), KeyboardButton("📊 Статистика")],
        [KeyboardButton("📋 История"), KeyboardButton("⬅️ Назад")]
    ]

def get_yes_no_keyboard() -> List[List[KeyboardButton]]:
    """Клавиатура Да/Нет"""
    return [
        [KeyboardButton("✅ Да"), KeyboardButton("❌ Нет")],
        [KeyboardButton("⬅️ Отмена")]
    ]

# ===== ОСНОВНЫЕ КОМАНДЫ =====
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user = update.effective_user
    storage.add_user(user.id, user.username, user.first_name)
    
    welcome_text = f"""
👋 *Добро пожаловать, {user.first_name}!*

Я - ваш медицинский помощник. Я помогу:
• Оценить симптомы
• Найти информацию о лекарствах
• Вести дневник самочувствия
• Настроить напоминания

{DISCLAIMER}

Выберите действие в меню ниже:
    """
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup(get_main_keyboard(), resize_keyboard=True)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    help_text = f"""
📋 *Доступные функции:*

• *🩺 Симптомы* - информация по симптомам и рекомендации
• *💊 Лекарства* - поиск информации о лекарствах
• *🚨 Экстренная помощь* - телефоны и инструкции
• *📋 Дневник* - отслеживание самочувствия
• *⏰ Напоминания* - напоминания о приёме лекарств

*Основные команды:*
/start - Начать работу
/help - Помощь
/diary - Открыть дневник
/emergency - Экстренная помощь

{DISCLAIMER}
    """
    
    await update.message.reply_text(
        help_text,
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup(get_main_keyboard(), resize_keyboard=True)
    )

# ===== ОБРАБОТЧИКИ КНОПОК ГЛАВНОГО МЕНЮ =====
async def handle_symptoms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки 'Симптомы'"""
    await update.message.reply_text(
        "🩺 *Выберите симптом или опишите свой:*",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup(get_symptoms_keyboard(), resize_keyboard=True)
    )
async def handle_emergency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки 'Экстренная помощь'"""
    await update.message.reply_text(
        "🚨 *Экстренная помощь*\n\nВ критических ситуациях немедленно звоните 103 или 112!",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup(get_emergency_keyboard(), resize_keyboard=True)
    )

async def handle_diary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки 'Дневник'"""
    await update.message.reply_text(
        "📋 *Дневник самочувствия*\n\nЗаписывайте симптомы, температуру и другие показатели.",
        parse_mode='Markdown',
        reply_markup=ReplyKeyboardMarkup(get_diary_keyboard(), resize_keyboard=True)
    )

async def handle_medicines(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки 'Лекарства'"""
    keyboard = [
        [InlineKeyboardButton("🔍 Поиск лекарства", callback_data="search_medicine")],
        [InlineKeyboardButton("📋 Инструкции", callback_data="instructions")],
        [InlineKeyboardButton("💊 Аналоги", callback_data="analogs")],
        [InlineKeyboardButton("⚠️ Взаимодействия", callback_data="interactions")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "💊 *Информация о лекарствах*\n\nВыберите действие:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def handle_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки 'Назад'"""
    await update.message.reply_text(
        "Главное меню:",
        reply_markup=ReplyKeyboardMarkup(get_main_keyboard(), resize_keyboard=True)
    )

# ===== ОБРАБОТКА СИМПТОМОВ =====
async def handle_symptom_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка выбора конкретного симптома"""
    symptom_text = update.message.text.lower()
    
    if symptom_text == "⬅️ назад":
        await handle_back(update, context)
        return
    
    if symptom_text in ["другое", "другой"]:
        await update.message.reply_text(
            "Опишите ваши симптомы своими словами:"
        )
        # Здесь можно добавить состояние для ожидания описания
        return
    
    # Поиск в базе симптомов
    symptom_key = None
    for key in SYMPTOMS_KB:
        if key in symptom_text or symptom_text in key:
            symptom_key = key
            break
    
    if symptom_key and symptom_key in SYMPTOMS_KB:
        info = SYMPTOMS_KB[symptom_key]
        
        response = f"""
*{symptom_key.upper()}*

📝 *Описание:* {info['description']}

🔍 *Возможные причины:*
{chr(10).join(['• ' + cause for cause in info['causes']])}

💡 *Что можно сделать:*
{chr(10).join(['• ' + care for care in info['self_care']])}

⚠️ *Обратиться к врачу, если:*
{info['see_doctor']}

{DISCLAIMER}
        """
        
        # Сохраняем в историю симптомов
        user_id = update.effective_user.id
        storage.symptoms_history[user_id].append({
            'symptom': symptom_key,
            'timestamp': datetime.now().isoformat()
        })
        
        await update.message.reply_text(response, parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "Информация по этому симптому временно недоступна. "
            "Рекомендуем обратиться к врачу для консультации."
        )

# ===== ЭКСТРЕННАЯ ПОМОЩЬ =====
async def handle_call_ambulance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Вызов скорой помощи"""
    response = """
🚑 *ВЫЗОВ СКОРОЙ ПОМОЩИ*

*Телефон:* 103 (или 112 с мобильного)

*Что говорить оператору:*
1. Четко назовите адрес
2. Опишите симптомы
3. Назовите возраст пациента
4. Укажите особые обстоятельства
5. Не вешайте трубку первым

*Когда вызывать скорую:*
• Потеря сознания
• Затрудненное дыхание
• Сильная боль в груди
• Обильное кровотечение
• Судороги
• Подозрение на инсульт/инфаркт
*Другие номера:*
• Полиция: 102
• МЧС: 101
• Единый: 112
    """
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def handle_emergency_phones(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Телефоны экстренных служб"""
    phones_text = "📞 *Телефоны экстренных служб:*\n\n"
    
    for service, number in EMERGENCY_PHONES.items():
        phones_text += f"• *{service.capitalize()}*: {number}\n"
    
    phones_text += "\n*112* - единый номер (работает без SIM-карты)"
    
    await update.message.reply_text(phones_text, parse_mode='Markdown')

async def handle_first_aid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Первая помощь"""
    keyboard = [
        [InlineKeyboardButton("🫁 Остановка дыхания", callback_data="aid_breathing")],
        [InlineKeyboardButton("🩸 Кровотечение", callback_data="aid_bleeding")],
        [InlineKeyboardButton("🔥 Ожоги", callback_data="aid_burns")],
        [InlineKeyboardButton("🤕 Обморок", callback_data="aid_faint")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🆘 *Первая помощь - основные принципы:*\n\n"
        "1. *Обеспечьте безопасность* - себе и пострадавшему\n"
        "2. *Проверьте сознание* - окликните, аккуратно потрясите\n"
        "3. *Вызовите скорую* - 103 или 112\n"
        "4. *Окажите помощь* - согласно ситуации\n\n"
        "Выберите конкретную ситуацию:",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def handle_check_symptoms(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверка симптомов на экстренность"""
    await update.message.reply_text(
        "🔍 *Проверка симптомов*\n\n"
        "Опишите ваши симптомы одним сообщением. "
        "Я проверю, требуют ли они экстренной помощи.\n\n"
        "*Пример:* 'сильная головная боль с тошнотой и головокружением'"
    )

# ===== ДНЕВНИК САМОЧУВСТВИЯ =====
async def handle_new_record(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Новая запись в дневнике"""
    await update.message.reply_text(
        "📝 *Новая запись в дневнике*\n\n"
        "Опишите ваши симптомы (одним сообщением):\n"
        "*Пример:* 'головная боль, слабость'"
    )
    # Здесь можно было бы установить состояние для диалога

async def handle_diary_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Статистика дневника"""
    user_id = update.effective_user.id
    
    if user_id not in storage.health_records or not storage.health_records[user_id]:
        await update.message.reply_text("У вас пока нет записей в дневнике.")
        return
    
    records = storage.health_records[user_id]
    total = len(records)
    latest = records[-1]
    
    # Анализ частых симптомов
    symptoms_count = {}
    for record in records:
        symptom = record.get('symptom', 'не указано')
        symptoms_count[symptom] = symptoms_count.get(symptom, 0) + 1
    
    frequent_symptoms = sorted(symptoms_count.items(), key=lambda x: x[1], reverse=True)[:3]
    
    response = f"""
📊 *Ваша статистика:*

• Всего записей: {total}
• Последняя запись: {datetime.fromisoformat(latest['timestamp']).strftime('%d.%m.%Y %H:%M')}

📈 *Частые симптомы:*
{chr(10).join([f'• {symptom}: {count} раз' for symptom, count in frequent_symptoms])}

💡 *Рекомендация:* Ведите записи регулярно для отслеживания динамики.
    """
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def handle_diary_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """История записей дневника"""
    user_id = update.effective_user.id
    
    if user_id not in storage.health_records or not storage.health_records[user_id]:
        await update.message.reply_text("История записей пуста.")
        return
    
    records = storage.health_records[user_id][-5:]  # Последние 5 записей
    history_text = "📋 *Последние записи:*\n\n"
    
    for i, record in enumerate(reversed(records), 1):
        date = datetime.fromisoformat(record['timestamp']).strftime('%d.%m.%Y %H:%M')
        symptom = record.get('symptom', 'не указано')
        temp = record.get('temperature')
        pressure = record.get('pressure')
        
        history_text += f"*{i}. {date}*\n"
        history_text += f"Симптомы: {symptom}\n"
        if temp:
            history_text += f"Температура: {temp}°C\n"
        if pressure:
            history_text += f"Давление: {pressure}\n"
        history_text += "\n"
    
    await update.message.reply_text(history_text, parse_mode='Markdown')

# ===== ОБРАБОТКА ИНЛАЙН-КНОПОК =====
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик инлайн-кнопок"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "search_medicine":
        await query.edit_message_text(
            "💊 *Поиск лекарства*\n\n"
            "Введите название лекарства (например, 'нурофен'):",
            parse_mode='Markdown'
        )
    
    elif data == "instructions":
        await query.edit_message_text(
            "📋 *Инструкции по применению*\n\n"
            "1. Всегда читайте инструкцию перед применением\n"
            "2. Соблюдайте дозировку\n"
            "3. Учитывайте противопоказания\n"
            "4. Храните лекарства правильно\n\n"
            "Введите название лекарства для получения конкретной инструкции:",
            parse_mode='Markdown'
        )
    
    elif data == "analogs":
        await query.edit_message_text(
            "💊 *Поиск аналогов*\n\n"
            "Аналоги - лекарства с одинаковым действующим веществом, но разными названиями.\n\n"
            "Введите название лекарства для поиска аналогов:",
            parse_mode='Markdown'
        )
    
    elif data == "interactions":
        await query.edit_message_text(
            "⚠️ *Взаимодействие лекарств*\n\n"
            "Некоторые лекарства нельзя принимать вместе.\n\n"
            "Введите названия лекарств через запятую (например, 'парацетамол, ибупрофен'):",
            parse_mode='Markdown'
        )
    
    elif data.startswith("aid_"):
        aid_type = data.split("_")[1]
        aid_responses = {
            "breathing": """
🫁 *Остановка дыхания:*
1. Убедитесь в безопасности
2. Вызовите скорую (103)
3. Наклоните голову назад, откройте рот
4. Проверьте дыхание (10 секунд)
5. Если нет дыхания - начните сердечно-легочную реанимацию
6. 30 нажатий на грудную клетку, затем 2 вдоха
7. Продолжайте до приезда скорой
            """,
            "bleeding": """
🩸 *Кровотечение:*
1. Наденьте перчатки если есть
2. Приподнимите поврежденную часть тела
3. Наложите давящую повязку
4. При сильном кровотечении - жгут выше раны
5. Запишите время наложения жгута
6. Вызовите скорую (103)
            """,
            "burns": """
🔥 *Ожоги:*
1. Уберите источник ожога
2. Охлаждайте проточной водой 15-20 минут
3. НЕ прокалывайте пузыри
4. Накройте чистой тканью
5. При серьезных ожогах вызовите скорую (103)
6. НЕ используйте масло, мази, лед
            """,
            "faint": """
🤕 *Обморок:*
1. Уложите на спину, приподнимите ноги
2. Обеспечьте приток воздуха
3. Расстегните тесную одежду
4. Не давайте воду/лекарства если человек без сознания
5. При длительном обмороке вызовите скорую (103)
            """
        }
        
        if aid_type in aid_responses:
            await query.edit_message_text(
                aid_responses[aid_type],
                parse_mode='Markdown'
            )

# ===== ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ =====
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка текстовых сообщений"""
    text = update.message.text
    
    # Проверяем, не является ли сообщение описанием симптомов для проверки
    if text and len(text) > 10:  # Если сообщение достаточно длинное
        # Проверяем на критические симптомы
        critical_keywords = [
            'не дышу', 'задыхаюсь', 'остановка сердца', 'без сознания',
            'сильное кровотечение', 'инсульт', 'инфаркт', 'утопление'
        ]
        
        text_lower = text.lower()
        is_critical = any(keyword in text_lower for keyword in critical_keywords)
        
        if is_critical:
            await update.message.reply_text(
                "🚨 *НЕМЕДЛЕННО ВЫЗЫВАЙТЕ СКОРУЮ ПОМОЩЬ!*\n\n"
                "📞 Наберите *103* или *112* прямо сейчас!\n\n"
                "Опишите симптомы оператору четко и спокойно.",
                parse_mode='Markdown'
            )
            return
    
    # Если это не критический случай и не кнопка меню, обрабатываем как запись в дневник
    if text and text not in ["🩺 Симптомы", "💊 Лекарства", "🚨 Экстренная помощь", 
                             "📋 Дневник", "⏰ Напоминания", "ℹ️ Помощь",
                             "⬅️ Назад", "➕ Новая запись", "📊 Статистика",
                             "📋 История", "🚑 Вызвать скорую", "📞 Телефоны",
                             "🆘 Первая помощь", "🔍 Проверить симптомы",
                             "Головная боль", "Температура", "Кашель",
                             "Боль в горле", "Тошнота", "Другое"]:
        
        # Добавляем как запись в дневник
        user_id = update.effective_user.id
        storage.add_health_record(user_id, text)
        
        await update.message.reply_text(
            "✅ *Запись сохранена в дневнике*\n\n"
            "Вы можете просмотреть историю записей в разделе '📋 Дневник' -> '📋 История'",
            parse_mode='Markdown'
        )

# ===== НАПОМИНАНИЯ =====
async def handle_reminders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки 'Напоминания'"""
    response = """
⏰ *Напоминания о приёме лекарств*

*Для настройки напоминаний:*
1. Укажите название лекарства
2. Дозировку
3. Время приёма
4. Частоту

*Пример:* 'Нурофен, 1 таблетка, 8:00, 12:00, 20:00'

*Доступные команды:*
/reminder_add - Добавить напоминание
/reminder_list - Список напоминаний
/reminder_delete - Удалить напоминание

⚠️ *Не забывайте принимать лекарства строго по назначению врача!*
    """
    
    await update.message.reply_text(response, parse_mode='Markdown')

async def reminder_add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Добавление напоминания"""
    await update.message.reply_text(
        "Добавление напоминания:\n\n"
        "Введите в формате:\n"
        "*Название - Дозировка - Время*\n\n"
        "*Пример:* Парацетамол - 1 таблетка - 08:00, 20:00",
        parse_mode='Markdown'
    )

# ===== ОСНОВНАЯ ФУНКЦИЯ =====
def main() -> None:
    """Запуск бота"""
    # Создаем Application
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("diary", handle_diary))
    application.add_handler(CommandHandler("emergency", handle_emergency))
    application.add_handler(CommandHandler("reminder_add", reminder_add_command))
    
    # Регистрируем обработчики кнопок
    application.add_handler(MessageHandler(filters.Text(["🩺 Симптомы"]), handle_symptoms))
    application.add_handler(MessageHandler(filters.Text(["💊 Лекарства"]), handle_medicines))
    application.add_handler(MessageHandler(filters.Text(["🚨 Экстренная помощь"]), handle_emergency))
    application.add_handler(MessageHandler(filters.Text(["📋 Дневник"]), handle_diary))
    application.add_handler(MessageHandler(filters.Text(["⏰ Напоминания"]), handle_reminders))
    application.add_handler(MessageHandler(filters.Text(["ℹ️ Помощь"]), help_command))
    application.add_handler(MessageHandler(filters.Text(["⬅️ Назад"]), handle_back))
    
    # Обработчики симптомов
    symptom_buttons = ["Головная боль", "Температура", "Кашель", "Боль в горле", "Тошнота", "Другое"]
    application.add_handler(MessageHandler(filters.Text(symptom_buttons), handle_symptom_selection))
    
    # Обработчики экстренной помощи
    application.add_handler(MessageHandler(filters.Text(["🚑 Вызвать скорую"]), handle_call_ambulance))
    application.add_handler(MessageHandler(filters.Text(["📞 Телефоны"]), handle_emergency_phones))
    application.add_handler(MessageHandler(filters.Text(["🆘 Первая помощь"]), handle_first_aid))
    application.add_handler(MessageHandler(filters.Text(["🔍 Проверить симптомы"]), handle_check_symptoms))
    
    # Обработчики дневника
    application.add_handler(MessageHandler(filters.Text(["➕ Новая запись"]), handle_new_record))
    application.add_handler(MessageHandler(filters.Text(["📊 Статистика"]), handle_diary_stats))
    application.add_handler(MessageHandler(filters.Text(["📋 История"]), handle_diary_history))
    
    # Обработчик инлайн-кнопок
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Обработчик текстовых сообщений (должен быть последним)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # Запускаем бота
    print("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if name == 'main':
    # Запуск бота
    main()
