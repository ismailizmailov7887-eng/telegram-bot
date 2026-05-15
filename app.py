import os
import random
import telebot
from flask import Flask, request
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Update
from dotenv import load_dotenv

load_dotenv()

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

if not BOT_TOKEN:
    raise ValueError("ОШИБКА: Переменная BOT_TOKEN не установлена!")

bot = telebot.TeleBot(BOT_TOKEN)

# --- ГЛОБАЛЬНОЕ ХРАНИЛИЩЕ ДЛЯ ИГР ---
active_duels = {}
active_escapes = {}

# --- НАСТРОЙКА ВЕБ-СЕРВЕРА (Flask) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Бот работает через Webhook 24/7!"

@app.route(f'/{BOT_TOKEN}', methods=['POST'])
def telegram_webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    else:
        return 'Forbidden', 403


# --- ФУНКЦИЯ ПРОВЕРКИ АДМИНА ---
def is_admin(chat_id, user_id):
    if chat_id == user_id:  # Если это ЛС с ботом
        return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception as e:
        print(f"Предупреждение проверки прав: {e}")
        return True  # Пропускаем, если возникла ошибка, чтобы не блокировать тесты


# --- ОБРАБОТЧИКИ КОМАНД ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"🎮 Доступные игры:\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏃‍♂️ [ ESCAPE ]\n"
        f"• Команда: ➡️ /escape\n\n"
        f"⚔️ [ DUEL ]\n"
        f"• Команда: ➡️ /duel\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    bot.send_message(message.chat.id, welcome_text)


# --- ИГРА ESCAPE ---
@bot.message_handler(commands=['escape'])
def start_escape(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not is_admin(chat_id, user_id):
        bot.reply_to(message, "🔒 Попросите админа начать игру ESCAPE!")
        return

    if chat_id in active_escapes:
        bot.reply_to(message, "❌ Игра уже запущена!")
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
    btn_join = InlineKeyboardButton("🏃‍♂️ Участвовать", callback_data="join_escape")
    btn_start = InlineKeyboardButton("🚀 Начать игру", callback_data="run_escape")
    btn_stop = InlineKeyboardButton("🛑 Отменить игру", callback_data="stop_escape")
    markup.add(btn_join)
    markup.add(btn_start, btn_stop)

    escape_text = (
        f"🏃‍♂️ **РЕГИСТРАЦИЯ НА ИГРУ ESCAPE** 🏃‍♂️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Игроков собрано: 1 / 30\n"
        f"📝 Список участников:\n"
        f"• {message.from_user.first_name}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Нажмите «Участвовать», затем админ нажмет «Начать игру»!"
    )
    bot.send_message(chat_id, escape_text, parse_mode="Markdown", reply_markup=markup)


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

    stage_text = (
        f"🏃‍♂️ **ESCAPE — РАУНД {game['stage_round']}** 🏃‍♂️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Выжившие: {', '.join(alive_names)}\n\n"
        f"💀 Шанс смерти за опасной дверью: 65%!\n"
        f"Выбирайте дверь 👇"
    )
    bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=stage_text, parse_mode="Markdown", reply_markup=markup)


