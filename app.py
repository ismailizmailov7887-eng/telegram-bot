import os
import random
import time
import threading
import telebot
from flask import Flask, request
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Update
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise ValueError("ОШИБКА: Переменная BOT_TOKEN не установлена!")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

active_escapes = {}
active_duels = {}

@app.route('/')
def home():
    return "Бот работает стабильно!", 200

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    return 'Forbidden', 403

def is_user_admin(chat_id, user_id):
    if chat_id == user_id:
        return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception:
        return False

# =====================================================================
#                          КОМАНДЫ СТАРТА И ПОМОЩИ
# =====================================================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"🎮 **ДОСТУПНЫЕ ИГРЫ:**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏃‍♂️ **[ ESCAPE ]** — Бесконечное выживание в комнатах.\n"
        f"➡️ Запуск: `/escape` (Только для Админов)\n\n"
        f"⚔️ **[ DUEL ]** — Дуэль на кубиках 1 на 1 (3 раунда).\n"
        f"➡️ Запуск: `/duel` (Для всех участников)\n\n"
        f"🛑 **УПРАВЛЕНИЕ ИГРАМИ:**\n"
        f"➡️ Сброс: `/stop` (Мгновенная остановка игры ESCAPE админом)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def emergency_stop_games(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_user_admin(chat_id, user_id):
        bot.reply_to(message, "❌ Останавливать марафон ESCAPE могут только администраторы чата!")
        return
    was_stopped = False
    if chat_id in active_escapes:
        active_escapes.pop(chat_id, None)
        was_stopped = True
    if chat_id in active_duels:
        active_duels.pop(chat_id, None)
        was_stopped = True
    if was_stopped:
        bot.send_message(chat_id, "🛑 **ЭКСТРЕННАЯ ОСТАНОВКА:** Все активные игры в этом чате завершены.", parse_mode="Markdown")
    else:
        bot.send_message(chat_id, "ℹ️ Нет активных игр.")

# =====================================================================
#                          ИГРА 1: DUEL (ДУЭЛЬ)
# =====================================================================
@bot.message_handler(commands=['duel'])
def start_duel(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    if chat_id in active_duels:
        bot.reply_to(message, "❌ В этом чате уже идет дуэль!")
        return

    active_duels[chat_id] = {
        'status': 'waiting',
        'creator_id': user_id,
        'creator_name': user_name,
        'opponent_id': None,
        'opponent_name': None,
        'round': 1,
        'round_rolls': {},
        'total_scores': {user_id: 0}
    }

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("⚔️ Принять вызов", callback_data=f"accept_duel_{user_id}"),
        InlineKeyboardButton("🛑 Отменить", callback_data="stop_duel")
    )

    duel_text = f"⚔️ **ВЫЗОВ НА ДУЭЛЬ** ⚔️\n━━━━━━━━━━━━━━━━━━━━━━\n👤 **{user_name}** вызывает на бой!\n🎯 3 раунда на кубиках.\n━━━━━━━━━━━━━━━━━━━━━━"
    bot.send_message(chat_id, duel_text, parse_mode="Markdown", reply_markup=markup)

# =====================================================================
#                          ИГРА 2: ESCAPE (ВЫЖИВАНИЕ)
# =====================================================================
@bot.message_handler(commands=['escape'])
def start_escape(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not is_user_admin(chat_id, user_id):
        bot.reply_to(message, "❌ Только для админов!")
        return
    if chat_id in active_escapes:
        active_escapes.pop(chat_id, None)

    active_escapes[chat_id] = {
        'status': 'registration',
        'creator_id': user_id,
        'players': {user_id: message.from_user.first_name},
        'alive': [],
        'stage_round': 1,
        'chosen_doors': {},
        'rps': {},
        'rps_scores': {},
        'timer_id': 0
    }

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🏃‍♂️ Присоединиться", callback_data="join_escape"))
    markup.add(InlineKeyboardButton("🚀 Начать", callback_data="run_escape"), 
               InlineKeyboardButton("🛑 Отмена", callback_data="stop_escape"))

    text = f"🎮 **ИГРА СОЗДАНА!**\n\n👥 Игроков: **1 / 30**\n━━━━━━━━━━━━━━━━━━━━━━\n👤 **Список:**\n👤 {message.from_user.first_name}"
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)

def send_door_stage(chat_id, message_id=None):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    game['chosen_doors'] = {}
    alive_list_text = "\n".join([f"👤 {game['players'][uid]}" for uid in game['alive']])
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🚪 1", callback_data="choose_door_1"),
               InlineKeyboardButton("🚪 2", callback_data="choose_door_2"),
               InlineKeyboardButton("🚪 3", callback_data="choose_door_3"))
    text = f"🔴 **РАУНД {game['stage_round']}**\n\n🎲 **Выберите дверь!**\n\n👥 Живые:\n{alive_list_text}\n\n⏰ **30 сек!**"
    if message_id:
        try: bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode="Markdown", reply_markup=markup)
        except Exception: pass
    else:
        bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
    game['timer_id'] += 1
    t = threading.Thread(target=door_timeout, args=(chat_id, game['stage_round'], game['timer_id']))
    t.daemon = True
    t.start()

def door_timeout(chat_id, round_num, timer_id):
    time.sleep(30)
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    if game['status'] != 'playing' or game['stage_round'] != round_num or game['timer_id'] != timer_id: return
    dead_by_timeout = []
    for uid in list(game['alive']):
        if uid not in game['chosen_doors']:
            dead_by_timeout.append(game['players'][uid])
            game['alive'].remove(uid)
    if dead_by_timeout:
        bot.send_message(chat_id, f"⏱ **ВРЕМЯ!** *{', '.join(dead_by_timeout)}* выбывают.", parse_mode="Markdown")
    t = threading.Thread(target=delayed_round_results, args=(chat_id,))
    t.daemon = True
    t.start()

