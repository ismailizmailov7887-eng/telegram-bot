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
        f"➡️ Сброс: `/stop` (Мгновенная остановка любых игр админом)\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")


# =====================================================================
#                          КОМАНДА /STOP (ЭКСТРЕННЫЙ СБРОС)
# =====================================================================
@bot.message_handler(commands=['stop'])
def emergency_stop_games(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not is_user_admin(chat_id, user_id):
        bot.reply_to(message, "❌ Останавливать игры могут только администраторы чата!")
        return

    was_stopped = False

    if chat_id in active_escapes:
        active_escapes.pop(chat_id, None)
        was_stopped = True

    if chat_id in active_duels:
        active_duels.pop(chat_id, None)
        was_stopped = True

    if was_stopped:
        bot.send_message(chat_id, "🛑 **ЭКСТРЕННАЯ ОСТАНОВКА:** Все активные игры и сессии в этом чате были принудительно завершены админом.", parse_mode="Markdown")
    else:
        bot.send_message(chat_id, "ℹ️ В этом чате сейчас нет запущенных игр.")


# =====================================================================
#                          ИГРА 1: DUEL (ДУЭЛЬ)
# =====================================================================
@bot.message_handler(commands=['duel'])
def start_duel(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    if chat_id in active_duels:
        bot.reply_to(message, "❌ В этом чате уже идет дуэль или создано лобби!")
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

    duel_text = (
        f"⚔️ **ВЫЗОВ НА ДУЭЛЬ** ⚔️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Игрок **{user_name}** бросает вызов чату!\n"
        f"🎯 Кто готов сразиться в кости (3 раунда)?\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Нажмите кнопку ниже, чтобы принять вызов! 👇"
    )
    bot.send_message(chat_id, duel_text, parse_mode="Markdown", reply_markup=markup)


# =====================================================================
#                          ИГРА 2: ESCAPE (ВЫЖИВАНИЕ)
# =====================================================================
@bot.message_handler(commands=['escape'])
def start_escape(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not is_user_admin(chat_id, user_id):
        bot.reply_to(message, "❌ Запускать регистрацию на ESCAPE могут только админы чата!")
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
        'timer_id': 0
    }

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🏃‍♂️ Участвовать", callback_data="join_escape"))
    markup.add(InlineKeyboardButton("🚀 Начать игру", callback_data="run_escape"), 
               InlineKeyboardButton("🛑 Отменить", callback_data="stop_escape"))

    text = (
        f"🏃‍♂️ **РЕГИСТРАЦИЯ НА ИГРУ ESCAPE** 🏃‍♂️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Собрано игроков: 1\n"
        f"📝 Список:\n• {message.from_user.first_name}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 Администратор, нажмите «Начать игру», когда все соберутся!"
    )
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)


def send_door_stage(chat_id, message_id=None):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    game['chosen_doors'] = {}  
    alive_names = [game['players'][uid] for uid in game['alive']]
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🚪 Дверь 1", callback_data="choose_door_1"),
        InlineKeyboardButton("🚪 Дверь 2", callback_data="choose_door_2"),
        InlineKeyboardButton("🚪 Дверь 3", callback_data="choose_door_3")
    )

    text = (
        f"🚪 **ESCAPE — РАУНД {game['stage_round']}** 🚪\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Оставшиеся в живых ({len(game['alive'])}):\n"
        f"🔥 {', '.join(alive_names)}\n\n"
        f"⚡️ Каждую секунду ловушка меняет свое местоположение!\n"
        f"⏳ **У вас ровно 10 секунд на выбор двери!** 👇"
    )
    
    if message_id:
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            try:
                msg = bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
                message_id = msg.message_id
            except Exception: return
    else:
        try:
            msg = bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)
            message_id = msg.message_id
        except Exception: return

    game['timer_id'] += 1
    current_timer_id = game['timer_id']
    
    t = threading.Thread(target=door_timeout, args=(chat_id, game['stage_round'], current_timer_id))
    t.daemon = True
    t.start()


