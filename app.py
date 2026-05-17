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
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"🏆 *ДОСТУПНЫЕ ИГРЫ*\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"🏃‍♂️ *ESCAPE* — Выживание в комнатах\n"
        f"Запуск: /escape (Только Админ)\n\n"
        f"⚔️ *DUEL* — Битва на кубиках\n"
        f"Запуск: /duel (Для всех)\n\n"
        f"⚙️ *УПРАВЛЕНИЕ*\n"
        f"🛑 СБРОС: /stop (Остановка всех игр)\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
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
    bot.send_message(chat_id, "🛑 *ВСЕ ИГРЫ ОСТАНОВЛЕНЫ*", parse_mode="Markdown")

# =====================================================================
#                          ЛОГИКА ESCAPE
# =====================================================================
@bot.message_handler(commands=['escape'])
def start_escape(message):
    chat_id = message.chat.id
    if not is_user_admin(chat_id, message.from_user.id):
        bot.reply_to(message, "❌ Только админ может запустить игру.")
        return
    
    active_escapes[chat_id] = {
        'status': 'registration',
        'players': {}, 
        'room': 1,
        'choices': {},
        'dead_door': None
    }
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ ВСТУПИТЬ", callback_data="esc_join"))
    markup.add(InlineKeyboardButton("🚀 НАЧАТЬ", callback_data="esc_start"))
    
    text = "🎮 *ИГРА ESCAPE НАЧИНАЕТСЯ*\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n👥 *УЧАСТНИКИ:* Пусто\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

def update_registration_text(chat_id, message_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    players_list = "\n".join([f"👤 {name}" for name in game['players'].values()])
    text = f"🎮 *ИГРА ESCAPE НАЧИНАЕТСЯ*\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n👥 *УЧАСТНИКИ:*\n{players_list if players_list else '📍 Пусто'}"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ ВСТУПИТЬ", callback_data="esc_join"))
    markup.add(InlineKeyboardButton("🚀 НАЧАТЬ", callback_data="esc_start"))
    try: bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
    except: pass

def escape_round_start(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    
    if len(game['players']) <= 2:
        start_knb_final(chat_id)
        return

    game['status'] = 'choosing'
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
    survivors_names = []
    
    for p_id in list(game['players'].keys()):
        name = game['players'][p_id]
        if game['choices'][p_id] == game['dead_door']:
            dead_names.append(name)
            game['players'].pop(p_id)
        else:
            survivors_names.append(name)

    res_text = f"📊 *ИТОГИ РАУНДА {game['room']}*\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    res_text += f"💀 *ПОГИБЛИ:* {', '.join(dead_names) if dead_names else 'Никто'}\n"
    res_text += f"💎 *ВЫЖИЛИ:* {', '.join(survivors_names) if survivors_names else 'Никто'}\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    
    bot.send_message(chat_id, res_text, parse_mode="Markdown")
    
    game['room'] += 1
    time.sleep(3)
    escape_round_start(chat_id)

# --- КНБ ФИНАЛ ---
def start_knb_final(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    if len(game['players']) < 2:
        winner = list(game['players'].values())[0] if game['players'] else "Никто"
        bot.send_message(chat_id, f"🏆 *ПОБЕДИТЕЛЬ:* {winner}", parse_mode="Markdown")
        active_escapes.pop(chat_id, None)
        return
    game['status'] = 'knb'; game['knb_score'] = {p_id: 0 for p_id in game['players']}; game['knb_moves'] = {}
    ids = list(game['players'].keys())
    bot.send_message(chat_id, f"🏁 *ФИНАЛЬНАЯ БИТВА (КНБ)*\n👤 {game['players'][ids[0]]} ⚔️ {game['players'][ids[1]]}", parse_mode="Markdown")
    next_knb_step(chat_id)

def next_knb_step(chat_id):
    if chat_id not in active_escapes: return
    markup = InlineKeyboardMarkup().row(InlineKeyboardButton("💎 Камень", callback_data="k_r"), InlineKeyboardButton("✂️ Ножницы", callback_data="k_s"), InlineKeyboardButton("📄 Бумага", callback_data="k_p"))
    bot.send_message(chat_id, "🗳 *Ваш ход:*", parse_mode="Markdown", reply_markup=markup)

# =====================================================================
#                          ДУЭЛЬ НА КУБИКАХ
# =====================================================================
@bot.message_handler(commands=['duel'])
def start_duel(message):
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
    if duel['status'] != 'fighting' or message.from_user.id not in [duel['creator_id'], duel['opponent_id']]: return
    if message.from_user.id in duel['round_rolls']: return
    duel['round_rolls'][message.from_user.id] = message.dice.value
    if len(duel['round_rolls']) == 2:
        time.sleep(5)
        c_id, o_id = duel['creator_id'], duel['opponent_id']
        duel['total_scores'][c_id] += duel['round_rolls'][c_id]
        duel['total_scores'][o_id] = duel['total_scores'].get(o_id, 0) + duel['round_rolls'][o_id]
        if duel['round'] >= 3:
            s1, s2 = duel['total_scores'][c_id], duel['total_scores'][o_id]
            win = duel['creator_name'] if s1 > s2 else duel['opponent_name']
            if s1 == s2: win = "Ничья"
            bot.send_message(chat_id, f"🏆 *ИТОГ:* {s1} — {s2}\n👑 Победил: {win}", parse_mode="Markdown")
            active_duels.pop(chat_id, None)
        else:
            bot.send_message(chat_id, f"📊 *РАУНД {duel['round']}* окончен. Счет: {duel['total_scores'][c_id]} — {duel['total_scores'][o_id]}", parse_mode="Markdown")
            duel['round'] += 1; duel['round_rolls'] = {}

# =====================================================================
#                          ОБРАБОТКА КНОПОК
# =====================================================================
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    chat_id, uid = call.message.chat.id, call.from_user.id
    
    if call.data == "esc_join":
        if chat_id in active_escapes and uid not in active_escapes[chat_id]['players']:
            active_escapes[chat_id]['players'][uid] = call.from_user.first_name
            update_registration_text(chat_id, call.message.message_id)
            
    elif call.data == "esc_start":
        if is_user_admin(chat_id, uid) and chat_id in active_escapes:
            if len(active_escapes[chat_id]['players']) >= 2:
                bot.delete_message(chat_id, call.message.message_id)
                escape_round_start(chat_id)
                
    elif call.data.startswith("dr_"):
        if chat_id in active_escapes and active_escapes[chat_id]['status'] == 'choosing':
            active_escapes[chat_id]['choices'][uid] = int(call.data.split("_")[1])
            bot.answer_callback_query(call.id, f"Выбор принят!")

    elif call.data == "accept_duel":
        if chat_id in active_duels and uid != active_duels[chat_id]['creator_id']:
            active_duels[chat_id].update({'status': 'fighting', 'opponent_id': uid, 'opponent_name': call.from_user.first_name})
            bot.edit_message_text("⚔️ *БИТВА НАЧАЛАСЬ!*", chat_id, call.message.message_id, parse_mode="Markdown")

# =====================================================================
#                          ЗАПУСК
# =====================================================================
@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def getMessage():
    bot.process_new_updates([Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route("/")
def index():
    bot.remove_webhook()
    bot.set_webhook(url=f"{RENDER_EXTERNAL_URL}/{BOT_TOKEN}")
    return "Online", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
