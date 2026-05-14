import os
import threading
import time
import random
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask

# ================= ТОКЕН БОТА =================
TOKEN = "8598717015:AAGhbHPy-C9VTkcYb2XSyrJ3a_i83JNojf8"

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=10)
app = Flask(__name__)

# ================= ХРАНИЛИЩЕ ИГР =================
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
        self.timer_thread = None
        self.final_game = None
        self.dead_room = None
        self.game_active = True
        
    def add_player(self, user_id, name):
        if user_id not in self.players and len(self.players) < 30:
            self.players[user_id] = {'name': name, 'alive': True}
            return True
        return False
    
    def get_alive_players(self):
        return {uid: data for uid, data in self.players.items() if data['alive']}
    
    def random_dead_room(self):
        self.dead_room = random.choice([1, 2, 3])
        return self.dead_room


class Duel:
    def __init__(self, creator_id, creator_name):
        self.creator_id = creator_id
        self.creator_name = creator_name
        self.player2_id = None
        self.player2_name = None
        self.started = False
        self.scores = {}
        self.roll_count = {}
        self.current_turn = None
        self.message_id = None


# ========== РЕГИСТРАЦИЯ КОМАНД ==========
def register_commands():
    try:
        commands = [
            BotCommand("start", "🏠 Начать работу с ботом"),
            BotCommand("help", "📖 Правила игры"),
            BotCommand("duel", "🎲 Создать дуэль 1v1"),
            BotCommand("start_game", "🎮 Запустить групповую игру (админ)"),
            BotCommand("stop_game", "⏹️ Остановить игру (админ)"),
        ]
        bot.delete_my_commands()
        bot.set_my_commands(commands)
        print("✅ Команды зарегистрированы!")
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")


# ================= КОМАНДЫ =================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🤖 **Игровой бот**\n\n"
                 "🎮 **Команды:**\n"
                 "• `/duel` - создать дуэль 1v1 (может любой)\n"
                 "• `/start_game` - запустить групповую игру (только админ)\n"
                 "• `/stop_game` - остановить игру (админ)\n"
                 "• `/help` - правила игры\n\n"
                 "🎲 **Кратко:**\n"
                 "Дуэль — кидайте кубик 3 раза, кто наберёт больше очков — победил!",
                 parse_mode="Markdown")


@bot.message_handler(commands=['help'])
def show_rules(message):
    rules = """
📖 **ПРАВИЛА ИГРЫ** 📖

🎲 **ДУЭЛЬ 1v1:**
• Каждый игрок кидает кубик **3 раза**
• После броска нажмите на кнопку с выпавшим числом (1-6)
• Бот автоматически считает сумму ваших очков
• **Победитель:** у кого сумма очков больше!
• Начать дуэль может **ЛЮБОЙ** игрок

🔄 **Ничья:** объявляется ничья

👑 **ГРУППОВАЯ ИГРА (КОМНАТЫ):**
• Запустить может **ТОЛЬКО АДМИН** чата командой `/start_game`
• Админ указывает приз
• Игроки присоединяются кнопкой
• Каждый раунд выбирается комната (1, 2 или 3)
• Одна комната случайно становится **ОПАСНОЙ** (50% смерть)
• Остальные комнаты безопасные
• Опасная комната **МЕНЯЕТСЯ** каждый раунд
• На выбор комнаты — **20 секунд**
• Выжившие проходят дальше
• **ФИНАЛ:** Камень, ножницы, бумага до 3 побед

🏆 **Победитель** получает приз!

💡 **Вопросы?** Просто попробуй игру!
"""
    bot.reply_to(message, rules, parse_mode="Markdown")


