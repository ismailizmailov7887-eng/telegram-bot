import os
import threading
import time
import random
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask

TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    print("❌ Ошибка: Не найден TELEGRAM_TOKEN!")
    exit(1)

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=10)
app = Flask(__name__)

games = {}
duels = {}


class Game:
    def __init__(self, chat_id, prize, admin_id):
        self.chat_id = chat_id
        self.prize = prize
        self.admin_id = admin_id
        self.players = {}
        self.round = 1
        self.choosing_phase = False
        self.choices = {}
        self.dead_door = None
        
    def add_player(self, user_id, name):
        if user_id not in self.players and len(self.players) < 30:
            self.players[user_id] = {'name': name, 'alive': True}
            return True
        return False
    
    def get_alive_players(self):
        return {uid: data for uid, data in self.players.items() if data['alive']}
    
    def random_dead_door(self):
        self.dead_door = random.choice([1, 2, 3])
        return self.dead_door


class Duel:
    def __init__(self, creator_id, creator_name, prize):
        self.creator_id = creator_id
        self.creator_name = creator_name
        self.prize = prize
        self.player2_id = None
        self.player2_name = None
        self.started = False
        self.scores = {}
        self.roll_count = {}
        self.current_turn = None


def register_commands():
    try:
        commands = [
            BotCommand("start", "Главное меню"),
            BotCommand("help", "Правила игр"),
            BotCommand("duel", "Создать дуэль 1v1"),
            BotCommand("start_game", "Запустить игру 3 двери (админ)"),
            BotCommand("stop_game", "Остановить игру (админ)"),
        ]
        bot.set_my_commands(commands)
    except:
        pass


@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(
        message,
        "✨ ДОБРО ПОЖАЛОВАТЬ ✨\n\n"
        "🚪 /start_game - игра 3 ДВЕРИ (только админ)\n"
        "🎲 /duel - дуэль на кубиках 1v1\n"
        "📖 /help - правила"
    )


@bot.message_handler(commands=['help'])
def show_rules(message):
    bot.reply_to(
        message,
        "ПРАВИЛА:\n\n"
        "3 ДВЕРИ:\n"
        "- Админ запускает /start_game\n"
        "- Игроки присоединяются кнопкой\n"
        "- 2 двери безопасные, 1 опасная (65% смерть)\n"
        "- Опасная дверь меняется каждый раунд\n"
        "- 20 секунд на выбор\n"
        "- Финал: Камень-Ножницы-Бумага до 3 побед\n\n"
        "ДУЭЛЬ:\n"
        "- /duel - создать дуэль\n"
        "- Второй игрок присоединяется кнопкой\n"
        "- Каждый кидает /dice 3 раза\n"
        "- Бот считает сумму и объявляет победителя"
    )


# ================= ИГРА 3 ДВЕРИ =================

def game_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🚪 ПРИСОЕДИНИТЬСЯ", callback_data="join_game"),
        InlineKeyboardButton("▶️ НАЧАТЬ", callback_data="start_doors_game"),
        InlineKeyboardButton("⏹️ СТОП", callback_data="stop_doors_game")
    )
    return markup


@bot.message_handler(commands=['start_game'])
def start_game_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    try:
        admins = bot.get_chat_administrators(chat_id)
        is_admin = any(a.user.id == user_id for a in admins)
    except:
        bot.reply_to(message, "❌ Только в группе!")
        return
    
    if not is_admin:
        bot.reply_to(message, "👑 Только админ может запустить игру!")
        return
    
    if chat_id in games:
        bot.reply_to(message, "⚠️ Игра уже запущена!")
        return
    
    msg = bot.reply_to(message, "💰 Введите приз для победителя:")
    bot.register_next_step_handler(msg, set_doors_prize, chat_id, user_id)


def set_doors_prize(message, chat_id, admin_id):
    prize = message.text
    games[chat_id] = Game(chat_id, prize, admin_id)
    
    bot.send_message(
        chat_id,
        f"🚪 ИГРА 3 ДВЕРИ\n\n"
        f"🏆 Приз: {prize}\n"
        f"👥 Игроков: 0/30\n\n"
        f"❗ Нажмите ПРИСОЕДИНИТЬСЯ\n"
        f"💀 Опасная дверь убивает с шансом 65%\n\n"
        f"👑 Админ нажимает НАЧАТЬ",
        reply_markup=game_keyboard()
    )


