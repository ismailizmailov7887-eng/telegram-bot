import os
import random
import telebot
from flask import Flask, request
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Update
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise ValueError("ОШИБКА: Переменная BOT_TOKEN не установлена в настройках Render!")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# Хранилища для активных игр
active_escapes = {}
active_duels = {}

@app.route('/')
def home():
    return "Бот работает!", 200

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = Update.de_json(json_string)
        
        # Жесткий перехват кликов кнопок (для стабильности на Render)
        if update.callback_query:
            handle_callbacks(update.callback_query)
            return 'OK', 200
            
        bot.process_new_updates([update])
        return 'OK', 200
    return 'Forbidden', 403


# =====================================================================
#                          КОМАНДА /START
# =====================================================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"🎮 **ДОСТУПНЫЕ ИГРЫ:**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏃‍♂️ **[ ESCAPE ]** — Выживание в комнатах с дверями.\n"
        f"➡️ Запуск: `/escape`\n\n"
        f"⚔️ **[ DUEL ]** — Дуэль на кубиках 1 на 1 (3 раунда).\n"
        f"➡️ Запуск: `/duel`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown")


# =====================================================================
#                          ИГРА 1: DUEL (ДУЭЛЬ)
# =====================================================================
@bot.message_handler(commands=['duel'])
def start_duel(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name

    if chat_id in active_duels:
        bot.reply_to(message, "❌ В этом чате уже создана дуэль или идет бой!")
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

    if chat_id in active_escapes:
        bot.reply_to(message, "❌ Игра ESCAPE уже запущена!")
        return

    active_escapes[chat_id] = {
        'status': 'registration',
        'creator_id': user_id,
        'players': {user_id: message.from_user.first_name},
        'alive': [],
        'stage_round': 1,
        'chosen_doors': {},
        'rps': {}
    }

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🏃‍♂️ Участвовать", callback_data="join_escape"))
    markup.add(InlineKeyboardButton("🚀 Начать игру", callback_data="run_escape"), 
               InlineKeyboardButton("🛑 Отменить", callback_data="stop_escape"))

    text = (
        f"🏃‍♂️ **РЕГИСТРАЦИЯ НА ИГРУ ESCAPE** 🏃‍♂️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Собрано игроков: 1 / 30\n"
        f"📝 Список:\n• {message.from_user.first_name}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Для тестов лимит снижен. Нажмите «Начать игру»!"
    )
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=markup)


def send_door_stage(chat_id, message_id):
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
        f"🏃‍♂️ **ESCAPE — РАУНД {game['stage_round']}** 🏃‍♂️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Выжившие: {', '.join(alive_names)}\n\n"
        f"💀 За одной из дверей ловушка (65% смерть)!\n"
        f"Выбирайте дверь 👇"
    )
    bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode="Markdown", reply_markup=markup)


# =====================================================================
#                      ЕДИНЫЙ ОБРАБОТЧИК КНОПОК
# =====================================================================
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
        if chat_id not in active_duels or active_duels[chat_id]['status'] == 'fighting': return

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
        active_duels.pop(chat_id, None)
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="🛑 Дуэль отменена.", reply_markup=None)

    # --- КНОПКИ ESCAPE ---
    elif call.data == "join_escape":
        if chat_id not in active_escapes: return
        game = active_escapes[chat_id]
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
        game['status'] = 'playing'
        game['alive'] = list(game['players'].keys())
        bot.answer_callback_query(call.id, "Игра стартует!")
        send_door_stage(chat_id, call.message.message_id)

    elif call.data == "stop_escape":
        active_escapes.pop(chat_id, None)
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="🛑 Игра ESCAPE отменена.", reply_markup=None)

    elif call.data.startswith("choose_door_"):
        if chat_id not in active_escapes: return
        game = active_escapes[chat_id]
        if user_id not in game['alive'] or user_id in game['chosen_doors']: return

        door_num = int(call.data.split("_")[2])
        game['chosen_doors'][user_id] = door_num
        bot.answer_callback_query(call.id, f"Вы зашли в дверь №{door_num}")

        if len(game['chosen_doors']) == len(game['alive']):
            death_door = random.choice([1, 2, 3])
            next_alive = []
            dead_this_round = []

            for uid in game['alive']:
                if game['chosen_doors'][uid] == death_door:
                    if random.random() < 0.65:
                        dead_this_round.append(game['players'][uid])
                    else:
                        next_alive.append(uid)
                else:
                    next_alive.append(uid)

            if not next_alive:
                next_alive = game['alive']
                dead_this_round = []

            game['alive'] = next_alive
            dead_text = ", ".join(dead_this_round) if dead_this_round else "Никто"
            bot.send_message(chat_id, f"📊 **Итоги раунда {game['stage_round']}**\n💀 Ловушка была в двери: {death_door}\n⚰️ Погибли: {dead_text}")

            if len(game['alive']) <= 2:
                if len(game['alive']) < 2:
                    all_ids = list(game['players'].keys())
                    game['alive'] = all_ids[:2] if len(all_ids) >= 2 else all_ids + all_ids

                game['status'] = 'rps_final'
                game['rps'] = {}
                
                markup_rps = InlineKeyboardMarkup()
                markup_rps.add(
                    InlineKeyboardButton("🪨 Камень", callback_data="rps_rock"),
                    InlineKeyboardButton("✂️ Ножницы", callback_data="rps_scissors"),
                    InlineKeyboardButton("📄 Бумага", callback_data="rps_paper")
                )
                bot.send_message(chat_id, f"🏆 **ФИНАЛ КНБ** 🏆\n💥 **{game['players'][game['alive'][0]]}** vs **{game['players'][game['alive'][1]]}**\nВыбирайте:", reply_markup=markup_rps)
            else:
                game['stage_round'] += 1
                send_door_stage(chat_id, call.message.message_id)

    elif call.data.startswith("rps_"):
        if chat_id not in active_escapes or active_escapes[chat_id]['status'] != 'rps_final': return
        game = active_escapes[chat_id]
        if user_id not in game['alive'] or user_id in game['rps']: return

        choice = call.data.split("_")[1]
        game['rps'][user_id] = choice
        bot.answer_callback_query(call.id, "Принято!")

        if len(game['rps']) == 2:
            p1_id, p2_id = game['alive'][0], game['alive'][1]
            c1, c2 = game['rps'][p1_id], game['rps'][p2_id]
            n1, n2 = game['players'][p1_id], game['players'][p2_id]

            res = f"🏁 **ФИНАЛ** 🏁\n👤 {n1}: {c1}\n👤 {n2}: {c2}\n\n"
            if c1 == c2: res += "🤝 Ничья!"
            elif (c1=='rock' and c2=='scissors') or (c1=='scissors' and c2=='paper') or (c1=='paper' and c2=='rock'):
                res += f"👑 Победитель ESCAPE: **{n1}**"
            else:
                res += f"👑 Победитель ESCAPE: **{n2}**"

            bot.send_message(chat_id, res)
            active_escapes.pop(chat_id, None)


