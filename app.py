import os
import random
import threading
import telebot
from flask import Flask, request
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Update
from dotenv import load_dotenv

load_dotenv()

# --- Конфигурация ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    print("ОШИБКА: BOT_TOKEN не найден в переменных окружения!")

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
    
    text = (
        "🎮 *ИГРА ESCAPE НАЧИНАЕТСЯ*\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "👥 *УЧАСТНИКИ:*\n"
        "📍 Список пуст...\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "Жми кнопку, чтобы войти!"
    )
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

def update_registration_text(chat_id, message_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    players_list = "\n".join([f"👤 {name}" for name in game['players'].values()])
    
    text = (
        "🎮 *ИГРА ESCAPE НАЧИНАЕТСЯ*\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"👥 *Участников:* {len(game['players'])}\n"
        f"{players_list if players_list else '📍 Список пуст...'}\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "Жми кнопку, чтобы войти!"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ ВСТУПИТЬ", callback_data="esc_join"))
    markup.add(InlineKeyboardButton("🚀 НАЧАТЬ", callback_data="esc_start"))
    
    try:
        bot.edit_message_text(text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
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
    
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🚪 Дверь 1", callback_data="dr_1"),
        InlineKeyboardButton("🚪 Дверь 2", callback_data="dr_2"),
        InlineKeyboardButton("🚪 Дверь 3", callback_data="dr_3")
    )
    
    text = (
        f"🔴 *РАУНД {game['room']}*\n\n"
        f"🎲 Выберите свою комнату\n\n"
        f"👥 В игре ({len(game['players'])}):\n"
        f"{players_list}\n\n"
        f"⏰ У вас 30 секунд!"
    )
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
    threading.Timer(30.0, escape_round_results, args=(chat_id,)).start()

