import os
import threading
import time
import random
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask

# ================= ТОКЕН БОТА =================
TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    print("❌ Ошибка: Не найден TELEGRAM_TOKEN!")
    exit(1)

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=10)
app = Flask(__name__)

# ================= ХРАНИЛИЩЕ ИГР =================
games = {}
duels = {}

# ================= ПРЕМИУМ-СТИКЕРЫ =================
# ЗДЕСЬ ТЫ МЕНЯЕШЬ СТИКЕРЫ НА СВОИ!
# Как получить ID стикера: https://t.me/Stickers_Robot → /getsticker → перешли стикер
PREMIUM_STICKERS = {
    "welcome": "CAACAgIAAxkBAAEGI_VnCHmJYyRz3",      # Приветствие
    "victory": "CAACAgIAAxkBAAEGI_cnCHmKZxT4v",     # Победа
    "game_start": "CAACAgIAAxkBAAEGI_mnCHmNcRg0",   # Начало игры
    "death": "CAACAgIAAxkBAAEGI_enCHmLWb42",        # Смерть игрока
    "dice_roll": "CAACAgIAAxkBAAEGI_enCHmLWb42",    # Бросок кубика
    "duel_start": "CAACAgIAAxkBAAEGI_enCHmLWb42",   # Начало дуэли
}

def send_sticker(chat_id, sticker_key):
    """Отправляет премиум-стикер по ключу"""
    try:
        if sticker_key in PREMIUM_STICKERS:
            bot.send_sticker(chat_id, PREMIUM_STICKERS[sticker_key])
    except:
        pass  # Если стикер не найден — просто игнорируем

# ================= КЛАССЫ =================
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
        self.dead_door = None
        self.game_active = True
        
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
        self.created_at = time.time()
        self.timer_thread = None


# ========== РЕГИСТРАЦИЯ КОМАНД ==========
def register_commands():
    try:
        commands = [
            BotCommand("start", "🏠 Главное меню"),
            BotCommand("help", "📖 Правила игр"),
            BotCommand("duel", "🎲 Дуэль на кубиках 1v1"),
            BotCommand("start_game", "🚪 Игра «3 двери» (админ)"),
            BotCommand("stop_game", "⏹️ Остановить игру (админ)"),
            BotCommand("cancel_duel", "❌ Отменить дуэль"),
        ]
        bot.delete_my_commands()
        bot.set_my_commands(commands)
        print("✅ Команды зарегистрированы!")
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")


# ================= КОМАНДЫ =================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    send_sticker(message.chat.id, "welcome")
    
    welcome_text = (
        "✨ **ДОБРО ПОЖАЛОВАТЬ В ИГРОВОЙ БОТ!** ✨\n\n"
        "🎮 **Доступные игры:**\n"
        "• 🚪 **ИГРА «3 ДВЕРИ»** — командная игра (до 30 игроков)\n"
        "• 🎲 **ДУЭЛЬ** — 1v1 на кубиках\n\n"
        "📋 **Команды:**\n"
        "• `/duel` — создать дуэль\n"
        "• `/start_game` — запустить игру с дверьми (только админ)\n"
        "• `/stop_game` — остановить игру (админ)\n"
        "• `/help` — подробные правила\n\n"
        "💎 **Удачи в игре!** 💎"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")


@bot.message_handler(commands=['help'])
def show_rules(message):
    rules = (
        "📖 **ПРАВИЛА ИГР** 📖\n\n"
        "🚪 **ИГРА «3 ДВЕРИ»:**\n"
        "• Запускает **только админ** чата/канала\n"
        "• От **2 до 30 игроков**\n"
        "• Каждый раунд: **3 двери**, **2 безопасные**, **1 опасная**\n"
        "• **Опасная дверь** меняется каждый раунд случайно\n"
        "• Опасная дверь убивает с шансом **65%** 💀\n"
        "• На выбор — **20 секунд**, иначе автоназначение\n"
        "• **Финал:** Камень ✊, ножницы ✌️, бумага 🖐️ до **3 побед**\n"
        "• Победитель получает **приз от админа** 🏆\n\n"
        "🎲 **ДУЭЛЬ НА КУБИКАХ:**\n"
        "• Начать может **любой игрок**\n"
        "• На поиск соперника — **60 секунд** ⏰\n"
        "• Каждый делает **3 броска** кубика\n"
        "• **Сами кидаете кубик** командой `/dice`\n"
        "• Бот **следит за очередью** и считает очки\n"
        "• **Победитель** — у кого больше сумма очков\n"
        "• Приз выбирают **сами игроки**\n\n"
        "👑 **Команды:**\n"
        "• `/start_game` — запустить игру (админ)\n"
        "• `/stop_game` — остановить игру (админ)\n"
        "• `/duel` — создать дуэль\n"
        "• `/cancel_duel` — отменить дуэль\n"
        "• `/help` — это меню"
    )
    bot.reply_to(message, rules, parse_mode="Markdown")


# ================= ИГРА «3 ДВЕРИ» =================
def game_control_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("▶️ НАЧАТЬ ИГРУ ▶️", callback_data="start_game_rooms"),
        InlineKeyboardButton("⏹️ СТОП", callback_data="admin_stop_game")
    )
    return markup