@bot.callback_query_handler(func=lambda call: call.data == "join_game")
def join_doors_game(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    name = call.from_user.first_name
    
    if chat_id not in games:
        bot.answer_callback_query(call.id, "❌ Игра не запущена!")
        return
    
    game = games[chat_id]
    
    if user_id in game.players:
        bot.answer_callback_query(call.id, "❌ Вы уже в игре!")
        return
    
    if len(game.players) >= 30:
        bot.answer_callback_query(call.id, "❌ Мест нет!")
        return
    
    game.add_player(user_id, name)
    bot.answer_callback_query(call.id, f"✅ {name}, вы присоединились!")
    
    bot.edit_message_text(
        f"🚪 ИГРА 3 ДВЕРИ\n\n"
        f"🏆 Приз: {game.prize}\n"
        f"👥 Игроков: {len(game.players)}/30\n\n"
        f"❗ Нажмите ПРИСОЕДИНИТЬСЯ\n"
        f"💀 Опасная дверь убивает с шансом 65%\n\n"
        f"👑 Админ нажимает НАЧАТЬ",
        chat_id, call.message.message_id,
        reply_markup=game_keyboard()
    )


@bot.callback_query_handler(func=lambda call: call.data == "start_doors_game")
def start_doors_game(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    if chat_id not in games:
        bot.answer_callback_query(call.id, "❌ Нет игры!")
        return
    
    game = games[chat_id]
    
    try:
        admins = bot.get_chat_administrators(chat_id)
        is_admin = any(a.user.id == user_id for a in admins)
    except:
        is_admin = False
    
    if not is_admin:
        bot.answer_callback_query(call.id, "👑 Только админ!", show_alert=True)
        return
    
    if len(game.players) < 2:
        bot.answer_callback_query(call.id, "❌ Нужно минимум 2 игрока!", show_alert=True)
        return
    
    bot.answer_callback_query(call.id, "✅ Игра начинается!")
    bot.send_message(chat_id, f"🚪 ИГРА НАЧИНАЕТСЯ!\n👥 {len(game.players)} участников\n🏆 Приз: {game.prize}")
    time.sleep(2)
    start_doors_round(chat_id, game)


@bot.callback_query_handler(func=lambda call: call.data == "stop_doors_game")
def stop_doors_game(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    try:
        admins = bot.get_chat_administrators(chat_id)
        is_admin = any(a.user.id == user_id for a in admins)
    except:
        is_admin = False
    
    if not is_admin:
        bot.answer_callback_query(call.id, "👑 Только админ!", show_alert=True)
        return
    
    if chat_id in games:
        del games[chat_id]
        bot.answer_callback_query(call.id, "⏹️ Игра остановлена!")
        bot.send_message(chat_id, "🛑 Игра остановлена админом!")


def start_doors_round(chat_id, game):
    game.choosing_phase = True
    game.choices = {}
    game.random_dead_door()
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🚪 ДВЕРЬ 1", callback_data="door_1"),
        InlineKeyboardButton("🚪 ДВЕРЬ 2", callback_data="door_2"),
        InlineKeyboardButton("🚪 ДВЕРЬ 3", callback_data="door_3")
    )
    
    alive = game.get_alive_players()
    players_text = "\n".join([f"👤 {data['name']}" for data in alive.values()])
    
    msg = bot.send_message(
        chat_id,
        f"🔴 РАУНД {game.round}\n\n"
        f"🚪 Выберите дверь!\n\n"
        f"Живые ({len(alive)}):\n{players_text}\n\n"
        f"⏰ 20 секунд\n████████████████████",
        reply_markup=markup
    )
    
    def timer():
        for seconds in range(20, 0, -1):
            if not game.choosing_phase:
                return
            try:
                progress = "█" * (20 - seconds) + "░" * seconds
                bot.edit_message_text(
                    f"🔴 РАУНД {game.round}\n\n"
                    f"🚪 Выберите дверь!\n\n"
                    f"Живые ({len(alive)}):\n{players_text}\n\n"
                    f"⏰ {seconds} сек\n{progress}",
                    chat_id, msg.message_id,
                    reply_markup=markup
                )
            except:
                pass
            time.sleep(1)
        
        if game.choosing_phase:
            for uid in game.get_alive_players():
                if uid not in game.choices:
                    game.choices[uid] = random.choice([1, 2, 3])
            game.choosing_phase = False
            process_doors_round(chat_id, game)
    
    threading.Thread(target=timer, daemon=True).start()


@bot.callback_query_handler(func=lambda call: call.data.startswith("door_"))
def choose_door(call):
    chat_id = call.message.chat.id
    uid = call.from_user.id
    door = int(call.data.split("_")[1])
    
    if chat_id not in games:
        bot.answer_callback_query(call.id, "❌ Ошибка!")
        return
    
    game = games[chat_id]
    
    if not game.choosing_phase:
        bot.answer_callback_query(call.id, "⏰ Время вышло!")
        return
    
    if uid in game.choices:
        bot.answer_callback_query(call.id, "❌ Уже выбрали!")
        return
    
    if uid not in game.get_alive_players():
        bot.answer_callback_query(call.id, "❌ Вы выбыли!")
        return
    
    game.choices[uid] = door
    bot.answer_callback_query(call.id, f"✅ Дверь {door}!")


def process_doors_round(chat_id, game):
    door_players = {1: [], 2: [], 3: []}
    for uid, door in game.choices.items():
        door_players[door].append(uid)
    
    dead = []
    msg = f"📊 РЕЗУЛЬТАТЫ РАУНДА {game.round}\n\n"
    
    for door in [1, 2, 3]:
        if door_players[door]:
            if door == game.dead_door:
                msg += f"🚪 ДВЕРЬ {door} 💀 ОПАСНАЯ\n"
                for uid in door_players[door]:
                    if random.random() < 0.65:
                        dead.append(uid)
                        msg += f"   💀 {game.players[uid]['name']} → погиб\n"
                    else:
                        msg += f"   ✅ {game.players[uid]['name']} → выжил\n"
            else:
                msg += f"🚪 ДВЕРЬ {door} ✅ БЕЗОПАСНАЯ\n"
                for uid in door_players[door]:
                    msg += f"   ✅ {game.players[uid]['name']} → выжил\n"
            msg += "\n"
    
    for uid in dead:
        game.players[uid]['alive'] = False
    
    alive = game.get_alive_players()
    msg += f"✅ ВЫЖИЛИ ({len(alive)}): " + ", ".join([p['name'] for p in alive.values()])
    
    bot.send_message(chat_id, msg)
    
    if len(alive) > 2:
        game.round += 1
        time.sleep(4)
        bot.send_message(chat_id, f"🔜 РАУНД {game.round}!\nОсталось {len(alive)} участников. Следующий раунд через 5 секунд...")
        time.sleep(5)
        start_doors_round(chat_id, game)
    elif len(alive) == 2:
        bot.send_message(chat_id, "🎯 ФИНАЛ! Камень, ножницы, бумага до 3 побед!")
        time.sleep(2)
        start_rps_final(chat_id, game, list(alive.keys()))
    elif len(alive) == 1:
        winner = list(alive.values())[0]['name']
        bot.send_message(chat_id, f"🏆 ПОБЕДИТЕЛЬ: {winner}!\n🎁 Приз: {game.prize}")
        del games[chat_id]
    else:
        bot.send_message(chat_id, f"💀 Все погибли! Приз {game.prize} невостребован.")
        del games[chat_id]


def start_rps_final(chat_id, game, players_ids):
    p1_id, p2_id = players_ids
    p1_name = game.players[p1_id]['name']
    p2_name = game.players[p2_id]['name']
    
    game.final_game = {
        'p1': {'id': p1_id, 'name': p1_name, 'score': 0},
        'p2': {'id': p2_id, 'name': p2_name, 'score': 0},
        'round': 1,
        'turn': p1_id
    }
    
    bot.send_message(chat_id, f"🎮 ФИНАЛ: КАМЕНЬ, НОЖНИЦЫ, БУМАГА!\n\n{p1_name} VS {p2_name}\nДо 3 побед!\n\n🎯 Начинает {p1_name}!")
    ask_rps(chat_id, game, p1_id)


def ask_rps(chat_id, game, user_id):
    name = game.players[user_id]['name']
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("✊ КАМЕНЬ", callback_data="rps_rock"),
        InlineKeyboardButton("✌️ НОЖНИЦЫ", callback_data="rps_scissors"),
        InlineKeyboardButton("🖐️ БУМАГА", callback_data="rps_paper")
    )
    bot.send_message(chat_id, f"🎮 {name}, ваш ход!", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith("rps_"))
def handle_rps_choice(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    if chat_id not in games:
        bot.answer_callback_query(call.id, "❌ Ошибка!")
        return
    
    game = games[chat_id]
    final = game.final_game
    
    if final['turn'] != user_id:
        bot.answer_callback_query(call.id, "❌ Не ваш ход!")
        return
    
    choice = call.data.split("_")[1]
    choice_ru = {"rock": "камень", "scissors": "ножницы", "paper": "бумага"}[choice]
    emoji = {"rock": "✊", "scissors": "✌️", "paper": "🖐️"}[choice]
    
    if user_id == final['p1']['id']:
        final['p1']['choice'] = choice_ru
        final['turn'] = final['p2']['id']
        bot.answer_callback_query(call.id, f"✅ {emoji} {choice_ru.upper()}!")
        ask_rps(chat_id, game, final['p2']['id'])
    else:
        final['p2']['choice'] = choice_ru
        bot.answer_callback_query(call.id, f"✅ {emoji} {choice_ru.upper()}!")
        
        p1c = final['p1']['choice']
        p2c = final['p2']['choice']
        p1 = final['p1']
        p2 = final['p2']
        
        if p1c == p2c:
            result = "🤝 НИЧЬЯ!"
        elif (p1c == "камень" and p2c == "ножницы") or \
             (p1c == "ножницы" and p2c == "бумага") or \
             (p1c == "бумага" and p2c == "камень"):
            p1['score'] += 1
            result = f"🎉 Очко получает {p1['name']}!"
        else:
            p2['score'] += 1
            result = f"🎉 Очко получает {p2['name']}!"
        
        bot.send_message(chat_id, f"📊 СЧЁТ: {p1['name']} {p1['score']} : {p2['score']} {p2['name']}\n{result}")
        
        if p1['score'] >= 3:
            bot.send_message(chat_id, f"🏆 ПОБЕДИТЕЛЬ: {p1['name']}!\n🎁 Приз: {game.prize}")
            del games[chat_id]
        elif p2['score'] >= 3:
            bot.send_message(chat_id, f"🏆 ПОБЕДИТЕЛЬ: {p2['name']}!\n🎁 Приз: {game.prize}")
            del games[chat_id]
        else:
            final['round'] += 1
            final['turn'] = final['p1']['id']
            time.sleep(2)
            bot.send_message(chat_id, f"🔜 РАУНД {final['round']}!\nСчёт: {p1['name']} {p1['score']} : {p2['score']} {p2['name']}\nНачинает {p1['name']}!")
            ask_rps(chat_id, game, final['p1']['id'])


# ================= ДУЭЛЬ =================

def duel_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎲 ПРИСОЕДИНИТЬСЯ", callback_data="join_duel"),
        InlineKeyboardButton("❌ ОТМЕНА", callback_data="cancel_duel")
    )
    return markup


def duel_control_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🎲 НАЧАТЬ ДУЭЛЬ", callback_data="start_duel"),
        InlineKeyboardButton("❌ ОТМЕНА", callback_data="cancel_duel")
    )
    return markup


