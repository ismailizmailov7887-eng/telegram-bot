import os
import telebot
from flask import Flask, request
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Update
from dotenv import load_dotenv

load_dotenv()

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise ValueError("ОШИБКА: Переменная BOT_TOKEN не установлена!")

bot = telebot.TeleBot(BOT_TOKEN)

# --- ГЛОБАЛЬНОЕ ХРАНИЛИЩЕ ДЛЯ АКТИВНЫХ ДУЭЛЕЙ ---
active_duels = {}

# --- НАСТРОЙКА ВЕБ-СЕРВЕРА (Flask) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает через Webhook 24/7!"

# ИСПРАВЛЕНО: list_methods заменено на корректный methods
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    else:
        return 'Forbidden', 403


# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ПРОВЕРКИ АДМИНА ---
def is_admin(chat_id, user_id):
    try:
        if chat_id == user_id:  # В личке сам себе админ
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
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"🎮 Доступные игры в этой группе:\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏃‍♂️ [ ESCAPE ]\n"
        f"• Описание: Выживи или проиграй.\n"
        f"• Запуск: ➡️ /escape\n"
        f"⚠️ Доступно только для администрации.\n\n"
        f"⚔️ [ DUEL ]\n"
        f"• Описание: Сразись 1 на 1 в серии из 3 бросков.\n"
        f"• Вызов: ➡️ /duel\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎲 После старта дуэли бросайте кубик 🎲 или используйте команду /dice!"
    )
    bot.send_message(message.chat.id, welcome_text)


