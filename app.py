import os
import threading
import time
import random
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask

# Инициализация
TOKEN = os.environ.get("8598717015:AAGhbHPy-C9VTkcYb2XSyrJ3a_i83JNojf8")
if not TOKEN:
    print("❌ Ошибка: Не найден TELEGRAM_TOKEN!")
    exit(1)

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=20)
app = Flask(__name__)

games = {}
duels = {}

# --- Классы состояний ---

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
        self.final_game = None

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

# --- Команды ---

def register_commands():
    commands = [
        BotCommand("start", "Главное меню"),
        BotCommand("help", "Правила игр"),
        BotCommand("duel", "Создать дуэль 1v1"),
        BotCommand("start_game", "Запустить 3 двери (админ)"),
        BotCommand("stop_game", "Остановить игру (админ)"),
    ]
    bot.set_my_commands(commands)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "✨ **ДОБРО ПОЖАЛОВАТЬ** ✨\n\n🚪 `/start_game` — 3 ДВЕРИ\n🎲 `/duel` — Дуэль на кубиках\n📖 `/help` — Правила", parse_mode="Markdown")

@bot.message_handler(commands=['help'])
def show_rules(message):
    rules = (
        "📖 **ПРАВИЛА**\n\n"
        "🚪 **3 ДВЕРИ**:\n"
        "- 2 двери безопасные, 1 опасная (65% шанс вылета).\n"
        "- Финал: Камень-Ножницы-Бумага до 3 побед.\n\n"
        "🎲 **ДУЭЛЬ**:\n"
        "- Игроки по очереди кидают кубик 🎲 3 раза.\n"
        "- Побеждает тот, у кого сумма больше."
    )
    bot.reply_to(message, rules, parse_mode="Markdown")

# --- Логика Игры 3 Двери ---

def game_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("🚪 ПРИСОЕДИНИТЬСЯ", callback_data="join_game"))
    markup.row(InlineKeyboardButton("▶️ НАЧАТЬ", callback_data="start_doors_game"),
               InlineKeyboardButton("⏹️ СТОП", callback_data="stop_doors_game"))
    return markup

@bot.message_handler(commands=['start_game'])
def start_game_command(message):
    chat_id = message.chat.id
    if message.chat.type == "private":
        return bot.reply_to(message, "❌ Игра работает только в группах!")
    
    admins = bot.get_chat_administrators(chat_id)
    if not any(a.user.id == message.from_user.id for a in admins):
        return bot.reply_to(message, "👑 Только админ может запустить игру!")

    msg = bot.reply_to(message, "💰 Введите приз (текстом):")
    bot.register_next_step_handler(msg, save_prize_and_open_lobby, chat_id, message.from_user.id)

def save_prize_and_open_lobby(message, chat_id, admin_id):
    prize = message.text
    games[chat_id] = Game(chat_id, prize, admin_id)
    bot.send_message(chat_id, f"🚪 **ИГРА 3 ДВЕРИ**\n\n🏆 Приз: {prize}\n👥 Игроков: 0/30\n\nНажмите кнопку ниже, чтобы зайти!", 
                     reply_markup=game_keyboard(), parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "join_game")
def handle_join(call):
    game = games.get(call.message.chat.id)
    if not game: return bot.answer_callback_query(call.id, "Игра не найдена")
    
    if game.add_player(call.from_user.id, call.from_user.first_name):
        bot.answer_callback_query(call.id, "✅ Вы в игре!")
        bot.edit_message_text(f"🚪 **ИГРА 3 ДВЕРИ**\n\n🏆 Приз: {game.prize}\n👥 Игроков: {len(game.players)}/30", 
                             call.message.chat.id, call.message.message_id, reply_markup=game_keyboard(), parse_mode="Markdown")
    else:
        bot.answer_callback_query(call.id, "❌ Вы уже в игре или нет мест")

@bot.callback_query_handler(func=lambda call: call.data == "start_doors_game")
def handle_start_btn(call):
    game = games.get(call.message.chat.id)
    if not game or call.from_user.id != game.admin_id:
        return bot.answer_callback_query(call.id, "Только админ, создавший игру!")
    
    if len(game.players) < 2:
        return bot.answer_callback_query(call.id, "Нужно минимум 2 игрока!", show_alert=True)
    
    start_doors_round(call.message.chat.id, game)

def start_doors_round(chat_id, game):
    game.choosing_phase = True
    game.choices = {}
    game.random_dead_door()
    
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("Дверь 1", callback_data="door_1"),
               InlineKeyboardButton("Дверь 2", callback_data="door_2"),
               InlineKeyboardButton("Дверь 3", callback_data="door_3"))
    
    alive = game.get_alive_players()
    msg = bot.send_message(chat_id, f"🔴 **РАУНД {game.round}**\n\nВыберите дверь! У вас 15 секунд.", 
                           reply_markup=markup, parse_mode="Markdown")
    
    def countdown():
        time.sleep(15)
        if chat_id in games:
            process_doors_round(chat_id, game)
            
    threading.Thread(target=countdown).start()