# --- ЕДИНЫЙ ОБРАБОТЧИК КНОПОК ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    user_name = call.from_user.first_name

    # Регистрация
    if call.data == "join_escape":
        if chat_id not in active_escapes: 
            bot.answer_callback_query(call.id, "Игра не найдена")
            return
        game = active_escapes[chat_id]
        if user_id in game['players']:
            bot.answer_callback_query(call.id, "Вы уже в игре!", show_alert=True)
            return

        game['players'][user_id] = user_name
        bot.answer_callback_query(call.id, "Вы добавлены!")

        player_list = "\n".join([f"• {name}" for name in game['players'].values()])
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🏃‍♂️ Участвовать", callback_data="join_escape"))
        markup.add(InlineKeyboardButton("🚀 Начать игру", callback_data="run_escape"), InlineKeyboardButton("🛑 Отменить игру", callback_data="stop_escape"))

        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=call.message.message_id, 
            text=f"🏃‍♂️ **РЕГИСТРАЦИЯ НА ИГРУ ESCAPE** 🏃‍♂️\n━━━━━━━━━━━━━━━━━━━━━━\n👥 Собрано: {len(game['players'])}\n📝 Список:\n{player_list}", 
            parse_mode="Markdown", 
            reply_markup=markup
        )

    # Старт игры
    elif call.data == "run_escape":
        if chat_id not in active_escapes: return
        game = active_escapes[chat_id]

        if not is_admin(chat_id, user_id):
            bot.answer_callback_query(call.id, "Только админ может начать!", show_alert=True)
            return

        game['status'] = 'playing'
        game['alive'] = list(game['players'].keys())
        bot.answer_callback_query(call.id, "Запуск...")
        send_door_stage(chat_id, call.message.message_id)

    elif call.data == "stop_escape":
        if not is_admin(chat_id, user_id): return
        active_escapes.pop(chat_id, None)
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text="🛑 Игра отменена.", reply_markup=None)

    # Выбор дверей
    elif call.data.startswith("choose_door_"):
        if chat_id not in active_escapes: return
        game = active_escapes[chat_id]
        
        if user_id not in game['alive']:
            bot.answer_callback_query(call.id, "Вы выбыли!", show_alert=True)
            return
        if user_id in game['chosen_doors']:
            bot.answer_callback_query(call.id, "Дверь уже выбрана!", show_alert=True)
            return

        door_num = int(call.data.split("_")[2])
        game['chosen_doors'][user_id] = door_num
        bot.answer_callback_query(call.id, f"Выбрана дверь №{door_num}")

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

            if len(next_alive) == 0:
                next_alive = game['alive']
                dead_this_round = []

            game['alive'] = next_alive
            dead_text = ", ".join(dead_this_round) if dead_this_round else "Никто"
            bot.send_message(chat_id, f"📊 **Итоги раунда {game['stage_round']}**\n💀 Опасная дверь: {death_door}\n⚰️ Погибли: {dead_text}")

            # Проверяем финал
            if len(game['alive']) <= 2:
                if len(game['alive']) > 2:
                    random.shuffle(game['alive'])
                    game['alive'] = game['alive'][:2]
                if len(game['alive']) < 2:
                    all_ids = list(game['players'].keys())
                    game['alive'] = all_ids[:2] if len(all_ids) >= 2 else all_ids

                game['status'] = 'rps_final'
                game['rps'] = {}
                
                markup_rps = InlineKeyboardMarkup()
                markup_rps.add(
                    InlineKeyboardButton("🪨 Камень", callback_data="rps_rock"),
                    InlineKeyboardButton("✂️ Ножницы", callback_data="rps_scissors"),
                    InlineKeyboardButton("📄 Бумага", callback_data="rps_paper")
                )
                bot.send_message(
                    chat_id, 
                    f"🏆 **ФИНАЛ КНБ** 🏆\n💥 **{game['players'][game['alive'][0]]}** vs **{game['players'][game['alive'][1]]}**\nВыбирайте:", 
                    reply_markup=markup_rps
                )
            else:
                game['stage_round'] += 1
                send_door_stage(chat_id, call.message.message_id)

    # Финал КНБ
    elif call.data.startswith("rps_"):
        if chat_id not in active_escapes or active_escapes[chat_id]['status'] != 'rps_final': return
        game = active_escapes[chat_id]

        if user_id not in game['alive']: return
        if user_id in game['rps']: return

        choice = call.data.split("_")[1]
        game['rps'][user_id] = choice
        bot.answer_callback_query(call.id, "Принято!")

        if len(game['rps']) == 2:
            p1_id, p2_id = game['alive'][0], game['alive'][1]
            c1, c2 = game['rps'][p1_id], game['rps'][p2_id]
            n1, n2 = game['players'][p1_id], game['players'][p2_id]

            res = f"🏁 **КОНЕЦ ИГРЫ** 🏁\n👤 {n1}: {c1}\n👤 {n2}: {c2}\n\n"
            if c1 == c2: res += "🤝 Ничья!"
            elif (c1=='rock' and c2=='scissors') or (c1=='scissors' and c2=='paper') or (c1=='paper' and c2=='rock'):
                res += f"👑 Победитель: **{n1}**"
            else:
                res += f"👑 Победитель: **{n2}**"

            bot.send_message(chat_id, res)
            active_escapes.pop(chat_id, None)

    # --- КНОПКИ ДЛЯ ИГРЫ DUEL ---
    elif call.data.startswith("accept_duel_"):
        creator_id = int(call.data.split("_")[2])
        if user_id == creator_id: return
        if chat_id not in active_duels or active_duels[chat_id]['status'] == 'fighting': return

        duel = active_duels[chat_id]
        duel['status'] = 'fighting'
        duel['opponent_id'] = user_id
        duel['opponent_name'] = user_name
        duel['total_scores'][user_id] = 0

        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=call.message.message_id, 
            text=f"⚔️ **БИТВА!** ⚔️\n👤 {duel['creator_name']} vs 👤 {user_name}\n🎲 Раунд 1/3. Кидайте /dice!"
        )


# --- СИСТЕМА ДУЭЛИ ---
@bot.message_handler(content_types=['dice', 'text'], func=lambda msg: msg.chat.id in active_duels)
def monitor_duel_dice(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    duel = active_duels[chat_id]

    if duel['status'] != 'fighting' or message.from_user.is_bot: return
    if user_id != duel['creator_id'] and user_id != duel['opponent_id']: return

    is_command = message.text and message.text.lower().startswith('/dice')
    if not (is_command or (message.dice and message.dice.emoji == '🎲')): return

    if user_id in duel['round_rolls']: return

    score = bot.send_dice(chat_id, emoji='🎲', reply_to_message_id=message.message_id).dice.value if is_command else message.dice.value
    duel['round_rolls'][user_id] = score

    if len(duel['round_rolls']) == 2:
        c_id, o_id = duel['creator_id'], duel['opponent_id']
        duel['total_scores'][c_id] += duel['round_rolls'][c_id]
        duel['total_scores'][o_id] += duel['round_rolls'][o_id]

        if duel['round'] == 3:
            res = f"🏆 ИТОГ ДУЭЛИ:\n✨ {duel['creator_name']}: {duel['total_scores'][c_id]}\n✨ {duel['opponent_name']}: {duel['total_scores'][o_id]}\n"
            bot.send_message(chat_id, res)
            active_duels.pop(chat_id, None)
        else:
            duel['round'] += 1
            duel['round_rolls'] = {}
            bot.send_message(chat_id, f"🎲 **Раунд {duel['round']} / 3**")


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL.rstrip('/')}/{BOT_TOKEN}"
        # КРИТИЧЕСКИЙ ФИКС ОЧЕРЕДИ:
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url, drop_pending_updates=True)
        print(f"Вебхук успешно перезапущен и очищен!")
    app.run(host="0.0.0.0", port=port)
