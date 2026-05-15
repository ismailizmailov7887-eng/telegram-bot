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
# active_escapes: { chat_id: { status, creator_id, players, alive, stage_round, chosen_doors, rps } }
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


# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ПРОВЕРКИ АДМИНА ---
def is_admin(chat_id, user_id):
    try:
        if chat_id == user_id:
            return True
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception as e:
        print(f"Ошибка проверки прав: {e}")
        return False


# --- ОБРАБОТЧИКИ КОМАНД ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"🎮 Доступные игры в этой группе:\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏃‍♂️ [ ESCAPE ]\n"
        f"• Описание: Раунды идут, пока не останется 2 выживших (шанс смерти за опасной дверью 65%). В конце — КНБ!\n"
        f"• Запуск: ➡️ /escape\n"
        f"⚠️ Доступно только для администрации.\n\n"
        f"⚔️ [ DUEL ]\n"
        f"• Описание: Сразись 1 на 1. Накопительный счет за 3 броска!\n"
        f"• Вызов: ➡️ /duel\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    bot.send_message(message.chat.id, welcome_text)


# --- ИГРА ESCAPE (РЕГИСТРАЦИЯ) ---
@bot.message_handler(commands=['escape'])
def start_escape(message):
    chat_id = message.chat.id
    user_id = message.from_user.id

    if not is_admin(chat_id, user_id):
        error_text = (
            f"⚠️ **Доступ ограничен**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏃‍♂️ Игра ESCAPE может быть запущена только администрацией чата!\n\n"
            f"🔒 Пожалуйста, попросите администратора ввести команду /escape."
        )
        bot.reply_to(message, error_text, parse_mode="Markdown")
        return

    if chat_id in active_escapes:
        bot.reply_to(message, "❌ В этом чате уже запущена игра ESCAPE!")
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
        f"📋 Требуется участников: от 4 до 30.\n"
        f"Жмите кнопку «Участвовать»!"
    )
    bot.send_message(chat_id, escape_text, parse_mode="Markdown", reply_markup=markup)


# --- ОТПРАВКА ТЕКУЩЕГО РАУНДА ДВЕРЕЙ ---
def send_door_stage(chat_id, message_id):
    game = active_escapes[chat_id]
    game['chosen_doors'] = {} # Очищаем выборы для нового раунда
    
    alive_names = [game['players'][uid] for uid in game['alive']]
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🚪 Дверь №1", callback_data="choose_door_1"),
        InlineKeyboardButton("🚪 Дверь №2", callback_data="choose_door_2"),
        InlineKeyboardButton("🚪 Дверь №3", callback_data="choose_door_3")
    )

    stage_text = (
        f"🏃‍♂️ **ESCAPE — РАУНД {game['stage_round']}** 🏃‍♂️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Выживших ({len(game['alive'])}): {', '.join(alive_names)}\n\n"
        f"🚨 Ловушки перенастроены! Перед вами снова 3 двери.\n"
        f"💀 За одной из них смерть с вероятностью 65%!\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Выжившие, выбирайте свою дверь 👇"
    )
    bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=stage_text, parse_mode="Markdown", reply_markup=markup)


