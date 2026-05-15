import os
import telebot
from threading import Thread
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
BOT_TOKEN = "8598717015:AAGhbHPy-C9VTkcYb2XSyrJ3a_i83JNojf8" 
bot = telebot.TeleBot(BOT_TOKEN)

# --- НАСТРОЙКА ВЕБ-СЕРВЕРА (для UptimeRobot / Cron-Job) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ПРОВЕРКИ АДМИНА ---
def is_admin(chat_id, user_id):
    try:
        # В личной переписке с ботом пользователь всегда считается админом
        if chat_id == user_id:
            return True
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception as e:
        print(f"Ошибка проверки прав для пользователя {user_id} в чате {chat_id}: {e}")
        return False


# --- ОБРАБОТЧИКИ КОМАНД ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        f"👋 Привет, *{message.from_user.first_name}*!\n\n"
        f"🎮 **Доступные игры в группе:**\n\n"
        f"🏃‍♂️ **ESCAPE**:\n"
        f"➡️ `/escape` — Запустить игру (🛑 **Доступно только админам!**)\n\n"
        f"⚔️ **DUEL**:\n"
        f"➡️ `/duel` — Бросить вызов на поединок (Запустить может любой).\n\n"
        f"🛑 _Любые кнопки остановки игр работают **исключительно** для администраторов чата!_"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")


# --- ИГРА ESCAPE (СТРОГО ДЛЯ АДМИНОВ) ---
@bot.message_handler(commands=['escape'])
def start_escape(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    # Проверка прав: если НЕ админ, то просто сбрасываем команду
    if not is_admin(chat_id, user_id):
        bot.reply_to(message, "❌ Ошибка доступа: Запускать игру **ESCAPE** могут только администраторы группы!")
        return

    markup = InlineKeyboardMarkup()
    btn_stop = InlineKeyboardButton("🛑 Завершить игру ESCAPE", callback_data="stop_escape")
    markup.add(btn_stop)

    escape_text = (
        f"🏃‍♂️ **Игра ESCAPE началась!** 🏃‍♂️\n"
        f"───────────────────\n"
        f"👑 Организатор (Админ): {message.from_user.first_name}\n"
        f"🚪 Приготовьтесь к побегу...\n\n"
        f"🛑 _Остановить игру может только администратор._"
    )
    bot.send_message(chat_id, escape_text, parse_mode="Markdown", reply_markup=markup)


# --- ИГРА DUEL (ЗАПУСК ДЛЯ ВСЕХ) ---
@bot.message_handler(commands=['duel'])
def start_duel(message):
    chat_id = message.chat.id

    markup = InlineKeyboardMarkup()
    btn_stop = InlineKeyboardButton("🛑 Завершить DUEL", callback_data="stop_duel")
    markup.add(btn_stop)

    duel_text = (
        f"⚔️ **Вызов на ДУЭЛЬ брошен!** ⚔️\n"
        f"───────────────────\n"
        f"🎯 Кто примет вызов?\n\n"
        f"🛑 _Внимание: досрочно завершить поединок кнопкой ниже может только администратор!_"
    )
    bot.send_message(chat_id, duel_text, parse_mode="Markdown", reply_markup=markup)


# --- ОБРАБОТКА НАЖАТИЙ НА КНОПКИ ОСТАНОВКИ (СТРОГО ДЛЯ АДМИНОВ) ---
@bot.callback_query_handler(func=lambda call: call.data in ["stop_escape", "stop_duel"])
def handle_stop_game(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id  # Тот, кто нажал на кнопку
    
    # Жесткая проверка: если на кнопку нажал НЕ админ, блокируем действие
    if not is_admin(chat_id, user_id):
        print(f"Пользователь {call.from_user.first_name} ({user_id}) пытался остановить игру без прав.")
        bot.answer_callback_query(
            callback_query_id=call.id, 
            text="⚠️ Доступ запрещен! Останавливать игры могут только администраторы.", 
            show_alert=True  # Показывает модальное окно на весь экран приложения
        )
        return

    # Если проверку прошли (значит нажал админ) — определяем игру и завершаем ее
    game_name = "ESCAPE" if call.data == "stop_escape" else "DUEL"
    
    stop_text = (
        f"🛑 **Игра {game_name} досрочно завершена!**\n"
        f"───────────────────\n"
        f"👑 Действие выполнено администратором: *{call.from_user.first_name}*"
    )
    
    # Редактируем сообщение (удаляем клавиатуру с кнопкой и меняем текст на финальный)
    bot.edit_message_text(
        chat_id=chat_id,
        message_id=call.message.message_id,
        text=stop_text,
        parse_mode="Markdown",
        reply_markup=None
    )
    bot.answer_callback_query(call.id, text="Игра успешно остановлена.")


# --- ЗАПУСК ПРОЕКТА ---
if __name__ == '__main__':
    # 1. Запускаем Flask-сервер в фоновом потоке для поддержания активности (24/7)
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # 2. Запускаем бесконечный опрос Telegram
    print("Бот успешно запущен 24/7 и готов обрабатывать игры...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