@bot.callback_query_handler(func=lambda call: call.data.startswith("door_"))
def handle_door_choice(call):
    game = games.get(call.message.chat.id)
    if not game or not game.choosing_phase: return
    
    uid = call.from_user.id
    if uid not in game.get_alive_players(): return bot.answer_callback_query(call.id, "Вы не участвуете")
    if uid in game.choices: return bot.answer_callback_query(call.id, "Вы уже выбрали!")
    
    game.choices[uid] = int(call.data.split("_")[1])
    bot.answer_callback_query(call.id, f"✅ Выбрана дверь {game.choices[uid]}")

def process_doors_round(chat_id, game):
    game.choosing_phase = False
    alive_players = game.get_alive_players()
    
    # Кто не успел — выбрал случайно
    for uid in alive_players:
        if uid not in game.choices:
            game.choices[uid] = random.choice([1, 2, 3])

    dead_list = []
    result_text = f"📊 **ИТОГИ РАУНДА {game.round}**\n\n💀 Опасная дверь была: {game.dead_door}\n\n"
    
    for uid, door in game.choices.items():
        name = game.players[uid]['name']
        if door == game.dead_door:
            if random.random() < 0.65:
                game.players[uid]['alive'] = False
                dead_list.append(name)
    
    if dead_list:
        result_text += f"💀 Погибли: {', '.join(dead_list)}\n"
    else:
        result_text += "🍀 В этом раунде все выжили!\n"
    
    bot.send_message(chat_id, result_text, parse_mode="Markdown")
    
    # Проверка условий завершения
    still_alive = game.get_alive_players()
    if len(still_alive) <= 1:
        if len(still_alive) == 1:
            winner = list(still_alive.values())[0]['name']
            bot.send_message(chat_id, f"🏆 **ПОБЕДИТЕЛЬ: {winner}**\nПриз: {game.prize}", parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "💀 Все погибли. Победителя нет.")
        del games[chat_id]
    else:
        game.round += 1
        time.sleep(3)
        start_doors_round(chat_id, game)

# --- Логика Дуэли ---

@bot.message_handler(commands=['duel'])
def cmd_duel(message):
    chat_id = message.chat.id
    if chat_id in duels:
        return bot.reply_to(message, "❌ Дуэль уже идет!")
    
    msg = bot.send_message(chat_id, "💰 На что играем? (Введите приз):")
    bot.register_next_step_handler(msg, create_duel_lobby, chat_id)

def create_duel_lobby(message, chat_id):
    prize = message.text
    duels[chat_id] = Duel(message.from_user.id, message.from_user.first_name, prize)
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎲 ПРИСОЕДИНИТЬСЯ", callback_data="join_duel"))
    bot.send_message(chat_id, f"🎲 **ДУЭЛЬ СОЗДАНА**\n\nСоздатель: {message.from_user.first_name}\n🏆 Приз: {prize}\n\nЖдем оппонента...", 
                     reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "join_duel")
def handle_join_duel(call):
    duel = duels.get(call.message.chat.id)
    if not duel or duel.started: return
    if call.from_user.id == duel.creator_id: return bot.answer_callback_query(call.id, "Нельзя играть с самим собой!")
    
    duel.player2_id = call.from_user.id
    duel.player2_name = call.from_user.first_name
    duel.started = True
    duel.current_turn = duel.creator_id
    duel.scores = {duel.creator_id: [], duel.player2_id: []}
    duel.roll_count = {duel.creator_id: 0, duel.player2_id: 0}
    
    bot.edit_message_text(f"🎲 **ДУЭЛЬ НАЧАТА!**\n\n{duel.creator_name} VS {duel.player2_name}\n\n"
                         f"🎯 Первым ходит {duel.creator_name}.\nОтправь 🎲 (кубик) в чат!", 
                         call.message.chat.id, call.message.message_id, parse_mode="Markdown")

@bot.message_handler(content_types=['dice'])
def handle_dice(message):
    chat_id = message.chat.id
    if chat_id not in duels: return
    
    duel = duels[chat_id]
    uid = message.from_user.id
    
    if uid != duel.current_turn:
        return # Игнорируем броски не в свою очередь

    val = message.dice.value
    duel.scores[uid].append(val)
    duel.roll_count[uid] += 1
    
    total = sum(duel.scores[uid])
    bot.reply_to(message, f"📊 Бросок {duel.roll_count[uid]}/3: **{val}**\nВсего: **{total}**", parse_mode="Markdown")
    
    # Смена хода или финал
    if duel.roll_count[uid] == 3:
        if uid == duel.creator_id:
            duel.current_turn = duel.player2_id
            bot.send_message(chat_id, f"🎯 Очередь {duel.player2_name}! Кидай 🎲")
        else:
            # Считаем итог
            s1 = sum(duel.scores[duel.creator_id])
            s2 = sum(duel.scores[duel.player2_id])
            
            res = f"🏁 **ИТОГ ДУЭЛИ**\n\n👤 {duel.creator_name}: {s1}\n👤 {duel.player2_name}: {s2}\n\n"
            if s1 > s2:
                res += f"🏆 Победил **{duel.creator_name}**!\n🎁 Приз: {duel.prize}"
            elif s2 > s1:
                res += f"🏆 Победил **{duel.player2_name}**!\n🎁 Приз: {duel.prize}"
            else:
                res += "🤝 Ничья!"
                
            bot.send_message(chat_id, res, parse_mode="Markdown")
            del duels[chat_id]

# --- Запуск ---

def run_bot():
    register_commands()
    print("🚀 Бот запущен...")
    bot.infinity_polling(skip_pending=True)

if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