def game_control_keyboard_with_join():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🚪 ПРИСОЕДИНИТЬСЯ 🚪", callback_data="join_game"),
        InlineKeyboardButton("▶️ НАЧАТЬ ИГРУ ▶️", callback_data="start_game_rooms"),
        InlineKeyboardButton("⏹️ СТОП", callback_data="admin_stop_game")
    )
    return markup


@bot.message_handler(commands=['start_game'])
def start_game_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    try:
        admin_list = bot.get_chat_administrators(chat_id)
        is_admin = any(admin.user.id == user_id for admin in admin_list)
    except:
        bot.reply_to(message, "❌ Эту команду можно использовать только в группе!")
        return
    
    if not is_admin:
        bot.reply_to(message, "👑 **Только администратор чата может запустить игру!**")
        return
    
    if chat_id in games:
        bot.reply_to(message, "⚠️ Игра уже запущена в этом чате!")
        return
    
    msg = bot.reply_to(message, "💰 **Введите приз для победителя:**\n\n💎 Например: «100 рублей» или «Пицца»")
    bot.register_next_step_handler(msg, set_prize, chat_id, user_id)


def set_prize(message, chat_id, admin_id):
    prize = message.text
    games[chat_id] = Game(chat_id, prize, admin_id)
    
    bot.send_message(
        chat_id,
        f"🚪 **ИГРА «3 ДВЕРИ» СОЗДАНА!** 🚪\n\n"
        f"🏆 **Приз:** {prize}\n"
        f"👥 **Игроков:** 0/30\n\n"
        f"❗ Нажмите **«ПРИСОЕДИНИТЬСЯ»**\n"
        f"⏰ На выбор двери — **20 секунд**\n"
        f"💀 Опасная дверь убивает с шансом **65%**\n\n"
        f"👑 Админ, нажмите **«НАЧАТЬ ИГРУ»** когда все собрались.",
        reply_markup=game_control_keyboard_with_join(),
        parse_mode="Markdown"
    )


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
    bot.answer_callback_query(call.id, f"✅ **{name}**, вы присоединились!")
    
    # Отправляем новое сообщение с актуальным количеством
    bot.send_message(
        chat_id,
        f"🚪 **ИГРА «3 ДВЕРИ»** 🚪\n\n"
        f"🏆 **Приз:** {game.prize}\n"
        f"👥 **Игроков:** {len(game.players)}/30\n\n"
        f"❗ Нажмите **«ПРИСОЕДИНИТЬСЯ»**\n"
        f"⏰ На выбор двери — **20 секунд**\n"
        f"💀 Опасная дверь убивает с шансом **65%**\n\n"
        f"👑 Админ, нажмите **«НАЧАТЬ ИГРУ»**",
        reply_markup=game_control_keyboard_with_join(),
        parse_mode="Markdown"
    )
    
    # Удаляем старое сообщение
    try:
        bot.delete_message(chat_id, call.message.message_id)
    except:
        pass


