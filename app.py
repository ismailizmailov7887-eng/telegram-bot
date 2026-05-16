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
#                          ГЛАВНОЕ МЕНЮ (НЕ ТРОНУТО)
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
#                          ЛОГИКА ESCAPE (ОБНОВЛЕНО ПО ТЗ)
# =====================================================================
@bot.message_handler(commands=['escape'])
def start_escape(message):
    chat_id = message.chat.id
    if not is_user_admin(chat_id, message.from_user.id):
        bot.reply_to(message, "❌ Только админ может запустить игру.")
        return
    
    active_escapes[chat_id] = {
        'status': 'registration',
        'players': {}, # id: name
        'room': 1,
        'choices': {},
        'dead_door': None
    }
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎮 ВСТУПИТЬ", callback_data="esc_join"))
    markup.add(InlineKeyboardButton("🚀 НАЧАТЬ ИГРУ", callback_data="esc_start"))
    
    text = (
        "🎮 **ИГРА НАЧИНАЕТСЯ!**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🏃‍♂️ Регистрация в ESCAPE открыта.\n"
        "Максимум 30 участников.\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

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
        f"🔴 **РАУНД {game['room']}**\n\n"
        f"🎲 **Выберите комнату!**\n\n"
        f"👥 **Живые ({len(game['players'])}):**\n{players_list}\n\n"
        f"⏰ **30 секунд!**"
    )
    
    msg = bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
    threading.Timer(30.0, escape_round_results, args=(chat_id,)).start()

def escape_round_results(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    
    # Авто-выбор для афк
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

    res_text = f"📊 **РЕЗУЛЬТАТЫ РАУНДА {game['room']}**\n\n"
    for d in range(1, 4):
        p_str = ", ".join(door_data[d]) if door_data[d] else "Пусто"
        icon = "💀" if d == game['dead_door'] else "✅"
        res_text += f"🚪 **КОМНАТА {d}**\n   {icon} {p_str}\n\n"

    survivors_names = []
    for p_id in dead_list:
        game['players'].pop(p_id)
    
    survivors_names = list(game['players'].values())
    res_text += f"✅ **ВЫЖИЛИ:** {', '.join(survivors_names)}\n"
    res_text += f"🔜 **РАУНД {game['room']+1}!** Через 5 секунд..."
    
    bot.send_message(chat_id, res_text, parse_mode="Markdown")
    game['room'] += 1
    threading.Timer(5.0, escape_round_start, args=(chat_id,)).start()

def start_knb_final(chat_id):
    game = active_escapes[chat_id]
    if len(game['players']) < 2:
        winner = list(game['players'].values())[0] if game['players'] else "Никто"
        bot.send_message(chat_id, f"🏆 **ПОБЕДИТЕЛЬ: {winner}**")
        active_escapes.pop(chat_id, None)
        return
    
    game['status'] = 'knb'
    game['knb_score'] = {p_id: 0 for p_id in game['players']}
    game['knb_moves'] = {}
    
    p_names = list(game['players'].values())
    bot.send_message(chat_id, f"🏁 **ФИНАЛ!**\n{p_names[0]} ⚔️ {p_names[1]}\nКНБ до 3-х побед!", parse_mode="Markdown")
    next_knb_step(chat_id)

def next_knb_step(chat_id):
    game = active_escapes[chat_id]
    game['knb_moves'] = {}
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("💎 Камень", callback_data="k_r"),
               InlineKeyboardButton("✂️ Ножницы", callback_data="k_s"),
               InlineKeyboardButton("📄 Бумага", callback_data="k_p"))
    bot.send_message(chat_id, "🎮 **Ваш ход!**", reply_markup=markup)

# =====================================================================
#                          ЛОГИКА ДУЭЛИ (НЕ ТРОНУТО)
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
    if user_id not in [duel['creator_id'], duel['opponent_id']]: return
    if user_id in duel['round_rolls']:
        bot.reply_to(message, "второй раз нельзя кидать леее")
        return
    duel['round_rolls'][user_id] = message.dice.value
    if len(duel['round_rolls']) == 2:
        threading.Thread(target=delayed_duel_result, args=(chat_id,)).start()

