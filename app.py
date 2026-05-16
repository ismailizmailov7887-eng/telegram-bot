import os
import random
import time
import threading
import telebot
from flask import Flask, request
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Update
from dotenv import load_dotenv

load_dotenv()

# --- Конфигурация ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

active_escapes = {}
active_duels = {}

# --- Вспомогательные функции ---
def is_user_admin(chat_id, user_id):
    if chat_id == user_id: return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except: return False

# =====================================================================
#                          ГЛАВНОЕ МЕНЮ
# =====================================================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        f"👋 **Привет, {message.from_user.first_name}!**\n\n"
        f"🌟 **ДОСТУПНЫЕ ИГРЫ:**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏃‍♂️ **[ ESCAPE ]** — Выживание в комнатах.\n"
        f"🔷 `ЗАПУСК:` /escape (Только Админ)\n\n"
        f"⚔️ **[ DUEL ]** — Битва на кубиках (3 раунда).\n"
        f"🔶 `ЗАПУСК:` /duel (Для всех)\n\n"
        f"⚙️ **УПРАВЛЕНИЕ:**\n"
        f"🚫 `СБРОС:` /stop (Остановка всех игр)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def stop_all(message):
    chat_id = message.chat.id
    if not is_user_admin(chat_id, message.from_user.id):
        bot.reply_to(message, "❌ Отмена доступна только администраторам.")
        return
    active_escapes.pop(chat_id, None)
    active_duels.pop(chat_id, None)
    bot.send_message(chat_id, "🛑 **ВСЕ ИГРЫ ОСТАНОВЛЕНЫ.**", parse_mode="Markdown")

# =====================================================================
#                          ЛОГИКА ESCAPE
# =====================================================================
@bot.message_handler(commands=['escape'])
def start_escape(message):
    chat_id = message.chat.id
    if not is_user_admin(chat_id, message.from_user.id):
        bot.reply_to(message, "❌ Только админ может запустить Escape!")
        return
    if chat_id in active_escapes:
        bot.reply_to(message, "❌ Игра уже запущена!")
        return

    active_escapes[chat_id] = {'room': 0, 'survivors': [], 'status': 'waiting'}
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🏃 Вступить", callback_data="join_esc"),
               InlineKeyboardButton("🚀 СТАРТ", callback_data="run_esc"))
    
    bot.send_message(chat_id, "🏃‍♂️ **РЕГИСТРАЦИЯ НА ESCAPE**\nНажми «Вступить», а затем Админ нажмет «Старт».", 
                     parse_mode="Markdown", reply_markup=markup)

def escape_step(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    game['room'] += 1
    
    # Логика: выживают не все (шанс 70%)
    survivors = game['survivors']
    if len(survivors) > 1:
        still_alive = [u for u in survivors if random.random() > 0.35]
        game['survivors'] = still_alive
        
        dead_count = len(survivors) - len(still_alive)
        text = f"🚪 **КОМНАТА №{game['room']}**\n━━━━━━━━━━━━\n💀 Ловушка устранила игроков: {dead_count}\n✅ Осталось: {len(still_alive)}"
        bot.send_message(chat_id, text, parse_mode="Markdown")
        
        if len(still_alive) <= 1:
            winner = f"🏆 ИГРА ОКОНЧЕНА!\nПобедитель: {f'ID {still_alive[0]}' if still_alive else 'Никто'}"
            bot.send_message(chat_id, winner)
            active_escapes.pop(chat_id, None)
        else:
            threading.Timer(4.0, escape_step, args=(chat_id,)).start()
    else:
        active_escapes.pop(chat_id, None)

# =====================================================================
#                          ЛОГИКА ДУЭЛИ
# =====================================================================
@bot.message_handler(commands=['duel'])
def start_duel(message):
    chat_id = message.chat.id
    if chat_id in active_duels:
        bot.reply_to(message, "❌ Дуэль уже идет!")
        return

    active_duels[chat_id] = {
        'status': 'waiting',
        'creator_id': message.from_user.id,
        'creator_name': message.from_user.first_name,
        'opponent_id': None,
        'opponent_name': None,
        'round': 1,
        'round_rolls': {},
        'total_scores': {message.from_user.id: 0}
    }

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⚔️ Принять", callback_data="accept_duel"),
               InlineKeyboardButton("🛑 Отмена", callback_data="stop_duel"))

    text = f"⚔️ **ВЫЗОВ ОТ {message.from_user.first_name}**\n3 раунда на кубиках!"
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(content_types=['dice'])
def handle_dice(message):
    chat_id = message.chat.id
    if chat_id not in active_duels or message.dice.emoji != '🎲': return
    
    duel = active_duels[chat_id]
    user_id = message.from_user.id
    if duel['status'] != 'fighting' or user_id not in [duel['creator_id'], duel['opponent_id']]: return
    if user_id in duel['round_rolls']: return

    duel['round_rolls'][user_id] = message.dice.value
    if len(duel['round_rolls']) == 2:
        threading.Thread(target=delayed_duel_result, args=(chat_id,)).start()