# =====================================================================
#                      МЕХАНИКА ОБРАБОТКИ КУБИКОВ ДЛЯ ДУЭЛИ
# =====================================================================
@bot.message_handler(content_types=['dice', 'text'], func=lambda msg: msg.chat.id in active_duels)
def monitor_duel_dice(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    duel = active_duels[chat_id]

    if duel['status'] != 'fighting' or message.from_user.is_bot: return
    if user_id != duel['creator_id'] and user_id != duel['opponent_id']: return

    is_command = message.text and message.text.lower().startswith('/dice')
    if not (is_command or (message.dice and message.dice.emoji == '🎲')): return

    if user_id in duel['round_rolls']:
        bot.reply_to(message, "❌ Вы уже бросили кубик в этом раунде!")
        return

    # Отправляем кубик или считываем значение
    if is_command:
        score = bot.send_dice(chat_id, emoji='🎲', reply_to_message_id=message.message_id).dice.value
    else:
        score = message.dice.value

    duel['round_rolls'][user_id] = score

    # Когда оба игрока кинули кубик
    if len(duel['round_rolls']) == 2:
        c_id, o_id = duel['creator_id'], duel['opponent_id']
        duel['total_scores'][c_id] += duel['round_rolls'][c_id]
        duel['total_scores'][o_id] += duel['round_rolls'][o_id]

        if duel['round'] == 3:
            res = (
                f"🏆 **ФИНАЛ ДУЭЛИ ЗАВЕРШЕН** 🏆\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"✨ {duel['creator_name']}: {duel['total_scores'][c_id]} очков\n"
                f"✨ {duel['opponent_name']}: {duel['total_scores'][o_id]} очков\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            if duel['total_scores'][c_id] > duel['total_scores'][o_id]:
                res += f"🎉 Победитель дуэли: **{duel['creator_name']}** 👑"
            elif duel['total_scores'][o_id] > duel['total_scores'][c_id]:
                res += f"🎉 Победитель дуэли: **{duel['opponent_name']}** 👑"
            else:
                res += "🤝 Ничья по очкам!"
            
            bot.send_message(chat_id, res, parse_mode="Markdown")
            active_duels.pop(chat_id, None)
        else:
            status_text = (
                f"📊 **ИТОГИ {duel['round']} РАУНДА**\n"
                f"• {duel['creator_name']} выбросил: {duel['round_rolls'][c_id]}\n"
                f"• {duel['opponent_name']} выбросил: {duel['round_rolls'][o_id]}\n\n"
                f"📈 **ОБЩИЙ СЧЕТ:**\n"
                f"✨ {duel['creator_name']}: {duel['total_scores'][c_id]}\n"
                f"✨ {duel['opponent_name']}: {duel['total_scores'][o_id]}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎲 **РАУНД {duel['round'] + 1} / 3** — Кидайте кубики!"
            )
            bot.send_message(chat_id, status_text, parse_mode="Markdown")
            duel['round'] += 1
            duel['round_rolls'] = {}


@bot.callback_query_handler(func=lambda call: True)
def standard_callback_handler(call):
    handle_callbacks(call)


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL.rstrip('/')}/{BOT_TOKEN}"
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    app.run(host="0.0.0.0", port=port)