@bot.callback_query_handler(func=lambda call: call.data == "start_game_rooms")
def start_rooms(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    bot.answer_callback_query(call.id, "✅ Игра начинается!")
    
    if chat_id not in games:
        return
    
    game = games[chat_id]
    
    try:
        admin_list = bot.get_chat_administrators(chat_id)
        is_admin = any(admin.user.id == user_id for admin in admin_list)
    except:
        is_admin = (user_id == game.admin_id)
    
    if not is_admin:
        bot.send_message(chat_id, "👑 **Только администратор может начать игру!**")
        return
    
    if len(game.players) < 2:
        bot.send_message(chat_id, "❌ Нужно минимум **2 игрока** для начала игры!")
        return
    
    send_sticker(chat_id, "game_start")
    
    bot.send_message(
        chat_id,
        f"🚪 **ИГРА «3 ДВЕРИ» НАЧИНАЕТСЯ!** 🚪\n\n"
        f"👥 **Участников:** {len(game.players)}\n"
        f"🏆 **Приз:** {game.prize}\n\n"
        f"✨ **Удачи всем!** ✨",
        parse_mode="Markdown"
    )
    time.sleep(2)
    start_round(chat_id, game)


def start_round(chat_id, game):
    game.choosing_phase = True
    game.choices = {}
    dead_door = game.random_dead_door()
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🚪 ДВЕРЬ 1 🚪", callback_data="door_1"),
        InlineKeyboardButton("🚪 ДВЕРЬ 2 🚪", callback_data="door_2"),
        InlineKeyboardButton("🚪 ДВЕРЬ 3 🚪", callback_data="door_3")
    )
    
    alive = game.get_alive_players()
    players_text = "\n".join([f"👤 **{data['name']}**" for data in alive.values()])
    
    msg = bot.send_message(
        chat_id,
        f"🔴 **РАУНД {game.round}** 🔴\n\n"
        f"🚪 **Выберите дверь!**\n\n"
        f"👥 **Живые игроки ({len(alive)}):**\n{players_text}\n\n"
        f"⏰ **20 секунд на выбор!**\n"
        f"████████████████████",
        reply_markup=markup,
        parse_mode="Markdown"
    )
    
    def timer_and_process():
        for seconds in range(20, 0, -1):
            if not game.choosing_phase:
                return
            try:
                progress = "█" * (20 - seconds) + "░" * seconds
                bot.edit_message_text(
                    f"🔴 **РАУНД {game.round}** 🔴\n\n"
                    f"🚪 **Выберите дверь!**\n\n"
                    f"👥 **Живые игроки ({len(alive)}):**\n{players_text}\n\n"
                    f"⏰ **Осталось: {seconds} секунд**\n"
                    f"{progress}",
                    chat_id, msg.message_id,
                    reply_markup=markup,
                    parse_mode="Markdown"
                )
            except:
                pass
            time.sleep(1)
        
        if game.choosing_phase:
            alive_players = game.get_alive_players()
            auto_list = []
            for uid in alive_players:
                if uid not in game.choices:
                    door = random.choice([1, 2, 3])
                    game.choices[uid] = door
                    auto_list.append(game.players[uid]['name'])
            
            if auto_list:
                bot.send_message(
                    chat_id,
                    f"⏰ **Время вышло!**\nАвтоназначение для: {', '.join([f'**{name}**' for name in auto_list])}",
                    parse_mode="Markdown"
                )
            
            game.choosing_phase = False
            process_round(chat_id, game)
    
    threading.Thread(target=timer_and_process, daemon=True).start()


@bot.callback_query_handler(func=lambda call: call.data.startswith("door_"))
def choose_door(call):
    chat_id = call.message.chat.id
    uid = call.from_user.id
    door = int(call.data.split("_")[1])
    
    if chat_id not in games:
        bot.answer_callback_query(call.id, "❌ Игра не найдена!")
        return
    
    game = games[chat_id]
    
    if not game.choosing_phase:
        bot.answer_callback_query(call.id, "⏰ Время выбора вышло!")
        return
    
    if uid in game.choices:
        bot.answer_callback_query(call.id, "❌ Вы уже выбрали дверь!")
        return
    
    if uid not in game.get_alive_players():
        bot.answer_callback_query(call.id, "❌ Вы выбыли из игры!")
        return
    
    game.choices[uid] = door
    bot.answer_callback_query(call.id, f"✅ Вы выбрали **ДВЕРЬ {door}**!")


