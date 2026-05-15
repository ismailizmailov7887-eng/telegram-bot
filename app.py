import os
import telebot
from threading import Thread
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

load_dotenv()

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("ОШИБКА: Переменная окружения BOT_TOKEN не установлена!")

bot = telebot.TeleBot(BOT_TOKEN)

# --- ГЛОБАЛЬНОЕ ХРАНИЛИЩЕ ДЛЯ АКТИВНЫХ ДУЭЛЕЙ ---
# Структура: { chat_id: { 'creator_id': int, 'opponent_id': int, 'creator_name': str, 'opponent_name': str, 'scores': { user_id: value } } }
active_duels = {}

# --- НАСТРОЙКА ВЕБ-СЕРВЕРА ---
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
        f"🏃‍♂️ **ESCAPE**:\n"
        f"➡️ `/escape` — Запустить игру (🛑 *Только админам*)\n\n"
        f"⚔️ **DUEL**:\n"
        f"➡️ `/duel` — Бросить вызов на поединок.\n\n"
        f"🎲 *После старта дуэли кидайте кубик 🎲 или пишите `/dice`*"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")


# --- ИГРА ESCAPE ---
@bot.message_handler(commands=['escape'])
def start_escape(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not is_admin(chat_id, user_id):
        bot.reply_to(message, "❌ Ошибка доступа: Только администраторы могут запускать ESCAPE!")
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


# --- ИГРА DUEL (СТАРТ) ---
@bot.message_handler(commands=['duel'])
def start_duel(message):
    chat_id = message.chat.id
    creator_id = message.from_user.id
    creator_name = message.from_user.first_name

    if chat_id in active_duels:
        bot.reply_to(message, "❌ В этом чате уже идет дуэль! Дождитесь её окончания.")
        return

    markup = InlineKeyboardMarkup()
    btn_accept = InlineKeyboardButton("⚔️ Принять вызов", callback_data=f"accept_duel_{creator_id}")
    btn_stop = InlineKeyboardButton("🛑 Отменить DUEL", callback_data="stop_duel")
    markup.add(btn_accept)
    markup.add(btn_stop)

    duel_text = (
        f"⚔️ **Вызов на ДУЭЛЬ брошен!** ⚔️\n"
        f"───────────────────\n"
        f"👤 Организатор: *{creator_name}*\n"
        f"🎯 Кто примет вызов?"
    )
    bot.send_message(chat_id, duel_text, parse_mode="Markdown", reply_markup=markup)


# --- ОБРАБОТКА НАЖАТИЙ НА КНОПКИ ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    user_name = call.from_user.first_name

    if call.data.startswith("accept_duel_"):
        creator_id = int(call.data.split("_")[2])
        
        if user_id == creator_id:
            bot.answer_callback_query(call.id, text="❌ Вы не можете принять собственный вызов!", show_alert=True)
            return

        if chat_id in active_duels:
            bot.answer_callback_query(call.id, text="❌ Дуэль уже кем-то принята или идет!", show_alert=True)
            return

        # Получаем имя создателя из текста сообщения (или оставляем бакап)
        creator_name = "Организатор"
        if call.message.entities:
            for entity in call.message.entities:
                if entity.type == "bold" and "Организатор" not in call.message.text[entity.offset:entity.offset+entity.length]:
                    creator_name = call.message.text[entity.offset:entity.offset+entity.length]

        # Регистрируем активную дуэль
        active_duels[chat_id] = {
            'creator_id': creator_id,
            'creator_name': creator_name,
            'opponent_id': user_id,
            'opponent_name': user_name,
            'scores': {}
        }

        start_fight_text = (
            f"⚔️ **ДУЭЛЬ НАЧАЛАСЬ!** ⚔️\n"
            f"───────────────────\n"
            f"💥 Игроки: *{creator_name}* VS *{user_name}*\n\n"
            f"🎲 **ЧТО ДЕЛАТЬ ДАЛЬШЕ:**\n"
            f"Оба игрока должны отправить в чат кубик (эмодзи 🎲) или написать команду `/dice`.\n"
            f"Бот подсчитает очки и выберет победителя!"
        )
        
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=start_fight_text, parse_mode="Markdown", reply_markup=None)
        bot.answer_callback_query(call.id, text="Вы приняли вызов! Бросайте кубики!")

    elif call.data in ["stop_escape", "stop_duel"]:
        if not is_admin(chat_id, user_id):
            bot.answer_callback_query(call.id, text="⚠️ Отменять игры могут только администраторы.", show_alert=True)
            return

        if call.data == "stop_duel" and chat_id in active_duels:
            active_duels.pop(chat_id, None)

        game_name = "ESCAPE" if call.data == "stop_escape" else "DUEL"
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=f"🛑 **Игра {game_name} досрочно завершена админом {user_name}!**", reply_markup=None)
        bot.answer_callback_query(call.id, text="Игра успешно остановлена.")