def door_timeout(chat_id, round_num, timer_id):
    time.sleep(10)
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    
    if game['status'] != 'playing' or game['stage_round'] != round_num or game['timer_id'] != timer_id:
        return
        
    dead_by_timeout = []
    for uid in list(game['alive']):
        if uid not in game['chosen_doors']:
            dead_by_timeout.append(game['players'][uid])
            game['alive'].remove(uid)
            
    if dead_by_timeout:
        try:
            bot.send_message(chat_id, f"⏱ **ВРЕМЯ ИСТЕКЛО!**\n⚰️ Игроки: *{', '.join(dead_by_timeout)}* не успели сделать выбор и превратились в пыль.", parse_mode="Markdown")
        except Exception: pass
        
    process_round_results(chat_id)


def process_round_results(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    
    if not game['alive']:
        bot.send_message(chat_id, "💀 **Никто не выжил!** Все игроки погибли из-за нерешительности. Игра окончена.")
        active_escapes.pop(chat_id, None)
        return

    death_door = random.choice([1, 2, 3])
    next_alive = []
    dead_this_round = []

    for uid in game['alive']:
        if game['chosen_doors'].get(uid) == death_door:
            if random.random() < 0.65:
                dead_this_round.append(game['players'][uid])
            else:
                next_alive.append(uid)
        else:
            next_alive.append(uid)

    if not next_alive:
        next_alive = game['alive'].copy()
        dead_this_round = []
        bot.send_message(chat_id, f"⚠️ Ловушка захлопнулась в двери **{death_door}**, но боги пощадили вас! Все выжили, продолжаем марафон.")

    game['alive'] = next_alive
    dead_text = ", ".join(dead_this_round) if dead_this_round else "Никто"
    
    round_report = (
        f"📊 **ИТОГИ РАУНДА {game['stage_round']}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💀 Ловушка находилась в: **Комнате №{death_door}**\n"
        f"⚰️ Погибли в этом раунде: *{dead_text}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    bot.send_message(chat_id, round_report, parse_mode="Markdown")

    if len(game['alive']) == 1:
        winner_name = game['players'][game['alive'][0]]
        bot.send_message(chat_id, f"👑 **ПОБЕДИТЕЛЬ ESCAPE:**\n━━━━━━━━━━━━━━━━━━━━━━\n🎉 Игрок **{winner_name}** прошел через весь ад и выжил один! 👑", parse_mode="Markdown")
        active_escapes.pop(chat_id, None)
    elif len(game['alive']) == 2:
        game['status'] = 'rps_final'
        send_rps_stage(chat_id)
    else:
        game['stage_round'] += 1
        send_door_stage(chat_id)


def send_rps_stage(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    game['rps'] = {} 
    
    markup_rps = InlineKeyboardMarkup()
    markup_rps.add(
        InlineKeyboardButton("🪨 Камень", callback_data="rps_rock"),
        InlineKeyboardButton("✂️ Ножницы", callback_data="rps_scissors")
    )
    markup_rps.add(InlineKeyboardButton("📄 Бумага", callback_data="rps_paper"))
    
    p1_name = game['players'][game['alive'][0]]
    p2_name = game['players'][game['alive'][1]]
    
    bot.send_message(
        chat_id, 
        f"🏆 **ФИНАЛ КНБ** 🏆\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💥 **{p1_name}**  vs  **{p2_name}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Осталось только двое! Выберите свое оружие для финального удара 👇", 
        reply_markup=markup_rps,
        parse_mode="Markdown"
    )


# =====================================================================
#                      ОБРАБОТЧИК ИНЛАЙН-КНОПОК
# =====================================================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    user_name = call.from_user.first_name

    # --- КНОПКИ ДУЭЛИ ---
    if call.data.startswith("accept_duel_"):
        creator_id = int(call.data.split("_")[2])
        if user_id == creator_id: 
            bot.answer_callback_query(call.id, "❌ Нельзя играть против самого себя!", show_alert=True)
            return
        if chat_id not in active_duels or active_duels[chat_id]['status'] == 'fighting': 
            bot.answer_callback_query(call.id, "Дуэль уже недоступна.")
            return

        duel = active_duels[chat_id]
        duel['status'] = 'fighting'
        duel['opponent_id'] = user_id
        duel['opponent_name'] = user_name
        duel['total_scores'][user_id] = 0

        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=call.message.message_id, 
            text=f"⚔️ **БИТВА НАЧАЛАСЬ!** ⚔️\n━━━━━━━━━━━━━━━━━━━━━━\n👤 {duel['creator_name']}  vs  👤 {user_name}\n\n🎲 **РАУНД 1 / 3**\nОтправьте команду `/dice` или пришлите кубик 🎲 в чат!",
            parse_mode="Markdown"
        )

    elif call.data == "stop_duel":
        if not is_user_admin(chat_id, user_id):
            bot.answer_callback_query(call.id, "❌ Отменять дуэль могут только админы!", show_alert=True)
            return
        active_duels.pop(chat_id, None)
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="🛑 Дуэль отменена.", reply_markup=None)

    # --- КНОПКИ ESCAPE ---
    elif call.data == "join_escape":
        if chat_id not in active_escapes: return
        game = active_escapes[chat_id]
        if game['status'] != 'registration': return
        
        if user_id in game['players']:
            bot.answer_callback_query(call.id, "Вы уже в игре!", show_alert=True)
            return

        game['players'][user_id] = user_name
        bot.answer_callback_query(call.id, "Вы добавлены!")

        player_list = "\n".join([f"• {name}" for name in game['players'].values()])
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🏃‍♂️ Участвовать", callback_data="join_escape"))
        markup.add(InlineKeyboardButton("🚀 Начать игру", callback_data="run_escape"), 
                   InlineKeyboardButton("🛑 Отменить", callback_data="stop_escape"))

        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=call.message.message_id, 
            text=f"🏃‍♂️ **РЕГИСТРАЦИЯ НА ИГРУ ESCAPE** 🏃‍♂️\n━━━━━━━━━━━━━━━━━━━━━━\n👥 Собрано: {len(game['players'])}\n📝 Список:\n{player_list}", 
            parse_mode="Markdown", 
            reply_markup=markup
        )

    elif call.data == "run_escape":
        if chat_id not in active_escapes: return
        game = active_escapes[chat_id]
        
        if not is_user_admin(chat_id, user_id):
            bot.answer_callback_query(call.id, "❌ Начать игру может только админ чата!", show_alert=True)
            return
            
        if game['status'] != 'registration': return
        if len(game['players']) < 2:
            bot.answer_callback_query(call.id, "❌ Нужно хотя бы 2 человека!", show_alert=True)
            return
        
        game['status'] = 'playing'
        game['alive'] = list(game['players'].keys())
        bot.answer_callback_query(call.id, "Игра стартует!")
        send_door_stage(chat_id, call.message.message_id)

    elif call.data == "stop_escape":
        if not is_user_admin(chat_id, user_id):
            bot.answer_callback_query(call.id, "❌ Отменить игру может только админ чата!", show_alert=True)
            return
        active_escapes.pop(chat_id, None)
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="🛑 Игра ESCAPE отменена админом.", reply_markup=None)

    elif call.data.startswith("choose_door_"):
        if chat_id not in active_escapes: return
        game = active_escapes[chat_id]
        if game['status'] != 'playing': return
        if user_id not in game['alive']:
            bot.answer_callback_query(call.id, "❌ Вы не участвуете или уже погибли!", show_alert=True)
            return
        if user_id in game['chosen_doors']:
            bot.answer_callback_query(call.id, "❌ Вы уже выбрали дверь!", show_alert=True)
            return

        door_num = int(call.data.split("_")[2])
        game['chosen_doors'][user_id] = door_num
        bot.answer_callback_query(call.id, f"Вы зашли в дверь №{door_num}")

        if len(game['chosen_doors']) == len(game['alive']):
            process_round_results(chat_id)

    elif call.data.startswith("rps_"):
        if chat_id not in active_escapes: return
        game = active_escapes[chat_id]
        if game['status'] != 'rps_final': return
        if user_id not in game['alive']:
            bot.answer_callback_query(call.id, "❌ Вы не в финале!", show_alert=True)
            return
        if user_id in game['rps']:
            bot.answer_callback_query(call.id, "❌ Вы уже сделали выбор!", show_alert=True)
            return

        choice = call.data.split("_")[1]
        game['rps'][user_id] = choice
        bot.answer_callback_query(call.id, "Выбор принят!")

        if len(game['rps']) == 2:
            p1_id, p2_id = game['alive'][0], game['alive'][1]
            c1, c2 = game['rps'][p1_id], game['rps'][p2_id]
            n1, n2 = game['players'][p1_id], game['players'][p2_id]

            translations = {'rock': '🪨 Камень', 'scissors': '✂️ Ножницы', 'paper': '📄 Бумага'}

            res = (
                f"🏁 **ИТОГИ ФИНАЛЬНОГО БОЯ** 🏁\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 {n1}: **{translations[c1]}**\n"
                f"👤 {n2}: **{translations[c2]}**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            
            if c1 == c2:
                res += "🤝 **Ничья! Снаряды столкнулись в воздухе. Переигровка!**"
                bot.send_message(chat_id, res, parse_mode="Markdown")
                send_rps_stage(chat_id) 
            elif (c1=='rock' and c2=='scissors') or (c1=='scissors' and c2=='paper') or (c1=='paper' and c2=='rock'):
                res += f"👑 **ПОБЕДИТЕЛЬ ESCAPE:** **{n1}** 🎉"
                bot.send_message(chat_id, res, parse_mode="Markdown")
                active_escapes.pop(chat_id, None)
            else:
                res += f"👑 **ПОБЕДИТЕЛЬ ESCAPE:** **{n2}** 🎉"
                bot.send_message(chat_id, res, parse_mode="Markdown")
                active_escapes.pop(chat_id, None)


# =====================================================================
#             ОБРАБОТКА ИГРОВЫХ КУБИКОВ И ТЕКСТА ДУЭЛЕЙ
# =====================================================================
@bot.message_handler(content_types=['dice', 'text'])
def monitor_duel_dice(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if chat_id not in active_duels: return
    duel = active_duels[chat_id]

    if duel['status'] != 'fighting' or message.from_user.is_bot: return
    if user_id != duel['creator_id'] and user_id != duel['opponent_id']: return

    is_command = message.text and message.text.lower().startswith('/dice')
    is_dice_emoji = message.dice and message.dice.emoji == '🎲'
    
    if not (is_command or is_dice_emoji): return

    if user_id in duel['round_rolls']:
        bot.reply_to(message, "❌ Вы уже бросили кубик в этом раунде!")
        return

    if is_command:
        try:
            score = bot.send_dice(chat_id, emoji='🎲', reply_to_message_id=message.message_id).dice.value
        except Exception: return
    else:
        score = message.dice.value

    duel['round_rolls'][user_id] = score

    if len(duel['round_rolls']) == 2:
        c_id, o_id = duel['creator_id'], duel['opponent_id']
        duel['total_scores'][c_id] += duel['round_rolls'][c_id]
        duel['total_scores'][o_id] += duel['round_rolls'][o_id]

        if duel['round'] == 3:
            res = (
                f"🏆 **ФИНАЛ ДУЭЛИ ЗАВЕРШЕН** 🏆\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✨ {duel['creator_name']}: **{duel['total_scores'][c_id]}** очков\n"
                f"✨ {duel['opponent_name']}: **{duel['total_scores'][o_id]}** очков\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            if duel['total_scores'][c_id] > duel['total_scores'][o_id]:
                res += f"🎉 Победитель дуэли: **{duel['creator_name']}** 👑"
            elif duel['total_scores'][o_id] > duel['total_scores'][c_id]:
                res += f"🎉 Победитель дуэли: **{duel['opponent_name']}** 👑"
            else:
                res += "🤝 Ничья по очкам! Победила дружба."
            
            bot.send_message(chat_id, res, parse_mode="Markdown")
            active_duels.pop(chat_id, None)
        else:
            status_text = (
                f"📊 **ИТОГИ РАУНДА №{duel['round']}**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎲 {duel['creator_name']} выбросил: **{duel['round_rolls'][c_id]}**\n"
                f"🎲 {duel['opponent_name']} выбросил: **{duel['round_rolls'][o_id]}**\n\n"
                f"📈 **ОБЩИЙ СЧЕТ:**\n"
                f"✨ {duel['creator_name']}: **{duel['total_scores'][c_id]}**\n"
                f"✨ {duel['opponent_name']}: **{duel['total_scores'][o_id]}**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎲 **РАУНД {duel['round'] + 1} / 3** — Время кидать кубики!"
            )
            bot.send_message(chat_id, status_text, parse_mode="Markdown")
            duel['round'] += 1
            duel['round_rolls'] = {}


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL.rstrip('/')}/{BOT_TOKEN}"
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    app.run(host="0.0.0.0", port=port)
