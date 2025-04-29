import telebot
from telebot import types
import os
import sqlite3
import re
import threading
import time
from datetime import datetime

TOKEN = 'ttt'
bot = telebot.TeleBot(TOKEN)

MAX_DBS_PER_USER = 20


def create_user_folder(chat_id):
    if not os.path.exists("users_data"):
        os.mkdir("users_data")
    user_folder = f"users_data/{chat_id}"
    if not os.path.exists(user_folder):
        os.mkdir(user_folder)
    return user_folder


def can_create_more_dbs(chat_id):
    user_folder = create_user_folder(chat_id)
    existing_dbs = [f for f in os.listdir(user_folder) if f.endswith('.sqlite')]
    return len(existing_dbs) < MAX_DBS_PER_USER


def is_valid_db_name(name):
    return bool(re.match(r'^[a-zA-Z0-9_]+$', name))


def create_db_if_not_exists(chat_id, db_name):
    user_folder = create_user_folder(chat_id)
    db_path = f"{user_folder}/{db_name}.sqlite"

    if os.path.exists(db_path):
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS problems (
            problem_id INTEGER PRIMARY KEY AUTOINCREMENT,
            problem TEXT NOT NULL,
            time_create DATETIME DEFAULT CURRENT_TIMESTAMP,
            time_send DATETIME NOT NULL,
            confirmed BOOLEAN DEFAULT FALSE,
            last_notification DATETIME  
        )"""
    )
    conn.commit()
    conn.close()
    return True



def get_user_dbs(chat_id):
    user_folder = create_user_folder(chat_id)
    return [f for f in os.listdir(user_folder) if f.endswith('.sqlite')]


def add_problem_to_db(chat_id, db_name, problem, time_send):
    user_folder = create_user_folder(chat_id)
    db_path = f"{user_folder}/{db_name}.sqlite"

    if not os.path.exists(db_path):
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO problems (problem, time_send) VALUES (?, ?)",
        (problem, time_send)
    )
    conn.commit()
    conn.close()
    return True


def get_problems_from_db(chat_id, db_name):
    user_folder = create_user_folder(chat_id)
    db_path = f"{user_folder}/{db_name}.sqlite"

    if not os.path.exists(db_path):
        return None

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT problem_id, problem, time_create, time_send FROM problems")
    problems = cursor.fetchall()
    conn.close()
    return problems


def delete_problem_from_db(chat_id, db_name, problem_id):
    user_folder = create_user_folder(chat_id)
    db_path = f"{user_folder}/{db_name}.sqlite"

    if not os.path.exists(db_path):
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM problems WHERE problem_id = ?",
        (problem_id,)
    )
    conn.commit()
    conn.close()
    return True


# Команда /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_folder = create_user_folder(message.chat.id)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📅 Распорядок дня", "✅ Текущая задача")

    bot.send_message(
        message.chat.id,
        f"🔹 Ваша папка: `{user_folder}`\n"
        f"Максимум БД: {MAX_DBS_PER_USER}\n"
        "Используйте /newproblemlist для создания базы задач.\n"
        "Используйте /delproblemlist для удаления базы.\n"
        "Используйте /addproblem для добавления задачи.\n"
        "Используйте /delproblem для удаления задачи.",
        reply_markup=markup,
        parse_mode="Markdown"
    )


# Команда /newproblemlist
@bot.message_handler(commands=['newproblemlist'])
def handle_new_problem(message):
    chat_id = message.chat.id

    if not can_create_more_dbs(chat_id):
        bot.send_message(chat_id, f"❌ Превышен лимит ({MAX_DBS_PER_USER} БД на пользователя)!")
        return

    msg = bot.send_message(
        chat_id,
        "📝 Введите название для базы данных (только латиница, цифры и _):",
        reply_markup=types.ForceReply(selective=True)
    )
    bot.register_next_step_handler(msg, process_db_name)


def process_db_name(message):
    chat_id = message.chat.id
    db_name = message.text.strip()

    if not db_name:
        bot.send_message(chat_id, "❌ Название не может быть пустым!")
        return

    if not is_valid_db_name(db_name):
        bot.send_message(chat_id, "❌ Можно использовать только латинские буквы, цифры и _!")
        return

    if not can_create_more_dbs(chat_id):
        bot.send_message(chat_id, f"❌ У вас уже {MAX_DBS_PER_USER} БД! Новые создавать нельзя.")
        return

    try:
        if create_db_if_not_exists(chat_id, db_name):
            bot.send_message(chat_id, f"✅ База данных `{db_name}.sqlite` создана!", parse_mode="Markdown")
        else:
            bot.send_message(chat_id, f"❌ Файл `{db_name}.sqlite` уже существует!", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ошибка: {str(e)}")


# Команда /delproblemlist
@bot.message_handler(commands=['delproblemlist'])
def handle_delete_problem_list(message):
    chat_id = message.chat.id
    dbs = get_user_dbs(chat_id)

    if not dbs:
        bot.send_message(chat_id, "❌ У вас нет ни одной БД для удаления!")
        return

    markup = types.InlineKeyboardMarkup()
    for db in dbs:
        markup.add(types.InlineKeyboardButton(db, callback_data=f"delete_db:{db}"))

    bot.send_message(
        chat_id,
        "🗑 Выберите БД для удаления:",
        reply_markup=markup
    )


# Обработчик кнопок удаления БД
@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_db:"))
def handle_delete_db(call):
    chat_id = call.message.chat.id
    db_name = call.data.split(":")[1]
    user_folder = create_user_folder(chat_id)
    db_path = f"{user_folder}/{db_name}"

    try:
        os.remove(db_path)
        bot.answer_callback_query(call.id, f"✅ {db_name} удалена!")
        bot.edit_message_text(
            f"🗑 База данных `{db_name}` успешно удалена.",
            chat_id,
            call.message.message_id
        )
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")


# Команда /addproblem
@bot.message_handler(commands=['addproblem'])
def handle_add_problem(message):
    chat_id = message.chat.id
    command_parts = message.text.split()

    if len(command_parts) < 2:
        bot.send_message(
            chat_id,
            "❌ Неверный формат!\n"
            "Пример: `/addproblem problem1:wakeup:1:8:45`\n"
            "Или: `/addproblem problem1:wakeup::8:45` (дата = сегодня)",
            parse_mode="Markdown"
        )
        return

    args = command_parts[1].split(':')
    if len(args) < 5:
        bot.send_message(
            chat_id,
            "❌ Не хватает параметров!\n"
            "Формат: `название_бд:задача:день:часы:минуты`\n"
            "Пример: `problem1:wakeup:1:8:45`",
            parse_mode="Markdown"
        )
        return

    db_name = args[0]
    problem_text = args[1]
    day = args[2]
    hours = args[3]
    minutes = args[4]

    # Проверка времени (часы и минуты обязательны)
    if not hours.isdigit() or not minutes.isdigit():
        bot.send_message(chat_id, "❌ Часы и минуты должны быть числами!")
        return

    hours = int(hours)
    minutes = int(minutes)

    if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
        bot.send_message(chat_id, "❌ Часы (0-23) и минуты (0-59) должны быть в допустимом диапазоне!")
        return

    # Если день не указан, берём сегодняшний
    if not day:
        today = datetime.now().day
        day = str(today)
    elif not day.isdigit():
        bot.send_message(chat_id, "❌ День должен быть числом (1-31) или пустым!")
        return

    day = int(day)
    if day < 1 or day > 31:
        bot.send_message(chat_id, "❌ День должен быть от 1 до 31!")
        return

    # Формируем дату (год и месяц берём текущие)
    now = datetime.now()
    try:
        time_send = datetime(now.year, now.month, day, hours, minutes).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        bot.send_message(chat_id, "❌ Некорректная дата (например, 31 февраля)!")
        return

    # Проверяем, существует ли БД
    user_folder = create_user_folder(chat_id)
    db_path = f"{user_folder}/{db_name}.sqlite"
    if not os.path.exists(db_path):
        bot.send_message(chat_id, f"❌ База данных `{db_name}.sqlite` не существует!", parse_mode="Markdown")
        return

    # Добавляем задачу в БД
    if add_problem_to_db(chat_id, db_name, problem_text, time_send):
        # Показываем список задач
        problems = get_problems_from_db(chat_id, db_name)
        if not problems:
            bot.send_message(chat_id, f"✅ Задача добавлена, но список задач пуст.")
            return

        tasks_list = "📋 Список задач:\n"
        for task in problems:
            task_id, task_text, time_create, time_send = task
            tasks_list += (
                f"🔹 ID: {task_id}\n"
                f"📌 Задача: {task_text}\n"
                f"🕒 Создана: {time_create}\n"
                f"⏰ Выполнить: {time_send}\n\n"
            )

        bot.send_message(chat_id, tasks_list)
    else:
        bot.send_message(chat_id, "❌ Ошибка при добавлении задачи!")


# Команда /delproblem
@bot.message_handler(commands=['delproblem'])
def handle_delete_problem(message):
    chat_id = message.chat.id
    command_parts = message.text.split()

    if len(command_parts) < 2:
        bot.send_message(
            chat_id,
            "❌ Укажите название БД!\n"
            "Пример: `/delproblem tasks1`",
            parse_mode="Markdown"
        )
        return

    db_name = command_parts[1]
    user_folder = create_user_folder(chat_id)
    db_path = f"{user_folder}/{db_name}.sqlite"

    if not os.path.exists(db_path):
        bot.send_message(chat_id, f"❌ База данных `{db_name}.sqlite` не существует!", parse_mode="Markdown")
        return

    problems = get_problems_from_db(chat_id, db_name)
    if not problems:
        bot.send_message(chat_id, "❌ В этой БД нет задач для удаления!")
        return

    markup = types.InlineKeyboardMarkup()
    for task in problems:
        task_id, task_text, _, time_send = task
        markup.add(
            types.InlineKeyboardButton(
                f"❌ {task_id}: {task_text} (до {time_send})",
                callback_data=f"delete_task:{db_name}:{task_id}"
            )
        )

    bot.send_message(
        chat_id,
        "🗑 Выберите задачу для удаления:",
        reply_markup=markup
    )


# Обработчик кнопок удаления задачи
@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_task:"))
def handle_delete_task(call):
    chat_id = call.message.chat.id
    _, db_name, problem_id = call.data.split(':')

    if delete_problem_from_db(chat_id, db_name, problem_id):
        bot.answer_callback_query(call.id, "✅ Задача удалена!")
        bot.edit_message_text(
            f"🗑 Задача в `{db_name}.sqlite` (ID: {problem_id}) удалена.",
            chat_id,
            call.message.message_id
        )
    else:
        bot.answer_callback_query(call.id, "❌ Ошибка при удалении!")


@bot.message_handler(commands=['time_date'])
def handle_time_date(message):
    try:
        # Получаем текущее время сервера
        server_time = datetime.now()
        time_str = server_time.strftime("%Y-%m-%d %H:%M:%S")
        timezone_str = time.tzname[0]  # Получаем название часового пояса

        # Дополнительная диагностика
        timestamp = time.time()
        localtime = time.localtime()
        gmtime = time.gmtime()

        response = (
            f"⏰ <b>Текущее время сервера</b>:\n"
            f"• Дата и время: <code>{time_str}</code>\n"
            f"• Часовой пояс: <code>{timezone_str}</code>\n"
            f"• Timestamp: <code>{timestamp}</code>\n\n"
            f"<b>Сравнение</b>:\n"
            f"• Локальное время: <code>{time.strftime('%Y-%m-%d %H:%M:%S', localtime)}</code>\n"
            f"• UTC время: <code>{time.strftime('%Y-%m-%d %H:%M:%S', gmtime)}</code>\n\n"
            f"Если время неверное, проверьте:\n"
            f"1) Настройки часового пояса сервера\n"
            f"2) Сервис синхронизации времени (ntpd)\n"
            f"3) Docker-контейнер (если используется)"
        )

        bot.send_message(message.chat.id, response, parse_mode="HTML")

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка при получении времени: {str(e)}")


@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_task:"))
def handle_confirmation(call):
    try:
        _, db_name, task_id = call.data.split(":")
        chat_id = call.message.chat.id

        confirm_task_in_db(chat_id, db_name, task_id)

        bot.edit_message_text(
            "✅ Задача подтверждена",
            chat_id=chat_id,
            message_id=call.message.message_id
        )
        bot.answer_callback_query(call.id, "Вы приступили к задаче!")

    except Exception as e:
        print(f"Ошибка подтверждения: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка подтверждения!")




import threading
import time
from datetime import datetime
import pytz


def confirm_task_in_db(chat_id, db_name, task_id):
    user_folder = create_user_folder(chat_id)
    db_path = f"{user_folder}/{db_name}.sqlite"

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE problems SET confirmed = TRUE WHERE problem_id = ?",
        (task_id,)
    )
    conn.commit()
    conn.close()


def check_and_notify():
    msk_timezone = pytz.timezone('Europe/Moscow')

    while True:
        try:
            now_msk = datetime.now(msk_timezone)
            current_time_str = now_msk.strftime("%Y-%m-%d %H:%M:%S")

            for user_folder in os.listdir("users_data"):
                if not user_folder.isdigit():
                    continue

                chat_id = int(user_folder)
                user_dbs = get_user_dbs(chat_id)

                for db_name in user_dbs:
                    clean_db_name = db_name.replace(".sqlite", "")
                    db_path = f"users_data/{user_folder}/{db_name}"

                    try:
                        conn = sqlite3.connect(db_path)
                        cursor = conn.cursor()

                        # Проверяем и добавляем недостающие столбцы
                        cursor.execute("PRAGMA table_info(problems)")
                        columns = [col[1] for col in cursor.fetchall()]

                        if 'confirmed' not in columns:
                            cursor.execute("ALTER TABLE problems ADD COLUMN confirmed BOOLEAN DEFAULT FALSE")
                        if 'last_notification' not in columns:
                            cursor.execute("ALTER TABLE problems ADD COLUMN last_notification DATETIME")

                        conn.commit()

                        # Получаем неподтвержденные задачи
                        cursor.execute(
                            """SELECT problem_id, problem, time_send, last_notification 
                               FROM problems 
                               WHERE confirmed = FALSE AND time_send <= ?""",
                            (current_time_str,)
                        )
                        tasks = cursor.fetchall()

                        for task in tasks:
                            task_id, task_text, time_send, last_notif = task

                            # Преобразуем last_notif в aware datetime если оно есть
                            if last_notif:
                                last_notif_dt = datetime.strptime(last_notif, "%Y-%m-%d %H:%M:%S")
                                last_notif_dt = msk_timezone.localize(last_notif_dt)
                            else:
                                last_notif_dt = None

                            # Проверяем необходимость напоминания
                            if last_notif_dt is None:
                                need_reminder = True
                            else:
                                time_diff = (now_msk - last_notif_dt).total_seconds()
                                need_reminder = time_diff >= 120  # 2 минуты

                            if need_reminder:
                                markup = types.InlineKeyboardMarkup()
                                confirm_btn = types.InlineKeyboardButton(
                                    "✅ Подтвердить выполнение",
                                    callback_data=f"confirm_task:{clean_db_name}:{task_id}"
                                )
                                markup.add(confirm_btn)

                                bot.send_message(
                                    chat_id,
                                    f"🔔 Напоминание\nЗадача: {task_text}\nВремя: {time_send}",
                                    reply_markup=markup
                                )

                                # Обновляем время последнего уведомления
                                cursor.execute(
                                    "UPDATE problems SET last_notification = ? WHERE problem_id = ?",
                                    (current_time_str, task_id)
                                )
                                conn.commit()

                    except Exception as e:
                        print(f"Ошибка при работе с БД {db_name}: {e}")
                    finally:
                        if conn:
                            conn.close()

            time.sleep(60 - datetime.now().second)

        except Exception as e:
            print(f"Ошибка в check_and_notify: {e}")
            time.sleep(10)


def update_existing_dbs():
    for user_folder in os.listdir("users_data"):
        if not user_folder.isdigit():
            continue

        for db_file in os.listdir(f"users_data/{user_folder}"):
            if db_file.endswith(".sqlite"):
                conn = sqlite3.connect(f"users_data/{user_folder}/{db_file}")
                cursor = conn.cursor()

                # Добавляем столбцы, если их нет
                cursor.execute("PRAGMA table_info(problems)")
                columns = [col[1] for col in cursor.fetchall()]

                if "confirmed" not in columns:
                    cursor.execute("ALTER TABLE problems ADD COLUMN confirmed BOOLEAN DEFAULT FALSE")

                if "last_notification" not in columns:
                    cursor.execute("ALTER TABLE problems ADD COLUMN last_notification DATETIME")

                conn.commit()
                conn.close()


if __name__ == '__main__':
    update_existing_dbs()  # Вызываем один раз
    reminder_thread = threading.Thread(target=check_and_notify, daemon=True)
    reminder_thread.start()
    bot.polling(none_stop=True)



#def update_all_databases():
#    for user_folder in os.listdir("users_data"):
#        if not user_folder.isdigit():
#            continue
#
#        for db_file in os.listdir(f"users_data/{user_folder}"):
#            if db_file.endswith(".sqlite"):
#                try:
#                    conn = sqlite3.connect(f"users_data/{user_folder}/{db_file}")
#                    cursor = conn.cursor()
#
#                    cursor.execute("PRAGMA table_info(problems)")
#                    columns = [col[1] for col in cursor.fetchall()]
#
#                    if 'confirmed' not in columns:
#                        cursor.execute("ALTER TABLE problems ADD COLUMN confirmed BOOLEAN DEFAULT FALSE")
#                        print(f"Added 'confirmed' to {user_folder}/{db_file}")
#
#                    if 'last_notification' not in columns:
#                        cursor.execute("ALTER TABLE problems ADD COLUMN last_notification DATETIME")
#                        print(f"Added 'last_notification' to {user_folder}/{db_file}")
#
#                    conn.commit()
#                except Exception as e:
#                    print(f"Error updating {user_folder}/{db_file}: {e}")
#                finally:
#                    if conn:
#                        conn.close()
#