def process_round(chat_id, game):
    door_players = {1: [], 2: [], 3: []}
    for uid, door in game.choices.items():
        door_players[door].append(uid)
    
    dead = []
    msg = f"📊 **РЕЗУЛЬТАТЫ РАУНДА {game.round}** 📊\n\n"
    
    for door in [1, 2, 3]:
        if door_players[door]:
            if door == game.dead_door:
                msg += f"🚪 **ДВЕРЬ {door}** 💀 **ОПАСНАЯ** (65% смерть)\n"
                for uid in door_players[door]:
                    if random.random() < 0.65:
                        dead.append(uid)
                        msg += f"   💀 **{game.players[uid]['name']}** → погиб\n"
                        send_sticker(chat_id, "death")
                    else:
                        msg += f"   ✅ **{game.players[uid]['name']}** → выжил\n"
            else:
                msg += f"🚪 **ДВЕРЬ {door}** ✅ **БЕЗОПАСНАЯ**\n"
                for uid in door_players[door]:
                    msg += f"   ✅ **{game.players[uid]['name']}** → выжил\n"
            msg += "\n"
    
    for uid in dead:
        game.players[uid]['alive'] = False
    
    alive = game.get_alive_players()
    msg += f"✅ **ВЫЖИЛИ ({len(alive)}):** " + ", ".join([f"**{p['name']}**" for p in alive.values()])
    
    bot.send_message(chat_id, msg, parse_mode="Markdown")
    
    if len(alive) > 2:
        game.round += 1
        time.sleep(4)
        bot.send_message(
            chat_id,
            f"🔜 **РАУНД {game.round}!** 🔜\n"
            f"🔥 **Осталось {len(alive)} участников!**\n"
            f"⏰ Следующий раунд через 5 секунд...",
            parse_mode="Markdown"
        )
        time.sleep(5)
        start_round(chat_id, game)
    elif len(alive) == 2:
        bot.send_message(
            chat_id,
            "🎯 **ФИНАЛ!** 🎯\n"
            f"🔥 **Осталось 2 игрока!**\n\n"
            f"🏆 **Камень, ножницы, бумага!**\n"
            f"📋 Игра до **3 побед**\n"
            f"🔄 Ничьи не засчитываются",
            parse_mode="Markdown"
        )
        time.sleep(2)
        start_rps_final(chat_id, game, list(alive.keys()))
    elif len(alive) == 1:
        winner = list(alive.values())[0]['name']
        send_sticker(chat_id, "victory")
        bot.send_message(
            chat_id,
            f"🏆 **ПОБЕДИТЕЛЬ: {winner}!** 🏆\n"
            f"🎁 **Приз: {game.prize}**\n\n"
            f"✨ **Поздравляем!** ✨",
            parse_mode="Markdown"
        )
        del games[chat_id]
    else:
        bot.send_message(
            chat_id,
            f"💀 **Все игроки погибли!** 💀\n"
            f"🎁 Приз **{game.prize}** остаётся невостребованным.",
            parse_mode="Markdown"
        )
        del games[chat_id]


# ================= ФИНАЛ: КАМЕНЬ-НОЖНИЦЫ-БУМАГА =================
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
    
    bot.send_message(
        chat_id,
        f"🎮 **ФИНАЛ: КАМЕНЬ, НОЖНИЦЫ, БУМАГА!** 🎮\n\n"
        f"👤 **{p1_name}**  VS  👤 **{p2_name}**\n"
        f"🏆 **До 3 побед!**\n\n"
        f"🎯 **Начинает {p1_name}!**\n"
        f"✊ Камень   ✌️ Ножницы   🖐️ Бумага",
        parse_mode="Markdown"
    )
    ask_for_choice(chat_id, game, p1_id)


