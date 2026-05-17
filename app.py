import os
import random
import threading
import telebot
import time
from flask import Flask, request
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Update
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Хранилище состояний
active_escapes = {}
active_duels = {}

def is_user_admin(chat_id, user_id):
    if chat_id == user_id: return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except: return False

# =====================================================================
#                          ОБРАБОТЧИК КНОПОК (ВЫШЕ ВСЕХ)
# =====================================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    uid = call.from_user.id
    
    # Кнопка вступления
    if call.data == "esc_join":
        if chat_id in active_escapes:
            game = active_escapes[chat_id]
            if uid not in game['players']:
                game['players'][uid] = call.from_user.first_name
                update_registration_text(chat_id, call.message.message_id)
            else:
                bot.answer_callback_query(call.id, "Ты уже в игре!")

    # Кнопка старта (только админ)
    elif call.data == "esc_start":
        if chat_id in active_escapes:
            if is_user_admin(chat_id, uid):
                if len(active_escapes[chat_id]['players']) >= 2:
                    bot.delete_message(chat_id, call.message.message_id)
                    escape_round_start(chat_id)
                else:
                    bot.answer_callback_query(call.id, "Нужно минимум 2 игрока!", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "Только админ может нажать старт", show_alert=True)

    # КНОПКИ ВЫБОРА ДВЕРЕЙ
    elif call.data.startswith("dr_"):
        if chat_id in active_escapes:
            game = active_escapes[chat_id]
            if uid in game['players']:
                door_num = int(call.data.split("_")[1])
                game['choices'][uid] = door_num
                bot.answer_callback_query(call.id, f"Выбрана дверь {door_num} ✅")
            else:
                bot.answer_callback_query(call.id, "Ты не участвуешь в этом раунде!", show_alert=True)

    # Принятие дуэли
    elif call.data == "accept_duel":
        if chat_id in active_duels:
            duel = active_duels[chat_id]
            if uid != duel['creator_id']:
                duel.update({
                    'status': 'fighting',
                    'opponent_id': uid,
                    'opponent_name': call.from_user.first_name,
                    'total_scores': {duel['creator_id']: 0, uid: 0}
                })
                bot.edit_message_text(f"⚔️ Битва началась: {duel['creator_name']} VS {duel['opponent_name']}!\nКидайте кубики 🎲", chat_id, call.message.message_id)

# =====================================================================
#                          ЛОГИКА ИГРЫ
# =====================================================================
@bot.message_handler(commands=['escape'])
def start_escape(message):
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Только админ!")
        return
    
    active_escapes[message.chat.id] = {
        'status': 'registration',
        'players': {}, 
        'room': 1,
        'choices': {}
    }
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ ВСТУПИТЬ", callback_data="esc_join"))
    markup.add(InlineKeyboardButton("🚀 НАЧАТЬ", callback_data="esc_start"))
    
    bot.send_message(message.chat.id, "🎮 *РЕГИСТРАЦИЯ НА ESCAPE*", parse_mode="Markdown", reply_markup=markup)

def update_registration_text(chat_id, message_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    players_list = "\n".join([f"👤 {name}" for name in game['players'].values()])
    text = f"🎮 *РЕГИСТРАЦИЯ НА ESCAPE*\n\n👥 *Участники:* {len(game['players'])}\n{players_list}"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ ВСТУПИТЬ", callback_data="esc_join"))
    markup.add(InlineKeyboardButton("🚀 НАЧАТЬ", callback_data="esc_start"))
    try: bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
    except: pass

def escape_round_start(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    
    if len(game['players']) <= 1:
        winner = list(game['players'].values())[0] if game['players'] else "Никто"
        bot.send_message(chat_id, f"🏆 *ПОБЕДИТЕЛЬ:* {winner}", parse_mode="Markdown")
        active_escapes.pop(chat_id, None)
        return

    game['status'] = 'choosing'
    game['choices'] = {}
    game['dead_door'] = random.randint(1, 3)
    
    players_list = "\n".join([f"👤 {name}" for name in game['players'].values()])
    markup = InlineKeyboardMarkup().row(
        InlineKeyboardButton("🚪 1", callback_data="dr_1"),
        InlineKeyboardButton("🚪 2", callback_data="dr_2"),
        InlineKeyboardButton("🚪 3", callback_data="dr_3")
    )
    
    bot.send_message(chat_id, f"🔴 *РАУНД {game['room']}*\n\n{players_list}\n\n📍 Выбирайте дверь! (30 сек)", parse_mode="Markdown", reply_markup=markup)
    threading.Timer(30.0, escape_round_results, args=(chat_id,)).start()

def escape_round_results(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    
    # Авто-выбор для тех, кто не нажал
    for p_id in list(game['players'].keys()):
        if p_id not in game['choices']:
            game['choices'][p_id] = random.randint(1, 3)

    dead_names = []
    survived_names = []
    
    for p_id in list(game['players'].keys()):
        name = game['players'][p_id]
        if game['choices'][p_id] == game['dead_door']:
            dead_names.append(name)
            game['players'].pop(p_id)
        else:
            survived_names.append(name)

    res_text = f"📊 *ИТОГИ РАУНДА {game['room']}*\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    res_text += f"💀 *ПОГИБЛИ:* {', '.join(dead_names) if dead_names else 'Никто'}\n"
    res_text += f"💎 *ВЫЖИЛИ:* {', '.join(survived_names) if survived_names else 'Никто'}\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    
    bot.send_message(chat_id, res_text, parse_mode="Markdown")
    
    game['room'] += 1
    time.sleep(3)
    escape_round_start(chat_id)

# =====================================================================
#                          ВЕБХУК И ЗАПУСК
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
    return "Online", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