def delayed_duel_result(chat_id):
    time.sleep(5)
    if chat_id not in active_duels: return
    duel = active_duels[chat_id]
    c_id, o_id = duel['creator_id'], duel['opponent_id']
    duel['total_scores'][c_id] += duel['round_rolls'][c_id]
    duel['total_scores'][o_id] = duel['total_scores'].get(o_id, 0) + duel['round_rolls'][o_id]
    if duel['round'] == 3:
        res = f"🏆 **ФИНАЛЬНЫЙ СЧЕТ**\n{duel['creator_name']}: {duel['total_scores'][c_id]}\n{duel['opponent_name']}: {duel['total_scores'][o_id]}"
        bot.send_message(chat_id, res, parse_mode="Markdown")
        active_duels.pop(chat_id, None)
    else:
        bot.send_message(chat_id, f"📊 Раунд {duel['round']} окончен. Счет {duel['total_scores'][c_id]}:{duel['total_scores'][o_id]}. СЛЕДУЮЩИЙ РАУНД!")
        duel['round'] += 1
        duel['round_rolls'] = {}

# =====================================================================
#                          CALLBACKS
# =====================================================================
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    chat_id = call.message.chat.id
    uid = call.from_user.id

    # Escape Callbacks
    if call.data == "esc_join":
        if chat_id in active_escapes:
            active_escapes[chat_id]['players'][uid] = call.from_user.first_name
            bot.answer_callback_query(call.id, "Вы вступили!")
    elif call.data == "esc_start":
        if is_user_admin(chat_id, uid) and chat_id in active_escapes:
            if len(active_escapes[chat_id]['players']) >= 2:
                bot.edit_message_text("🎮 ИГРА НАЧИНАЕТСЯ!", chat_id, call.message.message_id)
                escape_round_start(chat_id)
            else: bot.answer_callback_query(call.id, "Нужно 2+ игрока", show_alert=True)
    elif call.data.startswith("dr_"):
        if chat_id in active_escapes and uid in active_escapes[chat_id]['players']:
            active_escapes[chat_id]['choices'][uid] = int(call.data.split("_")[1])
            bot.answer_callback_query(call.id, "Выбор принят!")
    elif call.data.startswith("k_"):
        if chat_id in active_escapes and active_escapes[chat_id]['status'] == 'knb':
            move = call.data.split("_")[1]
            active_escapes[chat_id]['knb_moves'][uid] = move
            bot.answer_callback_query(call.id, "Принято!")
            if len(active_escapes[chat_id]['knb_moves']) == 2:
                process_knb_logic(chat_id)

    # Duel Callbacks
    elif call.data == "accept_duel":
        if chat_id in active_duels and active_duels[chat_id]['status'] == 'waiting':
            if uid == active_duels[chat_id]['creator_id']: return
            active_duels[chat_id].update({'status': 'fighting', 'opponent_id': uid, 'opponent_name': call.from_user.first_name})
            bot.edit_message_text("⚔️ **БИТВА НАЧАЛАСЬ!**", chat_id, call.message.message_id)
    elif call.data == "stop_duel":
        active_duels.pop(chat_id, None)
        bot.edit_message_text("❌ Дуэль отменена.", chat_id, call.message.message_id)

def process_knb_logic(chat_id):
    game = active_escapes[chat_id]
    ids = list(game['players'].keys())
    m1, m2 = game['knb_moves'][ids[0]], game['knb_moves'][ids[1]]
    n1, n2 = game['players'][ids[0]], game['players'][ids[1]]
    rules = {'r': 's', 's': 'p', 'p': 'r'}
    if m1 == m2: res = "🤝 НИЧЬЯ!"
    elif rules[m1] == m2:
        game['knb_score'][ids[0]] += 1
        res = f"✅ {n1} выиграл раунд!"
    else:
        game['knb_score'][ids[1]] += 1
        res = f"✅ {n2} выиграл раунд!"
    bot.send_message(chat_id, f"{res}\n📊 СЧЕТ: {game['knb_score'][ids[0]]}:{game['knb_score'][ids[1]]}")
    if any(s >= 3 for s in game['knb_score'].values()):
        win_id = max(game['knb_score'], key=game['knb_score'].get)
        bot.send_message(chat_id, f"👑 **ПОБЕДИТЕЛЬ: {game['players'][win_id]}**")
        active_escapes.pop(chat_id, None)
    else: threading.Timer(2.0, next_knb_step, args=(chat_id,)).start()

# --- RUN ---
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