# ================= ДУЭЛИ (МОЖЕТ ЛЮБОЙ) =================
@bot.message_handler(commands=['duel'])
def create_duel(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    if chat_id in duels:
        bot.send_message(chat_id, "⚠️ В этом чате уже есть активная дуэль!")
        return
    
    duel = Duel(user_id, user_name)
    duels[chat_id] = duel
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎲 ПРИСОЕДИНИТЬСЯ", callback_data="join_duel"))
    
    bot.send_message(chat_id, f"🎲 **ДУЭЛЬ**\n\n"
                     f"📖 **ПРАВИЛА ДУЭЛИ:**\n"
                     f"• Каждый кидает кубик 3 раза\n"
                     f"• Нажимайте на кнопку с выпавшим числом (1-6)\n"
                     f"• Победитель — у кого больше сумма очков!\n\n"
                     f"👤 Создатель: {user_name}\n"
                     f"👥 Ожидание второго игрока...\n\n"
                     f"❗ Нажмите **«ПРИСОЕДИНИТЬСЯ»**",
                     reply_markup=markup, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data == "join_duel")
def join_duel(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    user_name = call.from_user.first_name
    
    if chat_id not in duels:
        bot.answer_callback_query(call.id, "❌ Нет активной дуэли!")
        return
    
    duel = duels[chat_id]
    
    if duel.started:
        bot.answer_callback_query(call.id, "❌ Дуэль уже началась!")
        return
    
    if user_id == duel.creator_id:
        bot.answer_callback_query(call.id, "❌ Вы создали дуэль! Ожидайте второго игрока.")
        return
    
    if duel.player2_id is not None:
        bot.answer_callback_query(call.id, "❌ Мест нет!")
        return
    
    duel.player2_id = user_id
    duel.player2_name = user_name
    bot.answer_callback_query(call.id, f"✅ {user_name}, вы присоединились!")
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🎲 НАЧАТЬ ДУЭЛЬ", callback_data="start_duel"),
        InlineKeyboardButton("❌ ОТМЕНА", callback_data="cancel_duel")
    )
    
    bot.edit_message_text(f"🎲 **ДУЭЛЬ**\n\n"
                         f"📖 **ПРАВИЛА:** 3 броска, сумма очков\n\n"
                         f"👤 {duel.creator_name} VS 👤 {duel.player2_name}\n\n"
                         f"✅ Оба собрались!\n"
                         f"🎯 Нажмите **«НАЧАТЬ ДУЭЛЬ»** (может любой игрок)",
                         chat_id, call.message.message_id,
                         reply_markup=markup, parse_mode="Markdown")


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
    
    # Может начать ЛЮБОЙ из двух игроков (создатель или присоединившийся)
    if user_id != duel.creator_id and user_id != duel.player2_id:
        bot.answer_callback_query(call.id, "❌ Вы не участник дуэли!")
        return
    
    duel.started = True
    duel.scores = {duel.creator_id: [], duel.player2_id: []}
    duel.roll_count = {duel.creator_id: 0, duel.player2_id: 0}
    duel.current_turn = duel.creator_id
    
    bot.answer_callback_query(call.id, "🎲 Начинаем!")
    
    markup = InlineKeyboardMarkup(row_width=6)
    buttons = [InlineKeyboardButton(f"🎲 {i}", callback_data=f"roll_{i}") for i in range(1, 7)]
    markup.add(*buttons)
    
    bot.edit_message_text(f"🎲 **ДУЭЛЬ**\n\n"
                         f"👤 {duel.creator_name} VS {duel.player2_name}\n\n"
                         f"📋 **Правила:** 3 броска, сумма очков\n\n"
                         f"🎯 **Ход {duel.creator_name}!**\n👇 Нажмите на выпавшее число:",
                         chat_id, call.message.message_id,
                         reply_markup=markup, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data.startswith("roll_"))
def handle_roll(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    roll_value = int(call.data.split("_")[1])
    
    if chat_id not in duels:
        bot.answer_callback_query(call.id, "❌ Нет дуэли!")
        return
    
    duel = duels[chat_id]
    
    if not duel.started:
        bot.answer_callback_query(call.id, "❌ Не началась!")
        return
    
    if duel.current_turn != user_id:
        other = duel.creator_name if user_id == duel.player2_id else duel.player2_name
        bot.answer_callback_query(call.id, f"❌ Сейчас ход {other}!")
        return
    
    duel.scores[user_id].append(roll_value)
    duel.roll_count[user_id] += 1
    current_sum = sum(duel.scores[user_id])
    player_name = duel.creator_name if user_id == duel.creator_id else duel.player2_name
    
    bot.answer_callback_query(call.id, f"✅ Бросок #{duel.roll_count[user_id]}: {roll_value}")
    
    markup = InlineKeyboardMarkup(row_width=6)
    buttons = [InlineKeyboardButton(f"🎲 {i}", callback_data=f"roll_{i}") for i in range(1, 7)]
    markup.add(*buttons)
    
    if duel.roll_count[user_id] >= 3:
        other_id = duel.creator_id if user_id == duel.player2_id else duel.player2_id
        other_name = duel.creator_name if user_id == duel.player2_id else duel.player2_name
        
        if duel.roll_count[other_id] >= 3:
            score1 = sum(duel.scores[duel.creator_id])
            score2 = sum(duel.scores[duel.player2_id])
            result = f"🎲 **ИТОГ ДУЭЛИ**\n\n👤 {duel.creator_name}: **{score1}**\n👤 {duel.player2_name}: **{score2}**\n\n"
            if score1 > score2:
                result += f"🏆 **ПОБЕДИТЕЛЬ: {duel.creator_name}!** 🏆"
            elif score2 > score1:
                result += f"🏆 **ПОБЕДИТЕЛЬ: {duel.player2_name}!** 🏆"
            else:
                result += f"🤝 **НИЧЬЯ!**"
            bot.send_message(chat_id, result, parse_mode="Markdown")
            del duels[chat_id]
            return
        else:
            duel.current_turn = other_id
            bot.send_message(chat_id, f"✅ **{player_name}** завершил броски!\n📊 Сумма: **{current_sum}**\n\n🎯 **Ход {other_name}!**\n👇 Нажмите на выпавшее число:",
                             reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, f"🎲 **{player_name}**, бросок #{duel.roll_count[user_id]}!\n📊 Текущая сумма: **{current_sum}**\n⏰ Осталось: {3 - duel.roll_count[user_id]}\n\n👇 Ваш следующий бросок:",
                         reply_markup=markup, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data == "cancel_duel")
def cancel_duel(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    if chat_id not in duels:
        bot.answer_callback_query(call.id, "❌ Нет дуэли!")
        return
    
    duel = duels[chat_id]
    
    # Отменить может любой участник (создатель или присоединившийся)
    if user_id != duel.creator_id and user_id != duel.player2_id:
        bot.answer_callback_query(call.id, "❌ Вы не участник дуэли!")
        return
    
    del duels[chat_id]
    bot.answer_callback_query(call.id, "✅ Отменено!")
    bot.edit_message_text("❌ **Дуэль отменена.**", chat_id, call.message.message_id, parse_mode="Markdown")


# ================= ГРУППОВАЯ ИГРА (ТОЛЬКО АДМИНЫ) =================
@bot.message_handler(commands=['start_game'])
def start_game_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Проверка админа
    try:
        admin_list = bot.get_chat_administrators(chat_id)
        is_admin = any(admin.user.id == user_id for admin in admin_list)
    except:
        bot.reply_to(message, "❌ Эту команду можно использовать только в группе!")
        return
    
    if not is_admin:
        bot.reply_to(message, "❌ Только администратор чата может запустить групповую игру!")
        return
    
    if chat_id in games:
        bot.reply_to(message, "⚠️ Игра уже запущена в этом чате!")
        return
    
    msg = bot.reply_to(message, "💰 **Введите приз для победителя:**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, set_prize, chat_id, user_id)


@bot.message_handler(commands=['stop_game'])
def stop_game_command(message):
    chat_id = message.chat.id
    
    if chat_id not in games:
        bot.reply_to(message, "❌ Нет активной игры!")
        return
    
    game = games[chat_id]
    user_id = message.from_user.id
    
    try:
        admin_list = bot.get_chat_administrators(chat_id)
        is_admin = any(admin.user.id == user_id for admin in admin_list)
    except:
        is_admin = (user_id == game.admin_id)
    
    if not is_admin:
        bot.reply_to(message, "❌ Только администратор чата может остановить игру!")
        return
    
    del games[chat_id]
    bot.reply_to(message, "⏹️ **Групповая игра остановлена!**")


def set_prize(message, chat_id, admin_id):
    prize = message.text
    games[chat_id] = Game(chat_id, prize, admin_id)
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🚪 ПРИСОЕДИНИТЬСЯ", callback_data="join_game"),
        InlineKeyboardButton("▶️ НАЧАТЬ ИГРУ", callback_data="start_game_rooms"),
        InlineKeyboardButton("⏹️ СТОП", callback_data="admin_stop_game")
    )
    
    bot.send_message(chat_id, f"🎮 **ГРУППОВАЯ ИГРА СОЗДАНА!**\n\n🏆 Приз: {prize}\n👥 Игроков: 0/30\n\n⏰ На выбор комнаты - 20 секунд!\n👑 Управлять игрой может только админ!",
                     reply_markup=markup, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data == "join_game")
def join_game(call):
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
        bot.answer_callback_query(call.id, "❌ Мест больше нет!")
        return
    
    game.add_player(user_id, name)
    bot.answer_callback_query(call.id, f"✅ {name}, вы присоединились!")
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🚪 ПРИСОЕДИНИТЬСЯ", callback_data="join_game"),
        InlineKeyboardButton("▶️ НАЧАТЬ ИГРУ", callback_data="start_game_rooms"),
        InlineKeyboardButton("⏹️ СТОП", callback_data="admin_stop_game")
    )
    
    bot.edit_message_text(f"🎮 **ГРУППОВАЯ ИГРА**\n\n🏆 Приз: {game.prize}\n👥 Игроков: {len(game.players)}/30\n\n⏰ На выбор комнаты - 20 секунд!\n👑 Управляет админ",
                          chat_id, call.message.message_id,
                          reply_markup=markup, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data == "start_game_rooms")
def start_rooms(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    bot.answer_callback_query(call.id, "✅ Игра начинается!")
    
    if chat_id not in games:
        return
    
    game = games[chat_id]
    
    # Проверка админа (только админ может начать групповую игру)
    try:
        admin_list = bot.get_chat_administrators(chat_id)
        is_admin = any(admin.user.id == user_id for admin in admin_list)
    except:
        is_admin = (user_id == game.admin_id)
    
    if not is_admin:
        bot.send_message(chat_id, "❌ Только администратор чата может начать групповую игру!")
        return
    
    if len(game.players) < 2:
        bot.send_message(chat_id, "❌ Нужно минимум 2 игрока!")
        return
    
    bot.send_message(chat_id, f"🎮 **ГРУППОВАЯ ИГРА НАЧИНАЕТСЯ!**\n👥 Участников: {len(game.players)}\n🏆 Приз: {game.prize}",
                     parse_mode="Markdown")
    time.sleep(2)
    start_round(chat_id, game)


def start_round(chat_id, game):
    game.choosing_phase = True
    game.choices = {}
    game.random_dead_room()
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🚪 КОМНАТА 1", callback_data="room_1"),
        InlineKeyboardButton("🚪 КОМНАТА 2", callback_data="room_2"),
        InlineKeyboardButton("🚪 КОМНАТА 3", callback_data="room_3")
    )
    
    alive = game.get_alive_players()
    players_text = "\n".join([f"👤 {data['name']}" for data in alive.values()])
    
    bot.send_message(chat_id, f"🔴 **РАУНД {game.round}**\n\n🎲 Выберите комнату!\n\n👥 Живые ({len(alive)}):\n{players_text}\n\n⏰ **20 секунд на выбор!**",
                     reply_markup=markup, parse_mode="Markdown")
    
    def timer_and_process():
        time.sleep(20)
        if game.choosing_phase:
            alive = game.get_alive_players()
            for uid in alive:
                if uid not in game.choices:
                    game.choices[uid] = random.choice([1, 2, 3])
            game.choosing_phase = False
            process_round(chat_id, game)
    
    threading.Thread(target=timer_and_process, daemon=True).start()


@bot.callback_query_handler(func=lambda call: call.data.startswith("room_"))
def choose_room(call):
    chat_id = call.message.chat.id
    uid = call.from_user.id
    room = int(call.data.split("_")[1])
    
    if chat_id not in games:
        bot.answer_callback_query(call.id, "❌ Игра не найдена!")
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
    
    game.choices[uid] = room
    bot.answer_callback_query(call.id, f"✅ Комната {room}!")


def process_round(chat_id, game):
    room_players = {1: [], 2: [], 3: []}
    for uid, room in game.choices.items():
        room_players[room].append(uid)
    
    dead = []
    msg = f"📊 **РЕЗУЛЬТАТЫ РАУНДА {game.round}**\n\n"
    
    for room in [1, 2, 3]:
        if room_players[room]:
            if room == game.dead_room:
                msg += f"🚪 **КОМНАТА {room}** ⚠️ ОПАСНАЯ\n"
                for uid in room_players[room]:
                    if random.random() < 0.5:
                        dead.append(uid)
                        msg += f"   💀 {game.players[uid]['name']} → погиб\n"
                    else:
                        msg += f"   ✅ {game.players[uid]['name']} → выжил\n"
            else:
                msg += f"🚪 **КОМНАТА {room}** ✅ БЕЗОПАСНАЯ\n"
                for uid in room_players[room]:
                    msg += f"   ✅ {game.players[uid]['name']} → выжил\n"
            msg += "\n"
    
    for uid in dead:
        game.players[uid]['alive'] = False
    
    alive = game.get_alive_players()
    msg += f"✅ **ВЫЖИЛИ ({len(alive)}):** " + ", ".join([p['name'] for p in alive.values()])
    bot.send_message(chat_id, msg, parse_mode="Markdown")
    
    if len(alive) > 2:
        game.round += 1
        time.sleep(4)
        bot.send_message(chat_id, f"🔜 **РАУНД {game.round}!**\nОсталось {len(alive)} участников.\n⏰ Следующий раунд через 5 секунд...")
        time.sleep(5)
        start_round(chat_id, game)
    elif len(alive) == 2:
        bot.send_message(chat_id, "🎯 **ФИНАЛ!**\nКамень, ножницы, бумага до 3 побед!")
        time.sleep(2)
        start_rps_final(chat_id, game, list(alive.keys()))
    elif len(alive) == 1:
        winner = list(alive.values())[0]['name']
        bot.send_message(chat_id, f"🏆 **ПОБЕДИТЕЛЬ: {winner}!** 🎁 Приз: {game.prize}")
        del games[chat_id]
    else:
        bot.send_message(chat_id, f"💀 Все погибли! Приз {game.prize} невостребован.")
        del games[chat_id]


# ================= ФИНАЛ КАМЕНЬ-НОЖНИЦЫ-БУМАГА =================
def start_rps_final(chat_id, game, players_ids):
    p1_id, p2_id = players_ids
    p1_name = game.players[p1_id]['name']
    p2_name = game.players[p2_id]['name']
    
    game.final_game = {
        'player1': {'id': p1_id, 'name': p1_name, 'score': 0},
        'player2': {'id': p2_id, 'name': p2_name, 'score': 0},
        'round': 1,
        'waiting_for': p1_id
    }
    
    bot.send_message(chat_id, f"🎮 **ФИНАЛ: КАМЕНЬ, НОЖНИЦЫ, БУМАГА!**\n\n👤 {p1_name} VS 👤 {p2_name}\n🏆 До 3 побед!\n\n🎯 Начинает {p1_name}!")
    ask_for_choice(chat_id, game, p1_id)


def ask_for_choice(chat_id, game, user_id):
    player_name = game.players[user_id]['name']
    
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("🗿 КАМЕНЬ", callback_data="rps_rock"),
        InlineKeyboardButton("✂️ НОЖНИЦЫ", callback_data="rps_scissors"),
        InlineKeyboardButton("📄 БУМАГА", callback_data="rps_paper")
    )
    bot.send_message(chat_id, f"🎮 **{player_name}**, ваш ход! Выберите:",
                     reply_markup=markup, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: call.data.startswith("rps_"))
def handle_rps(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    if chat_id not in games:
        bot.answer_callback_query(call.id, "❌ Игра не найдена!")
        return
    
    game = games[chat_id]
    final = game.final_game
    
    if final['waiting_for'] != user_id:
        bot.answer_callback_query(call.id, "❌ Не ваш ход!")
        return
    
    choice_map = {
        'rps_rock': 'камень',
        'rps_scissors': 'ножницы',
        'rps_paper': 'бумага'
    }
    choice = choice_map[call.data]
    
    if user_id == final['player1']['id']:
        final['player1']['choice'] = choice
        final['waiting_for'] = final['player2']['id']
        bot.answer_callback_query(call.id, f"✅ {choice.upper()}!")
        ask_for_choice(chat_id, game, final['player2']['id'])
    else:
        final['player2']['choice'] = choice
        bot.answer_callback_query(call.id, f"✅ {choice.upper()}!")
        
        p1 = final['player1']
        p2 = final['player2']
        
        if p1['choice'] == p2['choice']:
            result = "🤝 НИЧЬЯ!"
        elif (p1['choice'] == 'камень' and p2['choice'] == 'ножницы') or \
             (p1['choice'] == 'ножницы' and p2['choice'] == 'бумага') or \
             (p1['choice'] == 'бумага' and p2['choice'] == 'камень'):
            p1['score'] += 1
            result = f"🎉 Очко получает {p1['name']}!"
        else:
            p2['score'] += 1
            result = f"🎉 Очко получает {p2['name']}!"
        
        bot.send_message(chat_id, f"📊 **СЧЁТ:** {p1['name']} {p1['score']} : {p2['score']} {p2['name']}\n{result}", parse_mode="Markdown")
        
        if p1['score'] >= 3:
            bot.send_message(chat_id, f"🏆 **ПОБЕДИТЕЛЬ ФИНАЛА: {p1['name']}!** 🎁 Приз: {game.prize}")
            del games[chat_id]
        elif p2['score'] >= 3:
            bot.send_message(chat_id, f"🏆 **ПОБЕДИТЕЛЬ ФИНАЛА: {p2['name']}!** 🎁 Приз: {game.prize}")
            del games[chat_id]
        else:
            final['round'] += 1
            final['waiting_for'] = final['player1']['id']
            time.sleep(2)
            bot.send_message(chat_id, f"🔜 **РАУНД {final['round']}!**\nСчёт: {p1['name']} {p1['score']} : {p2['score']} {p2['name']}\nНачинает {p1['name']}!")
            ask_for_choice(chat_id, game, final['player1']['id'])


@bot.callback_query_handler(func=lambda call: call.data == "admin_stop_game")
def admin_stop_game(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    try:
        admin_list = bot.get_chat_administrators(chat_id)
        is_admin = any(admin.user.id == user_id for admin in admin_list)
    except:
        bot.answer_callback_query(call.id, "❌ Только в группе!", show_alert=True)
        return
    
    if not is_admin:
        bot.answer_callback_query(call.id, "❌ Только админ!", show_alert=True)
        return
    
    if chat_id not in games:
        bot.answer_callback_query(call.id, "❌ Нет активной игры!", show_alert=True)
        return
    
    del games[chat_id]
    bot.answer_callback_query(call.id, "⏹️ Игра остановлена!")
    bot.send_message(chat_id, "🛑 **Групповая игра остановлена админом!**")


# ================= ЗАПУСК =================
def run_bot():
    register_commands()
    print("🚀 Бот запускается...")
    bot.remove_webhook()
    time.sleep(1)
    bot.infinity_polling(timeout=30, long_polling_timeout=20)


@app.route('/')
def home():
    return "🤖 Бот работает!", 200


@app.route('/health')
def health():
    return "OK", 200


if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    print(f"🌐 Веб-сервер на порту {port}")
    app.run(host='0.0.0.0', port=port)