def escape_round_results(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    
    for p_id in game['players']:
        if p_id not in game['choices']:
            game['choices'][p_id] = random.randint(1, 3)

    dead_list = []
    door_data = {1: [], 2: [], 3: []}
    
    for p_id, door in game['choices'].items():
        name = game['players'][p_id]
        if door == game['dead_door'] and random.random() < 0.65:
            dead_list.append(p_id)
        else:
            door_data[door].append(name)

    # Исправленная логика удаления игроков (Олег больше не воскреснет)
    for p_id in dead_list:
        game['players'].pop(p_id, None)

    res_text = f"📊 *РЕЗУЛЬТАТЫ РАУНДА {game['room']}*\n\n"
    for d in range(1, 4):
        p_str = ", ".join(door_data[d]) if door_data[d] else "Пусто"
        icon = "💀 ЛОВУШКА" if d == game['dead_door'] else "✅ БЕЗОПАСНО"
        res_text += f"🚪 *КОМНАТА {d}*\n{icon}: {p_str}\n\n"

    survivors_names = list(game['players'].values())
    res_text += f"💎 *ВЫЖИЛИ:* {', '.join(survivors_names) if survivors_names else 'Никто'}\n\n"
    
    if not game['players']:
        res_text += "💀 *Все игроки погибли. Игра завершена.*"
        bot.send_message(chat_id, res_text, parse_mode="Markdown")
        active_escapes.pop(chat_id, None)
        return

    res_text += f"🔜 СЛЕДУЮЩИЙ ЭТАП через 5 секунд..."
    bot.send_message(chat_id, res_text, parse_mode="Markdown")
    
    game['room'] += 1
    threading.Timer(5.0, escape_round_start, args=(chat_id,)).start()

def start_knb_final(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    
    if len(game['players']) < 2:
        winner = list(game['players'].values())[0] if game['players'] else "Никто"
        bot.send_message(chat_id, f"🏆 *ПОБЕДИТЕЛЬ:* {winner}", parse_mode="Markdown")
        active_escapes.pop(chat_id, None)
        return
    
    game['status'] = 'knb'
    game['knb_score'] = {p_id: 0 for p_id in game['players']}
    game['knb_moves'] = {}
    
    ids = list(game['players'].keys())
    n1, n2 = game['players'][ids[0]], game['players'][ids[1]]
    
    text = (
        "🏁 *ФИНАЛЬНАЯ БИТВА (КНБ)*\n"
        f"👤 {n1} ⚔️ {n2}\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        "Игра до 3-х побед!"
    )
    bot.send_message(chat_id, text, parse_mode="Markdown")
    next_knb_step(chat_id)

def next_knb_step(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    game['knb_moves'] = {}
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("💎 Камень", callback_data="k_r"),
               InlineKeyboardButton("✂️ Ножницы", callback_data="k_s"),
               InlineKeyboardButton("📄 Бумага", callback_data="k_p"))
    bot.send_message(chat_id, "🗳 *Ваш ход:*", parse_mode="Markdown", reply_markup=markup)

def process_knb_logic(chat_id):
    game = active_escapes[chat_id]
    ids = list(game['players'].keys())
    m1, m2 = game['knb_moves'][ids[0]], game['knb_moves'][ids[1]]
    n1, n2 = game['players'][ids[0]], game['players'][ids[1]]
    rules = {'r': 's', 's': 'p', 'p': 'r'}
    
    if m1 == m2: 
        res = "🤝 *НИЧЬЯ!*"
    elif rules[m1] == m2:
        game['knb_score'][ids[0]] += 1
        res = f"✅ *{n1} забирает раунд!*"
    else:
        game['knb_score'][ids[1]] += 1
        res = f"✅ *{n2} забирает раунд!*"
    
    score_text = f"📊 *СЧЁТ:* {n1} ({game['knb_score'][ids[0]]}) — ({game['knb_score'][ids[1]]}) {n2}"
    bot.send_message(chat_id, f"{res}\n{score_text}", parse_mode="Markdown")
    
    if any(s >= 3 for s in game['knb_score'].values()):
        win_id = max(game['knb_score'], key=game['knb_score'].get)
        bot.send_message(chat_id, f"👑 *ФИНАЛЬНЫЙ ПОБЕДИТЕЛЬ:* {game['players'][win_id]}", parse_mode="Markdown")
        active_escapes.pop(chat_id, None)
    else: 
        threading.Timer(2.0, next_knb_step, args=(chat_id,)).start()

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
    markup.add(InlineKeyboardButton("⚔️ ПРИНЯТЬ", callback_data=f"accept_duel"),
               InlineKeyboardButton("🛑 ОТМЕНА", callback_data="stop_duel"))

    text = (
        f"⚔️ *ВЫЗОВ НА ДУЭЛЬ*\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"👤 {message.from_user.first_name} вызывает на бой!\n"
        f"🎯 3 раунда на кубиках\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    )
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(content_types=['dice'])
def handle_dice(message):
    chat_id = message.chat.id
    if chat_id not in active_duels or message.dice.emoji != '🎲': return
    duel = active_duels[chat_id]
    user_id = message.from_user.id
    if duel['status'] != 'fighting': return
    if user_id not in [duel['creator_id'], duel['opponent_id']]: return
    if user_id in duel['round_rolls']:
        bot.reply_to(message, "Ты уже бросил кубик!")
        return
        
    duel['round_rolls'][user_id] = message.dice.value
    if len(duel['round_rolls']) == 2:
        threading.Thread(target=delayed_duel_result, args=(chat_id,)).start()

def delayed_duel_result(chat_id):
    import time
    time.sleep(5) 
    if chat_id not in active_duels: return
    duel = active_duels[chat_id]
    c_id, o_id = duel['creator_id'], duel['opponent_id']
    
    duel['total_scores'][c_id] += duel['round_rolls'][c_id]
    duel['total_scores'][o_id] = duel['total_scores'].get(o_id, 0) + duel['round_rolls'][o_id]
    
    if duel['round'] == 3:
        c_score = duel['total_scores'][c_id]
        o_score = duel['total_scores'][o_id]
        winner = duel['creator_name'] if c_score > o_score else duel['opponent_name']
        if c_score == o_score: winner = "Ничья"

        res = f"🏆 *ИТОГ:* {duel['creator_name']} {c_score} — {o_score} {duel['opponent_name']}\n👑 Победил: {winner}"
        bot.send_message(chat_id, res, parse_mode="Markdown")
        active_duels.pop(chat_id, None)
    else:
        status = f"📊 *РАУНД {duel['round']} ОКОНЧЕН*\n🔔 Счет: {duel['total_scores'][c_id]} — {duel['total_scores'][o_id]}\n🔜 Бросайте 🎲"
        bot.send_message(chat_id, status, parse_mode="Markdown")
        duel['round'] += 1
        duel['round_rolls'] = {}

# =====================================================================
#                          CALLBACKS
# =====================================================================
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    chat_id = call.message.chat.id
    uid = call.from_user.id

    if call.data == "esc_join":
        if chat_id in active_escapes:
            if uid not in active_escapes[chat_id]['players']:
                active_escapes[chat_id]['players'][uid] = call.from_user.first_name
                bot.answer_callback_query(call.id, "Вы вступили!")
                update_registration_text(chat_id, call.message.message_id)
            else:
                bot.answer_callback_query(call.id, "Ты уже в игре!")
                
    elif call.data == "esc_start":
        if is_user_admin(chat_id, uid) and chat_id in active_escapes:
            if len(active_escapes[chat_id]['players']) >= 2:
                bot.edit_message_text("🎮 *ИГРА НАЧИНАЕТСЯ!*", chat_id, call.message.message_id, parse_mode="Markdown")
                escape_round_start(chat_id)
            else: 
                bot.answer_callback_query(call.id, "Нужно минимум 2 игрока", show_alert=True)
            
    elif call.data.startswith("dr_"):
        if chat_id in active_escapes and active_escapes[chat_id]['status'] == 'choosing':
            active_escapes[chat_id]['choices'][uid] = int(call.data.split("_")[1])
            bot.answer_callback_query(call.id, "Принято!")
            
    elif call.data.startswith("k_"):
        if chat_id in active_escapes and active_escapes[chat_id]['status'] == 'knb':
            active_escapes[chat_id]['knb_moves'][uid] = call.data.split("_")[1]
            bot.answer_callback_query(call.id, "Ок!")
            if len(active_escapes[chat_id]['knb_moves']) == 2:
                process_knb_logic(chat_id)

    elif call.data == "accept_duel":
        if chat_id in active_duels and active_duels[chat_id]['status'] == 'waiting':
            if uid == active_duels[chat_id]['creator_id']: return
            active_duels[chat_id].update({'status': 'fighting', 'opponent_id': uid, 'opponent_name': call.from_user.first_name})
            bot.edit_message_text("⚔️ *БИТВА НАЧАЛАСЬ!*", chat_id, call.message.message_id, parse_mode="Markdown")
            
    elif call.data == "stop_duel":
        active_duels.pop(chat_id, None)
        bot.edit_message_text("❌ Отменено.", chat_id, call.message.message_id)

# =====================================================================
#                          WEBHOOK / RUN
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
    return "Online", 200

if __name__ == "__main__":
    # Сначала сбрасываем вебхук, потом ставим заново
    bot.remove_webhook()
    bot.set_webhook(url=f"{RENDER_EXTERNAL_URL}/{BOT_TOKEN}")
    
    # Render передает PORT автоматически
    port = int(os.environ.get('PORT', 5000))
    app.run(host="0.0.0.0", port=port)
