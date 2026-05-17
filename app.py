import os
import random
import threading
import telebot
import time
from flask import Flask, request
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Update
from dotenv import load_dotenv

load_dotenv()

# --- Конфигурация ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Хранилище сессий
active_escapes = {}
active_duels = {}

# --- Проверка админа ---
def is_user_admin(chat_id, user_id):
    if chat_id == user_id: return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except: return False

# =====================================================================
#                          ГЛАВНЫЙ ОБРАБОТЧИК КНОПОК
# =====================================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    chat_id = call.message.chat.id
    uid = call.from_user.id
    
    # --- ESCAPE: Вступить ---
    if call.data == "esc_join":
        if chat_id in active_escapes:
            game = active_escapes[chat_id]
            if uid not in game['players']:
                game['players'][uid] = call.from_user.first_name
                players_list = "\n".join([f"👤 {name}" for name in game['players'].values()])
                text = f"🎮 *РЕГИСТРАЦИЯ НА ESCAPE*\n\n👥 *Участники:* {len(game['players'])}\n{players_list}"
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("➕ ВСТУПИТЬ", callback_data="esc_join"))
                markup.add(InlineKeyboardButton("🚀 НАЧАТЬ", callback_data="esc_start"))
                try:
                    bot.edit_message_text(text, chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
                except: pass
            else:
                bot.answer_callback_query(call.id, "Вы уже в игре!")

    # --- ESCAPE: Начать (Только админ) ---
    elif call.data == "esc_start":
        if chat_id in active_escapes:
            if is_user_admin(chat_id, uid):
                if len(active_escapes[chat_id]['players']) >= 2:
                    bot.delete_message(chat_id, call.message.message_id)
                    escape_round_start(chat_id)
                else:
                    bot.answer_callback_query(call.id, "Нужно минимум 2 игрока!", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "Только админ может запустить игру!", show_alert=True)

    # --- ESCAPE: Выбор двери ---
    elif call.data.startswith("dr_"):
        if chat_id in active_escapes:
            game = active_escapes[chat_id]
            if uid in game['players']:
                door_num = int(call.data.split("_")[1])
                game['choices'][uid] = door_num
                bot.answer_callback_query(call.id, f"Дверь {door_num} выбрана!")
            else:
                bot.answer_callback_query(call.id, "Вы не участвуете!", show_alert=True)

    # --- DUEL: Принять вызов ---
    elif call.data == "accept_duel":
        if chat_id in active_duels:
            duel = active_duels[chat_id]
            if uid != duel['creator_id']:
                duel.update({
                    'status': 'fighting',
                    'opponent_id': uid,
                    'opponent_name': call.from_user.first_name,
                })
                duel['total_scores'][uid] = 0
                bot.edit_message_text(f"⚔️ *ДУЭЛЬ НАЧАЛАСЬ!*\n\n👤 {duel['creator_name']} VS 👤 {duel['opponent_name']}\n\nКидайте кубики 🎲!", chat_id, call.message.message_id, parse_mode="Markdown")

# =====================================================================
#                          КОМАНДЫ УПРАВЛЕНИЯ
# =====================================================================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    text = (
        "👋 *Меню управления*\n\n"
        "🏃‍♂️ /escape — Начать выживание (Админ)\n"
        "⚔️ /duel — Вызвать на дуэль\n"
        "🛑 /stop — Остановить все игры (Админ)"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def cmd_stop(message):
    if is_user_admin(message.chat.id, message.from_user.id):
        active_escapes.pop(message.chat.id, None)
        active_duels.pop(message.chat.id, None)
        bot.send_message(message.chat.id, "🛑 *Все процессы принудительно остановлены.*", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ У тебя нет прав на остановку.")

# =====================================================================
#                          ЛОГИКА ESCAPE
# =====================================================================
@bot.message_handler(commands=['escape'])
def cmd_escape(message):
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Только админ может начать набор.")
        return
    
    active_escapes[message.chat.id] = {
        'players': {}, 'room': 1, 'choices': {}, 'dead_door': None
    }
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ ВСТУПИТЬ", callback_data="esc_join"))
    markup.add(InlineKeyboardButton("🚀 НАЧАТЬ", callback_data="esc_start"))
    
    bot.send_message(message.chat.id, "🎮 *РЕГИСТРАЦИЯ НА ESCAPE*\n\n📍 Жду участников...", parse_mode="Markdown", reply_markup=markup)

def escape_round_start(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    
    if len(game['players']) <= 1:
        winner = list(game['players'].values())[0] if game['players'] else "Никто"
        bot.send_message(chat_id, f"🏆 *ИГРА ЗАВЕРШЕНА*\n👑 Победитель: {winner}", parse_mode="Markdown")
        active_escapes.pop(chat_id, None)
        return

    game['choices'] = {}
    game['dead_door'] = random.randint(1, 3)
    
    players_list = "\n".join([f"👤 {name}" for name in game['players'].values()])
    markup = InlineKeyboardMarkup().row(
        InlineKeyboardButton("🚪 Дверь 1", callback_data="dr_1"),
        InlineKeyboardButton("🚪 Дверь 2", callback_data="dr_2"),
        InlineKeyboardButton("🚪 Дверь 3", callback_data="dr_3")
    )
    
    bot.send_message(chat_id, f"🔴 *РАУНД {game['room']}*\n\n{players_list}\n\n📍 Выбирайте! (30 сек)", parse_mode="Markdown", reply_markup=markup)
    threading.Timer(30.0, escape_round_results, args=(chat_id,)).start()

def escape_round_results(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    
    for p_id in list(game['players'].keys()):
        if p_id not in game['choices']:
            game['choices'][p_id] = random.randint(1, 3)

    dead_names = []
    survivors = []
    
    for p_id in list(game['players'].keys()):
        name = game['players'][p_id]
        if game['choices'][p_id] == game['dead_door']:
            dead_names.append(name)
            game['players'].pop(p_id)
        else:
            survivors.append(name)

    res_text = f"📊 *ИТОГИ РАУНДА {game['room']}*\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    res_text += f"💀 *ПОГИБЛИ:* {', '.join(dead_names) if dead_names else 'Никто'}\n"
    res_text += f"💎 *ВЫЖИЛИ:* {', '.join(survivors) if survivors else 'Никто'}\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    
    bot.send_message(chat_id, res_text, parse_mode="Markdown")
    
    game['room'] += 1
    time.sleep(3)
    escape_round_start(chat_id)

# =====================================================================
#                          ЛОГИКА DUEL
# =====================================================================
@bot.message_handler(commands=['duel'])
def cmd_duel(message):
    if message.chat.id in active_duels: return
    active_duels[message.chat.id] = {
        'status': 'waiting', 'creator_id': message.from_user.id, 'creator_name': message.from_user.first_name,
        'opponent_id': None, 'opponent_name': None, 'round': 1, 'round_rolls': {}, 'total_scores': {message.from_user.id: 0}
    }
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("⚔️ ПРИНЯТЬ", callback_data="accept_duel"))
    bot.send_message(message.chat.id, f"⚔️ *{message.from_user.first_name}* вызывает на дуэль!", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(content_types=['dice'])
def handle_dice(message):
    chat_id = message.chat.id
    if chat_id not in active_duels or message.dice.emoji != '🎲': return
    duel = active_duels[chat_id]
    if duel.get('status') != 'fighting': return
    if message.from_user.id not in [duel['creator_id'], duel['opponent_id']]: return
    if message.from_user.id in duel['round_rolls']: return
    
    duel['round_rolls'][message.from_user.id] = message.dice.value
    if len(duel['round_rolls']) == 2:
        threading.Thread(target=duel_round_finish, args=(chat_id,)).start()

def duel_round_finish(chat_id):
    time.sleep(5)
    if chat_id not in active_duels: return
    duel = active_duels[chat_id]
    
    c_id, o_id = duel['creator_id'], duel['opponent_id']
    duel['total_scores'][c_id] += duel['round_rolls'][c_id]
    duel['total_scores'][o_id] += duel['round_rolls'][o_id]
    
    if duel['round'] >= 3:
        s1, s2 = duel['total_scores'][c_id], duel['total_scores'][o_id]
        winner = duel['creator_name'] if s1 > s2 else duel['opponent_name']
        if s1 == s2: winner = "Ничья"
        bot.send_message(chat_id, f"🏆 *ИТОГ ДУЭЛИ:* {s1} — {s2}\n👑 Победитель: {winner}", parse_mode="Markdown")
        active_duels.pop(chat_id, None)
    else:
        bot.send_message(chat_id, f"📊 *РАУНД {duel['round']} ОКОНЧЕН*\nСчет: {duel['total_scores'][c_id]} — {duel['total_scores'][o_id]}\n🔜 Жду кубики для раунда {duel['round']+1}!", parse_mode="Markdown")
        duel['round'] += 1
        duel['round_rolls'] = {}

# =====================================================================
#                          ВЕБХУК
# =====================================================================
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def getMessage():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = Update.de_json(json_string)
        bot.process_new_updates([update])
        return "!", 200
    return "Forbidden", 403

@app.route("/")
def index():
    bot.remove_webhook()
    bot.set_webhook(url=f"{RENDER_EXTERNAL_URL}/{BOT_TOKEN}")
    return "Bot Online", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