def delayed_duel_result(chat_id):
    time.sleep(4)
    if chat_id not in active_duels: return
    duel = active_duels[chat_id]
    c_id, o_id = duel['creator_id'], duel['opponent_id']
    
    duel['total_scores'][c_id] += duel['round_rolls'][c_id]
    duel['total_scores'][o_id] = duel['total_scores'].get(o_id, 0) + duel['round_rolls'][o_id]

    if duel['round'] == 3:
        res = f"🏆 **ИТОГ**\n{duel['creator_name']}: {duel['total_scores'][c_id]}\n{duel['opponent_name']}: {duel['total_scores'][o_id]}"
        bot.send_message(chat_id, res)
        active_duels.pop(chat_id, None)
    else:
        bot.send_message(chat_id, f"✅ Раунд {duel['round']} завершен! Ждем кубики для раунда {duel['round']+1}")
        duel['round'] += 1
        duel['round_rolls'] = {}

# =====================================================================
#                          CALLBACKS
# =====================================================================
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    chat_id = call.message.chat.id
    uid = call.from_user.id

    # Обработка Escape
    if call.data == "join_esc":
        if chat_id in active_escapes and uid not in active_escapes[chat_id]['survivors']:
            active_escapes[chat_id]['survivors'].append(uid)
            bot.answer_callback_query(call.id, "✅ Ты в игре!")
            
    elif call.data == "run_esc":
        if not is_user_admin(chat_id, uid): return
        if len(active_escapes[chat_id]['survivors']) < 2:
            bot.answer_callback_query(call.id, "Минимум 2 игрока!", show_alert=True)
            return
        active_escapes[chat_id]['status'] = 'running'
        bot.edit_message_text("🚪 Двери закрылись! Выживание началось...", chat_id, call.message.message_id)
        escape_step(chat_id)

    # Обработка Дуэли
    elif call.data == "accept_duel":
        if chat_id in active_duels and active_duels[chat_id]['status'] == 'waiting':
            if uid == active_duels[chat_id]['creator_id']: return
            active_duels[chat_id].update({'status': 'fighting', 'opponent_id': uid, 'opponent_name': call.from_user.first_name})
            bot.edit_message_text("⚔️ **БИТВА!** Кидайте кубики 🎲", chat_id, call.message.message_id, parse_mode="Markdown")
            
    elif call.data == "stop_duel":
        active_duels.pop(chat_id, None)
        bot.edit_message_text("❌ Отменено.", chat_id, call.message.message_id)

# =====================================================================
#                          WEBHOOK / RUN
# =====================================================================
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def getMessage():
    bot.process_new_updates([Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route("/")
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f"{RENDER_EXTERNAL_URL}/{BOT_TOKEN}")
    return "Status: Online", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