# --- ОБРАБОТКА CALLBACK КНОПОК ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    user_name = call.from_user.first_name

    # --- РЕГИСТРАЦИЯ И СТАРТ ---
    if call.data == "join_escape":
        if chat_id not in active_escapes: return
        game = active_escapes[chat_id]
        if user_id in game['players']:
            bot.answer_callback_query(call.id, text="🙋‍♂️ Вы уже в игре!", show_alert=True)
            return
        if len(game['players']) >= 30:
            bot.answer_callback_query(call.id, text="🚫 Лобби заполнено (макс. 30)!", show_alert=True)
            return

        game['players'][user_id] = user_name
        bot.answer_callback_query(call.id, text="✅ Добавлены в список!")

        player_list = "\n".join([f"• {name}" for name in game['players'].values()])
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🏃‍♂️ Участвовать", callback_data="join_escape"))
        markup.add(InlineKeyboardButton("🚀 Начать игру", callback_data="run_escape"), InlineKeyboardButton("🛑 Отменить игру", callback_data="stop_escape"))

        updated_text = (
            f"🏃‍♂️ **РЕГИСТРАЦИЯ НА ИГРУ ESCAPE** 🏃‍♂️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👥 Игроков собрано: {len(game['players'])} / 30\n"
            f"📝 Список участников:\n{player_list}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=updated_text, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "run_escape":
        if chat_id not in active_escapes: return
        game = active_escapes[chat_id]

        if not is_admin(chat_id, user_id):
            bot.answer_callback_query(call.id, text="⚠️ Начать игру может только администратор!", show_alert=True)
            return
        if len(game['players']) < 4:
            bot.answer_callback_query(call.id, text=f"❌ Нужно от 4 до 30 игроков! Сейчас: {len(game['players'])}", show_alert=True)
            return

        game['status'] = 'playing'
        game['alive'] = list(game['players'].keys())
        send_door_stage(chat_id, call.message.message_id)

    elif call.data == "stop_escape":
        if not is_admin(chat_id, user_id): return
        active_escapes.pop(chat_id, None)
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=f"🛑 **Игра ESCAPE отменена админом.**", reply_markup=None)

    # --- ИГРОВОЙ ПРОЦЕСС: ДВЕРИ ---
    elif call.data.startswith("choose_door_"):
        if chat_id not in active_escapes: return
        game = active_escapes[chat_id]
        
        if user_id not in game['alive']:
            bot.answer_callback_query(call.id, text="👻 Вы выбыли из игры!", show_alert=True)
            return
        if user_id in game['chosen_doors']:
            bot.answer_callback_query(call.id, text="🚪 Дверь уже выбрана!", show_alert=True)
            return

        door_num = int(call.data.split("_")[2])
        game['chosen_doors'][user_id] = door_num
        bot.answer_callback_query(call.id, text=f"Вы зашли в Дверь №{door_num}")

        # Проверяем, все ли оставшиеся в живых сделали выбор
        if len(game['chosen_doors']) == len(game['alive']):
            death_door = random.choice([1, 2, 3]) # Одна из дверей смертельная
            
            next_alive = []
            dead_this_round = []

            for uid in game['alive']:
                user_door = game['chosen_doors'][uid]
                if user_door == death_door:
                    if random.random() < 0.65: # 65% шанс смерти за этой дверью
                        dead_this_round.append(game['players'][uid])
                    else:
                        next_alive.append(uid) # Повезло, выжил (35%)
                else:
                    next_alive.append(uid) # Безопасная дверь

            # Если вдруг умерли ВСЕ в один раунд, отменяем их смерть (чтобы игра не ломалась)
            if len(next_alive) == 0:
                dead_this_round = []
                next_alive = game['alive'] # Даем второй шанс всем текущим

            game['alive'] = next_alive
            
            dead_text = ", ".join(dead_this_round) if dead_this_round else "Никто! Полный сейв."
            round_summary = (
                f"📊 **ИТОГИ РАУНДА {game['stage_round']}**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💀 Опасной была: **Дверь №{death_door}**\n"
                f"⚰️ Погибли на этом этапе: {dead_text}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            )
            bot.send_message(chat_id, round_summary)

            # КРИТИЧЕСКОЕ УСЛОВИЕ: Продолжаем раунды, ПОКА не останется ровно 2 игрока
            if len(game['alive']) <= 2:
                # Если выживших трое или больше (хотя по условию должно стать ровно 2), 
                # но ловушка убила слишком точечно, берем топ-2 из оставшихся живых
                if len(game['alive']) > 2:
                    random.shuffle(game['alive'])
                    game['alive'] = game['alive'][:2]

                # Если остался всего 1 выживший (все остальные разом умерли)
                if len(game['alive']) < 2:
                    # Добираем второго финалиста из списка только что погибших для финального шоу КНБ
                    all_player_ids = list(game['players'].keys())
                    current_alive = game['alive'][0] if game['alive'] else random.choice(all_player_ids)
                    other_candidates = [pid for pid in all_player_ids if pid != current_alive]
                    second_player = random.choice(other_candidates) if other_candidates else current_alive
                    game['alive'] = [current_alive, second_player]

                # ПЕРЕХОД К ФИНАЛУ «КАМЕНЬ, НОЖНИЦЫ, БУМАГА»
                game['status'] = 'rps_final'
                game['rps'] = {}
                
                p1_name = game['players'][game['alive'][0]]
                p2_name = game['players'][game['alive'][1]]

                rps_text = (
                    f"🏆 **ФИНАЛ ОПРЕДЕЛЕН!** 🏆\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"Они прошли все комнаты смерти и встретились лицом к лицу:\n"
                    f"💥 **{p1_name}**  vs  **{p2_name}**\n\n"
                    f"👊 Выберите оружие на кнопках ниже:"
                )
                
                markup_rps = InlineKeyboardMarkup()
                markup_rps.add(
                    InlineKeyboardButton("🪨 Камень", callback_data="rps_rock"),
                    InlineKeyboardButton("✂️ Ножницы", callback_data="rps_scissors"),
                    InlineKeyboardButton("📄 Бумага", callback_data="rps_paper")
                )
                bot.send_message(chat_id, rps_text, parse_mode="Markdown", reply_markup=markup_rps)
            else:
                # Игроков всё ещё больше двух — включаем следующий раунд дверей (хоть 10-й, хоть 25-й)
                game['stage_round'] += 1
                send_door_stage(chat_id, call.message.message_id)

    # --- ФИНАЛ КНБ ---
    elif call.data.startswith("rps_"):
        if chat_id not in active_escapes or active_escapes[chat_id]['status'] != 'rps_final': return
        game = active_escapes[chat_id]

        if user_id not in game['alive']:
            bot.answer_callback_query(call.id, text="❌ Вы зритель, выбор делают только финалисты!", show_alert=True)
            return
        if user_id in game['rps']:
            bot.answer_callback_query(call.id, text="⏳ Ваш выбор учтен. Ждем оппонента!", show_alert=True)
            return

        choice = call.data.split("_")[1]
        game['rps'][user_id] = choice
        bot.answer_callback_query(call.id, text="Выбор сделан!")

        if len(game['rps']) == 2:
            p1_id, p2_id = game['alive'][0], game['alive'][1]
            p1_name, p2_name = game['players'][p1_id], game['players'][p2_id]
            c1, c2 = game['rps'][p1_id], game['rps'][p2_id]

            emoji_map = {'rock': '🪨 Камень', 'scissors': '✂️ Ножницы', 'paper': '📄 Бумага'}

            result_rps = (
                f"🏁 **КОНЕЦ ИГРЫ ESCAPE** 🏁\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 {p1_name}: {emoji_map[c1]}\n"
                f"👤 {p2_name}: {emoji_map[c2]}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            )

            if c1 == c2:
                result_rps += "🤝 Ничья! Оба финалиста выжили и забирают главный приз бункера! 🎉"
            elif (c1 == 'rock' and c2 == 'scissors') or (c1 == 'scissors' and c2 == 'paper') or (c1 == 'paper' and c2 == 'rock'):
                result_rps += f"🎉 Абсолютный победитель ESCAPE: **{p1_name}** 👑"
            else:
                result_rps += f"🎉 Абсолютный победитель ESCAPE: **{p2_name}** 👑"

            bot.send_message(chat_id, result_rps, parse_mode="Markdown")
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

        start_fight_text = (
            f"⚔️ **БИТВА НАЧАЛАСЬ!** ⚔️\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 {duel['creator_name']}  vs  👤 {user_name}\n"
            f"🎯 Цель: Максимум очков за 3 раунда кубиков!\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎲 **РАУНД 1 / 3** 🎲\n"
            f"Используйте команду /dice или кидайте 🎲"
        )
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=start_fight_text, parse_mode="Markdown", reply_markup=None)

    elif call.data == "stop_duel":
        if not is_admin(chat_id, user_id): return
        active_duels.pop(chat_id, None)
        bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=f"🛑 **Игра DUEL отменена.**", reply_markup=None)


