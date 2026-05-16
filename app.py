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
#                          ЛОГИКА ДУЭЛИ (DUEL)
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
    markup.add(InlineKeyboardButton("⚔️ Принять вызов", callback_data=f"accept_duel"),
               InlineKeyboardButton("🛑 Отмена", callback_data="stop_duel"))

    # Добавлены правила в шапку
    text = (
        f"⚔️ **ВЫЗОВ НА ДУЭЛЬ** ⚔️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **{message.from_user.first_name}** вызывает на бой!\n"
        f"🎯 **3 раунда на кубиках.**\n"
        f"📜 **ПРАВИЛА:**\n"
        f"1. Кидайте кубик только в свою очередь.\n"
        f"2. Победит тот, кто наберет больше очков.\n"
        f"3. Повторные броски запрещены!\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(content_types=['dice'])
def handle_dice(message):
    chat_id = message.chat.id
    if chat_id not in active_duels or message.dice.emoji != '🎲': return
    
    duel = active_duels[chat_id]
    user_id = message.from_user.id

    if duel['status'] != 'fighting': return
    
    # Если кидает левый человек (не участник)
    if user_id not in [duel['creator_id'], duel['opponent_id']]: return

    # ПРОВЕРКА НА ПОВТОРНЫЙ БРОСОК
    if user_id in duel['round_rolls']:
        bot.reply_to(message, "второй раз нельзя кидать леее")
        return

    duel['round_rolls'][user_id] = message.dice.value

    if len(duel['round_rolls']) == 2:
        threading.Thread(target=delayed_duel_result, args=(chat_id,)).start()

def delayed_duel_result(chat_id):
    time.sleep(5) # Задержка 5 секунд
    if chat_id not in active_duels: return
    duel = active_duels[chat_id]
    
    c_id, o_id = duel['creator_id'], duel['opponent_id']
    duel['total_scores'][c_id] += duel['round_rolls'][c_id]
    duel['total_scores'][o_id] = duel['total_scores'].get(o_id, 0) + duel['round_rolls'][o_id]

    if duel['round'] == 3:
        res = (
            f"🏆 **ФИНАЛЬНЫЙ СЧЕТ** 🏆\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 {duel['creator_name']}: **{duel['total_scores'][c_id]}**\n"
            f"👤 {duel['opponent_name']}: **{duel['total_scores'][o_id]}**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        if duel['total_scores'][c_id] > duel['total_scores'][o_id]:
            res += f"👑 ПОБЕДИТЕЛЬ: **{duel['creator_name']}**"
        elif duel['total_scores'][o_id] > duel['total_scores'][c_id]:
            res += f"👑 ПОБЕДИТЕЛЬ: **{duel['opponent_name']}**"
        else:
            res += "🤝 **НИЧЬЯ!**"
        
        bot.send_message(chat_id, res, parse_mode="Markdown")
        active_duels.pop(chat_id, None)
    else:
        status = (
            f"📊 **РАУНД {duel['round']} ЗАВЕРШЕН**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 {duel['creator_name']} выбил: **{duel['round_rolls'][c_id]}**\n"
            f"👤 {duel['opponent_name']} выбил: **{duel['round_rolls'][o_id]}**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔔 Общий счет: **{duel['total_scores'][c_id]}** — **{duel['total_scores'][o_id]}**\n"
            f"🚀 Раунд {duel['round'] + 1}... ПОГНАЛИ!"
        )
        bot.send_message(chat_id, status, parse_mode="Markdown")
        duel['round'] += 1
        duel['round_rolls'] = {}

# =====================================================================
#                          CALLBACKS
# =====================================================================
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    chat_id = call.message.chat.id
    if call.data == "accept_duel":
        if chat_id in active_duels and active_duels[chat_id]['status'] == 'waiting':
            if call.from_user.id == active_duels[chat_id]['creator_id']:
                bot.answer_callback_query(call.id, "Вы не можете играть с самим собой!")
                return
            active_duels[chat_id]['status'] = 'fighting'
            active_duels[chat_id]['opponent_id'] = call.from_user.id
            active_duels[chat_id]['opponent_name'] = call.from_user.first_name
            bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, 
                                  text="⚔️ **БИТВА НАЧАЛАСЬ!**\n\nБросайте кубики 🎲 (Всего 3 раунда)", parse_mode="Markdown")
    
    elif call.data == "stop_duel":
        active_duels.pop(chat_id, None)
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="❌ Дуэль отменена.")

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