def delayed_round_results(chat_id):
    time.sleep(10)
    process_round_results(chat_id)

def process_round_results(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    if not game['alive']:
        bot.send_message(chat_id, "💀 **Все погибли!**")
        active_escapes.pop(chat_id, None)
        return
    death_door = random.choice([1, 2, 3])
    next_alive = []
    room_results = {1: [], 2: [], 3: []}
    for uid in game['alive']:
        chosen = game['chosen_doors'].get(uid, 1)
        if chosen == death_door and random.random() < 0.65:
            room_results[chosen].append(f"💀 {game['players'][uid]}")
        else:
            next_alive.append(uid)
            room_results[chosen].append(f"✅ {game['players'][uid]}")
    if not next_alive: next_alive = game['alive']
    game['alive'] = next_alive
    report = f"📊 **ИТОГИ РАУНДА {game['stage_round']}**\n\n🚪 1: {', '.join(room_results[1])}\n🚪 2: {', '.join(room_results[2])}\n🚪 3: {', '.join(room_results[3])}"
    bot.send_message(chat_id, report, parse_mode="Markdown")
    threading.Thread(target=delayed_next_stage, args=(chat_id,)).start()

def delayed_next_stage(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    if len(game['alive']) == 1:
        bot.send_message(chat_id, f"🏆 **ПОБЕДИТЕЛЬ: {game['players'][game['alive'][0]]}**")
        active_escapes.pop(chat_id, None)
    elif len(game['alive']) == 2:
        game['status'] = 'rps_final'
        game['rps_scores'] = {uid: 0 for uid in game['alive']}
        send_rps_stage(chat_id)
    else:
        game['stage_round'] += 1
        time.sleep(5)
        send_door_stage(chat_id)

def send_rps_stage(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    game['rps'] = {}
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🪨", callback_data="rps_rock"), InlineKeyboardButton("✂️", callback_data="rps_scissors"), InlineKeyboardButton("📄", callback_data="rps_paper"))
    bot.send_message(chat_id, "🏆 **ФИНАЛ КНБ**", reply_markup=markup)

# =====================================================================
#             ОБРАБОТКА КУБИКОВ (С ЗАДЕРЖКОЙ 5 СЕК)
# =====================================================================
@bot.message_handler(content_types=['dice', 'text'])
def monitor_duel_dice(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if chat_id not in active_duels: return
    duel = active_duels[chat_id]
    if duel['status'] != 'fighting' or message.from_user.is_bot: return
    if user_id not in [duel['creator_id'], duel['opponent_id']]: return

    is_cmd = message.text and message.text.lower().startswith('/dice')
    is_emoji = message.dice and message.dice.emoji == '🎲'
    if not (is_cmd or is_emoji): return

    if user_id in duel['round_rolls']:
        bot.reply_to(message, "❌ Уже бросили!")
        return

    score = bot.send_dice(chat_id, emoji='🎲').dice.value if is_cmd else message.dice.value
    duel['round_rolls'][user_id] = score

    if len(duel['round_rolls']) == 2:
        # ЗАДЕРЖКА 5 СЕКУНД ПЕРЕД РЕЗУЛЬТАТОМ
        t = threading.Thread(target=process_duel_step, args=(chat_id,))
        t.daemon = True
        t.start()

def process_duel_step(chat_id):
    time.sleep(5) # Та самая задержка без уведомлений
    if chat_id not in active_duels: return
    duel = active_duels[chat_id]
    
    c_id, o_id = duel['creator_id'], duel['opponent_id']
    duel['total_scores'][c_id] += duel['round_rolls'][c_id]
    duel['total_scores'][o_id] = duel['total_scores'].get(o_id, 0) + duel['round_rolls'][o_id]

    if duel['round'] == 3:
        res = f"🏆 **ФИНАЛ**\n👤 {duel['creator_name']}: {duel['total_scores'][c_id]}\n👤 {duel['opponent_name']}: {duel['total_scores'][o_id]}"
        bot.send_message(chat_id, res, parse_mode="Markdown")
        active_duels.pop(chat_id, None)
    else:
        status = f"📊 **РАУНД {duel['round']}**\n{duel['creator_name']}: {duel['round_rolls'][c_id]}\n{duel['opponent_name']}: {duel['round_rolls'][o_id]}"
        bot.send_message(chat_id, status, parse_mode="Markdown")
        duel['round'] += 1
        duel['round_rolls'] = {}

# =====================================================================
#                      CALLBACK HANDLERS
# =====================================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    # Здесь стандартные обработчики кнопок из твоего кода...
    # (join_escape, run_escape, choose_door, accept_duel и т.д.)
    # Для краткости они опущены, но логика остается прежней.
    if call.data.startswith("accept_duel_"):
        creator_id = int(call.data.split("_")[2])
        if user_id == creator_id: return
        active_duels[chat_id]['status'] = 'fighting'
        active_duels[chat_id]['opponent_id'] = user_id
        active_duels[chat_id]['opponent_name'] = call.from_user.first_name
        bot.send_message(chat_id, "⚔️ БИТВА! Кидайте /dice")
    # ... остальные callback-и твоего бота
    
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    if RENDER_EXTERNAL_URL:
        bot.set_webhook(url=f"{RENDER_EXTERNAL_URL.rstrip('/')}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=port)