@bot.message_handler(commands=['duel'])
def create_duel(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    if chat_id in duels:
        bot.send_message(chat_id, "⚠️ В этом чате уже есть активная дуэль!")
        return
    
    msg = bot.send_message(chat_id, "💰 Введите приз для победителя:")
    bot.register_next_step_handler(msg, set_duel_prize, chat_id, user_id, user_name)


def set_duel_prize(message, chat_id, creator_id, creator_name):
    prize = message.text
    duel = Duel(creator_id, creator_name, prize)
    duels[chat_id] = duel
    
    bot.send_message(
        chat_id,
        f"🎲 ДУЭЛЬ\n\n"
        f"🏆 Приз: {prize}\n"
        f"👤 Создатель: {creator_name}\n\n"
        f"📖 Правила:\n"
        f"• Каждый кидает /dice 3 раза\n"
        f"• Бот считает сумму\n"
        f"• Победитель — у кого больше\n\n"
        f"⏰ 60 секунд на поиск соперника!\n"
        f"👇 Нажмите ПРИСОЕДИНИТЬСЯ",
        reply_markup=duel_keyboard()
    )
    
    def timer():
        time.sleep(60)
        if chat_id in duels and not duels[chat_id].started:
            del duels[chat_id]
            bot.send_message(chat_id, "⏰ Время вышло! Дуэль отменена.")
    
    threading.Thread(target=timer, daemon=True).start()


@bot.callback_query_handler(func=lambda call: call.data == "join_duel")
def join_duel(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    user_name = call.from_user.first_name
    
    if chat_id not in duels:
        bot.answer_callback_query(call.id, "❌ Нет дуэли!")
        return
    
    duel = duels[chat_id]
    
    if duel.started:
        bot.answer_callback_query(call.id, "❌ Дуэль уже началась!")
        return
    
    if user_id == duel.creator_id:
        bot.answer_callback_query(call.id, "❌ Вы создали дуэль!")
        return
    
    if duel.player2_id:
        bot.answer_callback_query(call.id, "❌ Мест нет!")
        return
    
    duel.player2_id = user_id
    duel.player2_name = user_name
    bot.answer_callback_query(call.id, f"✅ {user_name}, вы присоединились!")
    
    bot.edit_message_text(
        f"🎲 ДУЭЛЬ\n\n"
        f"🏆 Приз: {duel.prize}\n"
        f"👤 {duel.creator_name} VS 👤 {duel.player2_name}\n\n"
        f"✅ Оба игрока собрались!\n"
        f"🎯 Нажмите НАЧАТЬ ДУЭЛЬ (может любой)",
        chat_id, call.message.message_id,
        reply_markup=duel_control_keyboard()
    )


@bot.callback_query_handler(func=lambda call: call.data == "start_duel")
def start_duel(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    if chat_id not in duels:
        bot.answer_callback_query(call.id, "❌ Нет дуэли!")
        return
    
    duel = duels[chat_id]
    
    if duel.started:
        bot.answer_callback_query(call.id, "❌ Уже началась!")
        return
    
    if user_id not in [duel.creator_id, duel.player2_id]:
        bot.answer_callback_query(call.id, "❌ Вы не участник!")
        return
    
    duel.started = True
    duel.scores = {duel.creator_id: [], duel.player2_id: []}
    duel.roll_count = {duel.creator_id: 0, duel.player2_id: 0}
    duel.current_turn = duel.creator_id
    
    bot.answer_callback_query(call.id, "🎲 Дуэль началась!")
    
    bot.edit_message_text(
        f"🎲 ДУЭЛЬ НАЧАЛАСЬ!\n\n"
        f"🏆 Приз: {duel.prize}\n"
        f"👤 {duel.creator_name} VS 👤 {duel.player2_name}\n\n"
        f"📋 Как играть:\n"
        f"• Каждый кидает /dice 3 раза\n"
        f"• Бот сам считает сумму\n\n"
        f"🎯 ПЕРВЫЙ ХОД: {duel.creator_name}!\n"
        f"👇 Отправьте /dice",
        chat_id, call.message.message_id
    )


@bot.callback_query_handler(func=lambda call: call.data == "cancel_duel")
def cancel_duel(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    if chat_id not in duels:
        bot.answer_callback_query(call.id, "❌ Нет дуэли!")
        return
    
    duel = duels[chat_id]
    
    if user_id not in [duel.creator_id, duel.player2_id]:
        bot.answer_callback_query(call.id, "❌ Вы не участник!")
        return
    
    del duels[chat_id]
    bot.answer_callback_query(call.id, "✅ Дуэль отменена!")
    bot.edit_message_text("❌ Дуэль отменена.", chat_id, call.message.message_id)


@bot.message_handler(func=lambda message: True)
def handle_dice_in_duel(message):
    chat_id = message.chat.id
    
    if chat_id not in duels:
        return
    
    duel = duels[chat_id]
    
    if not duel.started:
        return
    
    user_id = message.from_user.id
    
    if user_id not in [duel.creator_id, duel.player2_id]:
        return
    
    if duel.current_turn != user_id:
        other = duel.creator_name if user_id == duel.player2_id else duel.player2_name
        bot.reply_to(message, f"❌ Сейчас ход {other}! Дождитесь.")
        return
    
    if not message.dice or message.dice.emoji != "🎲":
        bot.reply_to(message, f"❌ {message.from_user.first_name}, это не кубик!\n🎲 Отправьте /dice")
        return
    
    roll = message.dice.value
    player_name = duel.creator_name if user_id == duel.creator_id else duel.player2_name
    roll_num = duel.roll_count[user_id] + 1
    
    duel.scores[user_id].append(roll)
    duel.roll_count[user_id] = roll_num
    total = sum(duel.scores[user_id])
    
    bot.send_message(chat_id, f"🎲 {player_name} бросок #{roll_num}: {roll}\n📊 Сумма: {total}")
    
    if duel.roll_count[user_id] >= 3:
        other_id = duel.creator_id if user_id == duel.player2_id else duel.player2_id
        
        if duel.roll_count[other_id] >= 3:
            score1 = sum(duel.scores[duel.creator_id])
            score2 = sum(duel.scores[duel.player2_id])
            
            if score1 > score2:
                winner = duel.creator_name
                result = f"🏆 ПОБЕДИТЕЛЬ: {winner}! 🏆"
            elif score2 > score1:
                winner = duel.player2_name
                result = f"🏆 ПОБЕДИТЕЛЬ: {winner}! 🏆"
            else:
                result = "🤝 НИЧЬЯ!"
            
            bot.send_message(
                chat_id,
                f"🎲 ИТОГ ДУЭЛИ\n\n"
                f"{duel.creator_name}: {score1}\n"
                f"{duel.player2_name}: {score2}\n\n"
                f"{result}\n"
                f"🎁 Приз: {duel.prize}"
            )
            del duels[chat_id]
            return
        else:
            duel.current_turn = other_id
            other_name = duel.creator_name if other_id == duel.creator_id else duel.player2_name
            bot.send_message(
                chat_id,
                f"✅ {player_name} завершил! Итог: {total}\n\n"
                f"🎯 ТЕПЕРЬ ХОД {other_name}!\n👇 Отправьте /dice"
            )
    else:
        bot.send_message(
            chat_id,
            f"🎲 {player_name}, осталось бросков: {3 - duel.roll_count[user_id]}\n👇 Отправьте /dice"
        )


@bot.message_handler(commands=['stop_game'])
def stop_game_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    try:
        admins = bot.get_chat_administrators(chat_id)
        is_admin = any(a.user.id == user_id for a in admins)
    except:
        bot.reply_to(message, "❌ Только в группе!")
        return
    
    if not is_admin:
        bot.reply_to(message, "👑 Только админ!")
        return
    
    if chat_id in games:
        del games[chat_id]
        bot.reply_to(message, "⏹️ Игра остановлена!")
    else:
        bot.reply_to(message, "❌ Нет активной игры!")


def run_bot():
    register_commands()
    print("🚀 Бот запущен!")
    bot.remove_webhook()
    time.sleep(1)
    bot.infinity_polling(timeout=30, long_polling_timeout=20)


@app.route('/')
def home():
    return "Бот работает", 200


@app.route('/health')
def health():
    return "OK", 200


if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