# --- СИСТЕМА ДУЭЛИ (3 КУБИКА) ---
@bot.message_handler(content_types=['dice', 'text'], func=lambda msg: msg.chat.id in active_duels)
def monitor_duel_dice(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    duel = active_duels[chat_id]

    if duel['status'] != 'fighting' or message.from_user.is_bot: return
    if user_id != duel['creator_id'] and user_id != duel['opponent_id']: return

    is_command = message.text and message.text.lower().startswith('/dice')
    is_emoji_dice = message.dice is not None and message.dice.emoji == '🎲'
    if not (is_command or is_emoji_dice): return

    if user_id in duel['round_rolls']:
        bot.reply_to(message, f"❌ Вы уже бросили кубик в {duel['round']}-м раунде!")
        return

    score = bot.send_dice(chat_id, emoji='🎲', reply_to_message_id=message.message_id).dice.value if is_command else message.dice.value
    duel['round_rolls'][user_id] = score

    if len(duel['round_rolls']) == 2:
        c_id, o_id = duel['creator_id'], duel['opponent_id']
        c_name, o_name = duel['creator_name'], duel['opponent_name']
        
        duel['total_scores'][c_id] += duel['round_rolls'][c_id]
        duel['total_scores'][o_id] += duel['round_rolls'][o_id]

        if duel['round'] == 3:
            result_text = (
                f"🏆 РЕЗУЛЬТАТЫ ДУЭЛИ 🏆\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 ФИНАЛЬНЫЙ СЧЁТ:\n"
                f"✨ {c_name}: {duel['total_scores'][c_id]} 🔥\n"
                f"✨ {o_name}: {duel['total_scores'][o_id]} 🔥\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            if duel['total_scores'][c_id] > duel['total_scores'][o_id]:
                result_text += f"🎉 Победитель: {c_name} 👑"
            elif duel['total_scores'][o_id] > duel['total_scores'][c_id]:
                result_text += f"🎉 Победитель: {o_name} 👑"
            else:
                result_text += "🤝 Ничья!"
            bot.send_message(chat_id, result_text)
            active_duels.pop(chat_id, None)
        else:
            status_text = (
                f"📊 ИТОГИ {duel['round']}-ГО РАУНДА\n"
                f"📈 Общий счёт:\n"
                f"• {c_name}: {duel['total_scores'][c_id]}\n"
                f"• {o_name}: {duel['total_scores'][o_id]}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"🎲 **РАУНД {duel['round'] + 1} / 3** 🎲"
            )
            bot.send_message(chat_id, status_text)
            duel['round'] += 1
            duel['round_rolls'] = {}


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL.rstrip('/')}/{BOT_TOKEN}"
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url, drop_pending_updates=True)
    app.run(host="0.0.0.0", port=port)