def ask_for_choice(chat_id, game, user_id):
    player_name = game.players[user_id]['name']
    
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("✊ КАМЕНЬ", callback_data="rps_rock"),
        InlineKeyboardButton("✌️ НОЖНИЦЫ", callback_data="rps_scissors"),
        InlineKeyboardButton("🖐️ БУМАГА", callback_data="rps_paper")
    )
    
    bot.send_message(
        chat_id,
        f"🎮 **{player_name}**, ваш ход!\n"
        f"✊ **Камень** | ✌️ **Ножницы** | 🖐️ **Бумага**",
        reply_markup=markup,
        parse_mode="Markdown"
    )


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
        bot.answer_callback_query(call.id, "❌ Сейчас не ваш ход!")
        return
    
    choice_map = {
        'rps_rock': 'камень',
        'rps_scissors': 'ножницы',
        'rps_paper': 'бумага'
    }
    choice = choice_map[call.data]
    choice_emoji = {'камень': '✊', 'ножницы': '✌️', 'бумага': '🖐️'}[choice]
    
    if user_id == final['player1']['id']:
        final['player1']['choice'] = choice
        final['waiting_for'] = final['player2']['id']
        bot.answer_callback_query(call.id, f"✅ Вы выбрали {choice_emoji} {choice.upper()}!")
        ask_for_choice(chat_id, game, final['player2']['id'])
    else:
        final['player2']['choice'] = choice
        bot.answer_callback_query(call.id, f"✅ Вы выбрали {choice_emoji} {choice.upper()}!")
        
        p1 = final['player1']
        p2 = final['player2']
        round_num = final['round']
        
        if p1['choice'] == p2['choice']:
            result = "🤝 **НИЧЬЯ!**"
            winner_name = None
        elif (p1['choice'] == 'камень' and p2['choice'] == 'ножницы') or \
             (p1['choice'] == 'ножницы' and p2['choice'] == 'бумага') or \
             (p1['choice'] == 'бумага' and p2['choice'] == 'камень'):
            p1['score'] += 1
            result = f"🎉 **Очко получает {p1['name']}!** 🎉"
            winner_name = p1['name']
        else:
            p2['score'] += 1
            result = f"🎉 **Очко получает {p2['name']}!** 🎉"
            winner_name = p2['name']
        
        bot.send_message(
            chat_id,
            f"📊 **РАУНД {round_num}**\n\n"
            f"{result}\n\n"
            f"📈 **СЧЁТ:**\n"
            f"👤 **{p1['name']}** — {p1['score']}\n"
            f"👤 **{p2['name']}** — {p2['score']}\n\n"
            f"🏆 **До победы:** {3 - p1['score']} и {3 - p2['score']} очков",
            parse_mode="Markdown"
        )
        
        if p1['score'] >= 3:
            send_sticker(chat_id, "victory")
            bot.send_message(
                chat_id,
                f"🏆 **ПОБЕДИТЕЛЬ ФИНАЛА: {p1['name']}!** 🏆\n"
                f"🎁 **Приз: {game.prize}**\n\n"
                f"✨ **Поздравляем с победой!** ✨",
                parse_mode="Markdown"
            )
            del games[chat_id]
        elif p2['score'] >= 3:
            send_sticker(chat_id, "victory")
            bot.send_message(
                chat_id,
                f"🏆 **ПОБЕДИТЕЛЬ ФИНАЛА: {p2['name']}!** 🏆\n"
                f"🎁 **Приз: {game.prize}**\n\n"
                f"✨ **Поздравляем с победой!** ✨",
                parse_mode="Markdown"
            )
            del games[chat_id]
        else:
            final['round'] += 1
            final['waiting_for'] = final['player1']['id']
            time.sleep(2)
            bot.send_message(
                chat_id,
                f"🔜 **РАУНД {final['round']}!** 🔜\n\n"
                f"📊 **Текущий счёт:**\n"
                f"👤 **{p1['name']}** — {p1['score']}\n"
                f"👤 **{p2['name']}** — {p2['score']}\n\n"
                f"🎯 **Начинает {p1['name']}!**",
                parse_mode="Markdown"
            )
            ask_for_choice(chat_id, game, final['player1']['id'])


