import os
import telebot
from threading import Thread
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
BOT_TOKEN = "8598717015:AAGhbHPy-C9VTkcYb2XSyrJ3a_i83JNojf8 
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
        print(f"Ошибка проверки прав: {e}")
        return False


# --- ОБРАБОТЧИКИ КОМАНД ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        f"👋 Привет, *{message.from_user.first_name}*!\n\n"
        f"🎮 **Доступные игры в группе:**\n\n"
        f"🏃‍♂️ **ESCAPE** (Только для админов):\n"
        f"➡️ `/escape` — Запустить игру побега.\n\n"
        f"⚔️ **DUEL** (Для всех игроков):\n"
        f"➡️ `/duel` — Бросить вызов на поединок.\n\n"
        f"🛑 _Любой администратор может досрочно остановить текущую игру с помощью кнопки под ней!_"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")


# --- ИГРА ESCAPE (Запуск только админом) ---
@bot.message_handler(commands=['escape'])
def start_escape(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not is_admin(chat_id, user_id):
        bot.reply_to(message, "❌ Запускать игру **escape** могут только администраторы!")
        return

    markup = InlineKeyboardMarkup()
    btn_stop = InlineKeyboardButton("🛑 Завершить игру ESCAPE", callback_data="stop_escape")
    markup.add(btn_stop)

    escape_text = (
        f"🏃‍♂️ **Игра ESCAPE началась!** 🏃‍♂️\n"
        f"───────────────────\n"
        f"👑 Организатор: {message.from_user.first_name}\n"
        f"🚪 Приготовьтесь к побегу..."
    )
    bot.send_message(chat_id, escape_text, parse_mode="Markdown", reply_markup=markup)


# --- ИГРА DUEL (Запуск любым игроком) ---
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
        f"_(Администратор может досрочно остановить поединок кнопкой ниже)_"
    )
    bot.send_message(chat_id, duel_text, parse_mode="Markdown", reply_markup=markup)


# --- ОБРАБОТКА НАЖАТИЙ НА КНОПКИ ЗАВЕРШЕНИЯ ---
@bot.callback_query_handler(func=lambda call: call.data in ["stop_escape", "stop_duel"])
def handle_stop_game(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id  # Тот, кто нажал на кнопку
    
    # Строгая проверка: если нажал НЕ админ
    if not is_admin(chat_id, user_id):
        bot.answer_callback_query(
            callback_query_id=call.id, 
            text="⚠️ Убери свои руки! Кнопка только для админов.", 
            show_alert=True
        )
        return

    # Если нажал админ — определяем игру и завершаем
    game_name = "ESCAPE" if call.data == "stop_escape" else "DUEL"
    
    stop_text = (
        f"🛑 **Игра {game_name} досрочно завершена!**\n"
        f"───────────────────\n"
        f"👑 Решение принято администратором: *{call.from_user.first_name}*"
    )
    
    # Обновляем сообщение (удаляем кнопки, пишем финал)
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
    # 1. Запускаем Flask-сервер в фоновом потоке для 24/7
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # 2. Запускаем бесконечный опрос Telegram
    print("Бот успешно запущен 24/7 (Только игры)...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)                        