# --- СЛЕЖКА ЗА КУБИКАМИ И СБОР РЕЗУЛЬТАТОВ ---
# Метод ловит текстовую команду /dice ИЛИ отправку обычного эмодзи кубика (content_types=['dice', 'text'])
@bot.message_handler(content_types=['dice', 'text'], func=lambda msg: msg.chat.id in active_duels)
def monitor_duel_dice(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    duel = active_duels[chat_id]

    # Проверяем, участвует ли этот человек в текущей дуэли
    if user_id != duel['creator_id'] and user_id != duel['opponent_id']:
        return

    # Проверяем, является ли сообщение броском кубика
    is_command = message.text and message.text.lower().startswith('/dice')
    is_emoji_dice = message.dice is not None and message.dice.emoji == '🎲'

    if not (is_command or is_emoji_dice):
        return

    # Проверяем, не кидал ли этот игрок кубик ранее
    if user_id in duel['scores']:
        bot.reply_to(message, "❌ Вы уже сделали свой бросок в этой дуэли!")
        return

    # Если отправлена команда /dice, бот сам бросает кубик от имени системы для игрока
    if is_command:
        sent_dice = bot.send_dice(chat_id, emoji='🎲', reply_to_message_id=message.message_id)
        score = sent_dice.dice.value
    else:
        # Если игрок сам кинул эмодзи-кубик, берем его значение
        score = message.dice.value

    # Записываем результат игрока
    duel['scores'][user_id] = score

    # Проверяем, бросили ли оба участника
    if len(duel['scores']) == 2:
        c_id, o_id = duel['creator_id'], duel['opponent_id']
        c_score = duel['scores'][c_id]
        o_score = duel['scores'][o_id]
        
        c_name = duel['creator_name']
        o_name = duel['opponent_name']

        # Формируем итог
        result_text = (
            f"🏆 **РЕЗУЛЬТАТЫ ДУЭЛИ** 🏆\n"
            f"───────────────────\n"
            f"👤 {c_name} выбросил: **{c_score}** 🎲\n"
            f"👤 {o_name} выбросил: **{o_score}** 🎲\n"
            f"───────────────────\n"
        )

        if c_score > o_score:
            result_text += f"🎉 Победитель: *{c_name}*! Король арены! 👑"
        elif o_score > c_score:
            result_text += f"🎉 Победитель: *{o_name}*! Король арены! 👑"
        else:
            result_text += "🤝 **Ничья!** Оба бойца равны по силе. Начните новую дуэль!"

        bot.send_message(chat_id, result_text, parse_mode="Markdown")
        
        # Удаляем дуэль из активных, освобождая место для следующей
        active_duels.pop(chat_id, None)


# --- ЗАПУСК ПРОЕКТА ---
if __name__ == '__main__':
    # Фоновый Flask
    flask_thread = Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("Сброс старых подключений (Conflict 409)...")
    bot.delete_webhook(drop_pending_updates=True)

    print("Бот успешно запущен и следит за дуэлями...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10)
