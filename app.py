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

@bot.callback_query_handler(func=lambda call: call.data.startswith(("esc_", "dr_")))
def handle_escape_clicks(call):
    chat_id = call.message.chat.id
    uid = call.from_user.id
    
    if chat_id not in active_escapes:
        bot.answer_callback_query(call.id, "Игра не активна.")
        return

    game = active_escapes[chat_id]

    if call.data == "esc_join":
        if uid not in game['players']:
            game['players'][uid] = call.from_user.first_name
            players_list = "\n".join([f"👤 {name}" for name in game['players'].values()])
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("➕ ВСТУПИТЬ", callback_data="esc_join"),
                                               InlineKeyboardButton("🚀 НАЧАТЬ", callback_data="esc_start"))
            bot.edit_message_text(f"🎮 *ИГРОКИ:* {len(game['players'])}\n{players_list}", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.answer_callback_query(call.id, "Ты уже в списке!")

    elif call.data == "esc_start":
        if is_user_admin(chat_id, uid):
            if len(game['players']) >= 2:
                bot.delete_message(chat_id, call.message.message_id)
                escape_round_start(chat_id)
            else:
                bot.answer_callback_query(call.id, "Минимум 2 игрока!", show_alert=True)

    elif call.data.startswith("dr_"):
        if uid in game['players']:
            game['choices'][uid] = int(call.data.split("_")[1])
            bot.answer_callback_query(call.id, f"Выбрана дверь {game['choices'][uid]}")

def escape_round_start(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    
    # ПРОВЕРКА ПОБЕДИТЕЛЯ
    count = len(game['players'])
    if count == 0:
        bot.send_message(chat_id, "💀 Все погибли. Конец игры.")
        active_escapes.pop(chat_id, None)
        return
    if count == 1:
        winner = list(game['players'].values())[0]
        bot.send_message(chat_id, f"🏆 *ЕДИНСТВЕННЫЙ ВЫЖИВШИЙ:* {winner}", parse_mode="Markdown")
        active_escapes.pop(chat_id, None)
        return

    game['status'] = 'choosing'
    game['choices'] = {} # Очищаем старые ходы!
    game['dead_door'] = random.randint(1, 3)
    
    players_list = "\n".join([f"👤 {name}" for name in game['players'].values()])
    markup = InlineKeyboardMarkup().row(
        InlineKeyboardButton("🚪 1", callback_data="dr_1"),
        InlineKeyboardButton("🚪 2", callback_data="dr_2"),
        InlineKeyboardButton("🚪 3", callback_data="dr_3")
    )
    
    bot.send_message(chat_id, f"🔴 *РАУНД {game['room']}*\n\n{players_list}\n\nУ вас 30 секунд на выбор!", parse_mode="Markdown", reply_markup=markup)
    
    # Запускаем таймер завершения раунда
    threading.Timer(30.0, escape_round_results, args=(chat_id,)).start()

def escape_round_results(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    
    # Авто-выбор для тех, кто проспал
    for p_id in list(game['players'].keys()):
        if p_id not in game['choices']:
            game['choices'][p_id] = random.randint(1, 3)

    dead_list = []
    door_data = {1: [], 2: [], 3: []}
    
    for p_id, door in game['choices'].items():
        name = game['players'].get(p_id)
        if not name: continue
        
        if door == game['dead_door'] and random.random() < 0.65:
            dead_list.append(p_id)
        else:
            door_data[door].append(name)

    # УДАЛЯЕМ мертвых
    for p_id in dead_list:
        game['players'].pop(p_id, None)

    res_text = f"📊 *ИТОГИ РАУНДА {game['room']}*\n\n"
    for d in range(1, 4):
        p_str = ", ".join(door_data[d]) if door_data[d] else "Пусто"
        icon = "💀 ЛОВУШКА" if d == game['dead_door'] else "✅ ОК"
        res_text += f"🚪 Дверь {d}: {p_str} ({icon})\n"

    survivors = list(game['players'].values())
    res_text += f"\n💎 *ВЫЖИЛИ:* {', '.join(survivors) if survivors else 'Никто'}"
    
    bot.send_message(chat_id, res_text, parse_mode="Markdown")
    
    # Переход к следующему раунду
    game['room'] += 1
    time.sleep(2) # Небольшая пауза перед следующим раундом
    escape_round_start(chat_id)

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def getMessage():
    bot.process_new_updates([Update.de_json(request.stream.read().decode("utf-8"))])
    return "!", 200

@app.route("/")
def index():
    return "Bot Online", 200

if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{RENDER_EXTERNAL_URL}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
