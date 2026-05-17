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

active_escapes = {}

def is_user_admin(chat_id, user_id):
    if chat_id == user_id: return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except: return False

@bot.message_handler(commands=['escape'])
def start_escape(message):
    if not is_user_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Только админы могут начать игру.")
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

@bot.callback_query_handler(func=lambda call: call.data.startswith(("esc_", "dr_")))
def handle_escape_clicks(call):
    chat_id, uid = call.message.chat.id, call.from_user.id
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]

    if call.data == "esc_join":
        if uid not in game['players']:
            game['players'][uid] = call.from_user.first_name
            bot.answer_callback_query(call.id, "Ты в игре!")
        else:
            bot.answer_callback_query(call.id, "Ты уже вступил.")

    elif call.data == "esc_start":
        if is_user_admin(chat_id, uid):
            if len(game['players']) >= 2:
                bot.delete_message(chat_id, call.message.message_id)
                escape_round_start(chat_id)
            else:
                bot.answer_callback_query(call.id, "Мало игроков!", show_alert=True)

    elif call.data.startswith("dr_"):
        if uid in game['players'] and game['status'] == 'choosing':
            game['choices'][uid] = int(call.data.split("_")[1])
            bot.answer_callback_query(call.id, f"Выбрана дверь {game['choices'][uid]}")

def escape_round_start(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    
    if len(game['players']) <= 1:
        winner = list(game['players'].values())[0] if game['players'] else "Никто"
        bot.send_message(chat_id, f"🏆 *ФИНАЛ*\n👑 Единственный выживший: {winner}", parse_mode="Markdown")
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
    
    bot.send_message(chat_id, f"🔴 *РАУНД {game['room']}*\n\nВ игре:\n{players_list}\n\n📍 Выбирайте дверь! (30 сек)", parse_mode="Markdown", reply_markup=markup)
    threading.Timer(30.0, escape_round_results, args=(chat_id,)).start()

def escape_round_results(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    
    for p_id in list(game['players'].keys()):
        if p_id not in game['choices']:
            game['choices'][p_id] = random.randint(1, 3)

    dead_names = []
    survived_names = []
    
    # Обрабатываем результаты
    for p_id in list(game['players'].keys()):
        name = game['players'][p_id]
        if game['choices'][p_id] == game['dead_door']:
            dead_names.append(name)
            game['players'].pop(p_id)
        else:
            survived_names.append(name)

    # Формируем короткий отчет
    res_text = f"📊 *ИТОГИ РАУНДА {game['room']}*\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    
    if dead_names:
        res_text += f"💀 *ПОГИБЛИ:* {', '.join(dead_names)}\n"
    else:
        res_text += "💀 *ПОГИБЛИ:* Никто (всем повезло!)\n"
        
    res_text += f"💎 *ВЫЖИЛИ:* {', '.join(survived_names) if survived_names else 'Никто'}\n"
    res_text += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"

    bot.send_message(chat_id, res_text, parse_mode="Markdown")
    
    game['room'] += 1
    time.sleep(3)
    escape_round_start(chat_id)

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def getMessage():
    bot.process_new_updates([Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route("/")
def index():
    return "Online", 200

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{RENDER_EXTERNAL_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