# --- ИГРА ESCAPE ---
@bot.message_handler(commands=['escape'])
def start_escape(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not is_admin(chat_id, user_id):
        error_text = (
            f"🚫 Ошибка доступа\n\n"
            f"🏃‍♂️ Игра ESCAPE может быть запущена только администрацией чата!\n"
            f"🔒 Пожалуйста, попросите администратора ввести команду /escape, чтобы начать сбор игроков."
        )
        bot.reply_to(message, error_text)
        return

    markup = InlineKeyboardMarkup()
    btn_stop = InlineKeyboardButton("🛑 Завершить игру ESCAPE", callback_data="stop_escape")
    markup.add(btn_stop)

    escape_text = (
        f"🏃‍♂️ **Игра ESCAPE началась!** 🏃‍♂️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 Организатор: {message.from_user.first_name}\n"
        f"🚪 Приготовьтесь к побегу...\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(chat_id, escape_text, parse_mode="Markdown", reply_markup=markup)


# --- ИГРА DUEL (СТАРТ) ---
@bot.message_handler(commands=['duel'])
def start_duel(message):
    chat_id = message.chat.id
    creator_id = message.from_user.id
    creator_name = message.from_user.first_name

    if chat_id in active_duels:
        bot.reply_to(message, "❌ В этом чате уже идет или готовится дуэль! Дождитесь её окончания.")
        return

    active_duels[chat_id] = {
        'status': 'waiting',
        'creator_id': creator_id,
        'creator_name': creator_name,
        'opponent_id': None,
        'opponent_name': None,
        'round': 1,
        'round_rolls': {},
        'wins': {creator_id: 0}
    }

    markup = InlineKeyboardMarkup()
    btn_accept = InlineKeyboardButton("⚔️ Принять вызов", callback_data=f"accept_duel_{creator_id}")
    btn_stop = InlineKeyboardButton("🛑 Отменить DUEL", callback_data="stop_duel")
    markup.add(btn_accept)
    markup.add(btn_stop)

    duel_text = (
        f"⚔️ **Вызов на ДУЭЛЬ брошен!** ⚔️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Организатор: {creator_name}\n"
        f"🎯 Кто примет вызов на битву из 3 бросков?\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
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

        if chat_id not in active_duels:
            bot.answer_callback_query(call.id, text="❌ Дуэль не найдена или была отменена!", show_alert=True)
            return
            
        if active_duels[chat_id]['status'] == 'fighting':
            bot.answer_callback_query(call.id, text="❌ Дуэль уже кем-то принята!", show_alert=True)
            return

        duel = active_duels[chat_id]
        duel['status'] = 'fighting'
        duel['opponent_id'] = user_id
        duel['opponent_name'] = user_name
        duel['wins'][user_id] = 0

        start_fight_text = (
            f"⚔️ **БИТВА НАЧАЛАСЬ!** ⚔️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 {duel['creator_name']}  vs  👤 {user_name}\n"
            f"🎯 Формат: Битва до 3-х бросков!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🚩 **РАУНД 1** 🚩\n"
            f"Оба игрока, бросайте кубик 🎲 или пишите `/dice`!"
        )
        
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=start_fight_text, parse_mode="Markdown", reply_markup=None)
        bot.answer_callback_query(call.id, text="Вы приняли вызов! Раунд 1 начался!")

    elif call.data in ["stop_escape", "stop_duel"]:
        if not is_admin(chat_id, user_id):
            bot.answer_callback_query(call.id, text="⚠️ Отменять игры могут только администраторы.", show_alert=True)
            return

        if call.data == "stop_duel":
            active_duels.pop(chat_id, None)

        game_name = "ESCAPE" if call.data == "stop_escape" else "DUEL"
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=f"🛑 **Игра {game_name} досрочно завершена админом {user_name}!**", reply_markup=None)
        bot.answer_callback_query(call.id, text="Игра успешно остановлена.")


# --- СЛЕЖКА ЗА КУБИКАМИ И МНОГОРАУНДОВАЯ ЛОГИКА ---
@bot.message_handler(content_types=['dice', 'text'], func=lambda msg: msg.chat.id in active_duels)
def monitor_duel_dice(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    duel = active_duels[chat_id]

    if duel['status'] != 'fighting' or message.from_user.is_bot:
        return

    if user_id != duel['creator_id'] and user_id != duel['opponent_id']:
        return

    is_command = message.text and message.text.lower().startswith('/dice')
    is_emoji_dice = message.dice is not None and message.dice.emoji == '🎲'

    if not (is_command or is_emoji_dice):
        return

    if user_id in duel['round_rolls']:
        bot.reply_to(message, f"❌ Вы уже бросили кубик в {duel['round']}-м раунде!")
        return

    if is_command:
        sent_dice = bot.send_dice(chat_id, emoji='🎲', reply_to_message_id=message.message_id)
        score = sent_dice.dice.value
    else:
        score = message.dice.value

    duel['round_rolls'][user_id] = score

    if len(duel['round_rolls']) == 2:
        c_id, o_id = duel['creator_id'], duel['opponent_id']
        c_name, o_name = duel['creator_name'], duel['opponent_name']
        c_score = duel['round_rolls'][c_id]
        o_score = duel['round_rolls'][o_id]

        if c_score > o_score:
            duel['wins'][c_id] += 1
            round_winner = f"Выиграл {c_name} 🎯"
        elif o_score > c_score:
            duel['wins'][o_id] += 1
            round_winner = f"Выиграл {o_name} 🎯"
        else:
            round_winner = "Ничья в раунде! 🤝"

        # Финал наступает, если сыграно 3 раунда или кто-то взял 2 победы
        if duel['wins'][c_id] == 2 or duel['wins'][o_id] == 2 or duel['round'] == 3:
            total_c_wins = duel['wins'][c_id]
            total_o_wins = duel['wins'][o_id]

            result_text = (
                f"🏆 РЕЗУЛЬТАТЫ ДУЭЛИ 🏆\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚔️ Битва титанов (3 раунда):\n"
                f"👤 {c_name}  vs  👤 {o_name}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🎲 Последний раунд бросков:\n"
                f"┌─ {c_name}: {c_score} 🎲\n"
                f"└─ {o_name}: {o_score} 🎲\n\n"
                f"📊 Общий счет по раундам:\n"
                f"⭐ {c_name}: {total_c_wins}\n"
                f"⭐ {o_name}: {total_o_wins}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
            )

            if total_c_wins > total_o_wins:
                result_text += f"🎉 Победитель: {c_name} 👑\n🌟 Король арены! 🌟"
            elif total_o_wins > total_c_wins:
                result_text += f"🎉 Победитель: {o_name} 👑\n🌟 Король арены! 🌟"
            else:
                result_text += "🤝 Абсолютная ничья по итогам всех раундов! Вы оба достойные бойцы!"

            bot.send_message(chat_id, result_text)
            active_duels.pop(chat_id, None)
        else:
            status_text = (
                f"📊 **Итоги {duel['round']}-го раунда:**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 {c_name}: {c_score} 🎲\n"
                f"👤 {o_name}: {o_score} 🎲\n\n"
                f"📢 {round_winner}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🚩 **РАУНД {duel['round'] + 1}** 🚩\n"
                f"Жду броски кубиков от бойцов!"
            )
            bot.send_message(chat_id, status_text)
            
            duel['round'] += 1
            duel['round_rolls'] = {}


# --- ЗАПУСК ВЕБХУКА ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    
    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL.rstrip('/')}/{BOT_TOKEN}"
        print(f"Установка Webhook на адрес: {webhook_url}")
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    else:
        print("ВНИМАНИЕ: RENDER_EXTERNAL_URL не найден. Проверьте настройки окружения Render.")

    app.run(host="0.0.0.0", port=port)