# ================= ДУЭЛЬ НА КУБИКАХ (ИГРОКИ КИДАЮТ САМИ) =================
@bot.message_handler(commands=['duel'])
def create_duel(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    if chat_id in duels:
        bot.send_message(chat_id, "⚠️ В этом чате уже есть активная дуэль!")
        return
    
    msg = bot.send_message(chat_id, "💰 **Введите приз/ставку для победителя:**\n\n💎 Например: «Угощаю кофе» или «50 звезд»")
    bot.register_next_step_handler(msg, set_duel_prize, chat_id, user_id, user_name)


def set_duel_prize(message, chat_id, user_id, user_name):
    prize = message.text
    
    duel = Duel(user_id, user_name, prize)
    duels[chat_id] = duel
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎲 ПРИСОЕДИНИТЬСЯ", callback_data="join_duel"))
    
    bot.send_message(
        chat_id,
        f"🎲 **ДУЭЛЬ НА КУБИКАХ** 🎲\n\n"
        f"📖 **ПРАВИЛА:**\n"
        f"• Каждый игрок кидает кубик **3 раза**\n"
        f"• Используйте команду **/dice** или встроенный кубик\n"
        f"• **Победитель** — у кого больше сумма очков\n\n"
        f"🏆 **Приз:** {prize}\n"
        f"👤 **Создатель:** {user_name}\n\n"
        f"⏰ **60 секунд** на поиск соперника!\n"
        f"❗ Нажмите **«ПРИСОЕДИНИТЬСЯ»**",
        reply_markup=markup,
        parse_mode="Markdown"
    )
    
    def duel_timer():
        time.sleep(60)
        if chat_id in duels and not duels[chat_id].started:
            del duels[chat_id]
            bot.send_message(chat_id, "⏰ **Время вышло!** Дуэль отменена. Никто не присоединился.")
    
    timer_thread = threading.Thread(target=duel_timer)
    timer_thread.daemon = True
    timer_thread.start()
    duel.timer_thread = timer_thread


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
    
    bot.answer_callback_query(call.id, f"✅ **{user_name}**, вы присоединились!")
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🎲 НАЧАТЬ ДУЭЛЬ", callback_data="start_duel"),
        InlineKeyboardButton("❌ ОТМЕНА", callback_data="cancel_duel")
    )
    
    bot.edit_message_text(
        f"🎲 **ДУЭЛЬ НА КУБИКАХ** 🎲\n\n"
        f"📖 **ПРАВИЛА:**\n"
        f"• Каждый кидает кубик **3 раза** (команда `/dice`)\n"
        f"• Бот сам считает сумму и объявляет победителя\n\n"
        f"🏆 **Приз:** {duel.prize}\n"
        f"👤 **{duel.creator_name}** VS 👤 **{duel.player2_name}**\n\n"
        f"✅ **Оба игрока собрались!**\n"
        f"🎯 Нажмите **«НАЧАТЬ ДУЭЛЬ»**",
        chat_id, call.message.message_id,
        reply_markup=markup,
        parse_mode="Markdown"
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
    
    if user_id != duel.creator_id and user_id != duel.player2_id:
        bot.answer_callback_query(call.id, "❌ Вы не участник дуэли!")
        return
    
    duel.started = True
    duel.scores = {duel.creator_id: [], duel.player2_id: []}
    duel.roll_count = {duel.creator_id: 0, duel.player2_id: 0}
    duel.current_turn = duel.creator_id
    
    bot.answer_callback_query(call.id, "🎲 Дуэль началась!")
    send_sticker(chat_id, "duel_start")
    
    bot.edit_message_text(
        f"🎲 **ДУЭЛЬ НАЧАЛАСЬ!** 🎲\n\n"
        f"🏆 **Приз:** {duel.prize}\n"
        f"👤 **{duel.creator_name}** VS 👤 **{duel.player2_name}**\n\n"
        f"📋 **Правила:**\n"
        f"• Каждый кидает **3 раза** команду `/dice`\n"
        f"• Бот сам считает очки и объявляет победителя!\n\n"
        f"🎯 **Первый ход: {duel.creator_name}!**\n"
        f"👇 Отправьте **/dice** или нажмите на кубик в меню",
        chat_id, call.message.message_id,
        parse_mode="Markdown"
    )


@bot.message_handler(func=lambda message: message.chat.id in duels and duels[message.chat.id].started)
def handle_dice_rolls(message):
    """Обрабатывает броски кубиков в активной дуэли"""
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if chat_id not in duels:
        return
    
    duel = duels[chat_id]
    
    if not duel.started:
        return
    
    # Проверяем, что игрок участвует в дуэли
    if user_id not in [duel.creator_id, duel.player2_id]:
        return
    
    # Проверяем, чей сейчас ход
    if duel.current_turn != user_id:
        other_name = duel.creator_name if user_id == duel.player2_id else duel.player2_name
        bot.reply_to(message, f"❌ Сейчас ход **{other_name}**! Дождитесь своей очереди.")
        return
    
    # Проверяем, что прислали именно кубик
    if message.dice is None or message.dice.emoji != "🎲":
        bot.reply_to(
            message,
            f"❌ **{message.from_user.first_name}**, вы отправили не кубик!\n\n"
            f"🎲 Пожалуйста, отправьте **кубик** используя команду `/dice` или нажав на кубик в меню.\n\n"
            f"📋 **Доступные эмодзи для броска:** 🎲 (кубик)",
            parse_mode="Markdown"
        )
        return
    
    # Получаем значение кубика
    roll_value = message.dice.value
    roll_num = duel.roll_count[user_id] + 1
    
    duel.scores[user_id].append(roll_value)
    duel.roll_count[user_id] = roll_num
    current_sum = sum(duel.scores[user_id])
    
    player_name = duel.creator_name if user_id == duel.creator_id else duel.player2_name
    
    send_sticker(chat_id, "dice_roll")
    
    bot.send_message(
        chat_id,
        f"🎲 **{player_name}** бросок #{roll_num}: выпало **{roll_value}**\n"
        f"📊 Текущая сумма: **{current_sum}**",
        parse_mode="Markdown"
    )
    
    if duel.roll_count[user_id] >= 3:
        other_id = duel.creator_id if user_id == duel.player2_id else duel.player2_id
        other_name = duel.creator_name if user_id == duel.player2_id else duel.player2_name
        
        if duel.roll_count[other_id] >= 3:
            score1 = sum(duel.scores[duel.creator_id])
            score2 = sum(duel.scores[duel.player2_id])
            name1 = duel.creator_name
            name2 = duel.player2_name
            
            result = (
                f"🎲 **ИТОГ ДУЭЛИ** 🎲\n\n"
                f"👤 **{name1}:** {score1} очков\n"
                f"👤 **{name2}:** {score2} очков\n\n"
            )
            
            if score1 > score2:
                result += f"🏆 **ПОБЕДИТЕЛЬ: {name1}!** 🏆"
                send_sticker(chat_id, "victory")
            elif score2 > score1:
                result += f"🏆 **ПОБЕДИТЕЛЬ: {name2}!** 🏆"
                send_sticker(chat_id, "victory")
            else:
                result += f"🤝 **НИЧЬЯ!**"
            
            bot.send_message(chat_id, result, parse_mode="Markdown")
            del duels[chat_id]
            return
        else:
            duel.current_turn = other_id
            bot.send_message(
                chat_id,
                f"✅ **{player_name}** завершил броски!\n"
                f"📊 Сумма: **{current_sum}**\n\n"
                f"🎯 **Теперь ход {other_name}!**\n"
                f"👇 Отправьте **/dice** или нажмите на кубик",
                parse_mode="Markdown"
            )
    else:
        bot.send_message(
            chat_id,
            f"🎲 **{player_name}**, осталось бросков: {3 - duel.roll_count[user_id]}\n"
            f"👇 Отправьте **/dice** снова!",
            parse_mode="Markdown"
        )


@bot.callback_query_handler(func=lambda call: call.data == "cancel_duel")
def cancel_duel(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    if chat_id not in duels:
        bot.answer_callback_query(call.id, "❌ Нет дуэли!")
        return
    
    duel = duels[chat_id]
    
    if user_id != duel.creator_id and user_id != duel.player2_id:
        bot.answer_callback_query(call.id, "❌ Вы не участник дуэли!")
        return
    
    del duels[chat_id]
    bot.answer_callback_query(call.id, "✅ Дуэль отменена!")
    bot.edit_message_text("❌ **Дуэль отменена.**", chat_id, call.message.message_id, parse_mode="Markdown")


@bot.message_handler(commands=['cancel_duel'])
def cancel_duel_command(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if chat_id not in duels:
        bot.reply_to(message, "❌ Нет активной дуэли!")
        return
    
    duel = duels[chat_id]
    
    if user_id != duel.creator_id and user_id != duel.player2_id:
        bot.reply_to(message, "❌ Вы не участник дуэли!")
        return
    
    del duels[chat_id]
    bot.reply_to(message, "✅ **Дуэль отменена!**")


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
    bot.send_message(chat_id, "🛑 **Игра остановлена админом!**")


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
    bot.reply_to(message, "⏹️ **Игра остановлена!**")


# ================= ЗАПУСК БОТА =================
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
