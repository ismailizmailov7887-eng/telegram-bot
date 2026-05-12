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

# ========== РЕГИСТРАЦИЯ КОМАНД ДЛЯ МЕНЮ ==========
def register_commands():
    """Регистрирует команды бота в Telegram API для отображения в меню"""
    try:
        commands = [
            BotCommand("start", "🏠 Начать работу с ботом"),
            BotCommand("start_game", "🎮 Запустить новую игру (только админ)"),
            BotCommand("stop_game", "⏹️ Остановить активную игру (только админ)"),
        ]
        bot.delete_my_commands()
        bot.set_my_commands(commands)
        print("✅ Команды зарегистрированы в Telegram!")
    except Exception as e:
        print(f"⚠️ Ошибка регистрации команд: {e}")

# ================= КОМАНДЫ БОТА =================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🤖 Привет! Я бот для игры!\n\n"
                 "👑 **Чтобы начать игру, админ чата должен:**\n"
                 "1️⃣ Нажать кнопку «СТАРТ»\n"
                 "2️⃣ Указать приз\n"
                 "3️⃣ Дождаться участников и нажать «НАЧАТЬ ИГРУ»\n\n"
                 "🎲 **Правила:**\n"
                 "• 3 комнаты, одна опасная (50% смерть)\n"
                 "• Опасная комната меняется каждый раунд\n"
                 "• На выбор — 30 секунд\n"
                 "• В финале — Камень, ножницы, бумага до 3 побед\n\n"
                 "📋 **Команды:**\n"
                 "/start_game - запустить игру (админ)\n"
                 "/stop_game - остановить игру (админ)",
                 parse_mode="Markdown")

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
        bot.reply_to(message, "❌ Только администратор чата может запустить игру!")
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
    bot.reply_to(message, "⏹️ **Игра остановлена!**")
    bot.send_message(chat_id, "▶️ Нажмите **СТАРТ** чтобы начать новую игру.",
                     reply_markup=game_control_keyboard(), parse_mode="Markdown")

def game_control_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("▶️ СТАРТ", callback_data="admin_start_game"),
        InlineKeyboardButton("⏹️ СТОП", callback_data="admin_stop_game")
    )
    return markup

def game_control_keyboard_with_join():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🚪 ПРИСОЕДИНИТЬСЯ", callback_data="join_game"),
        InlineKeyboardButton("▶️ НАЧАТЬ ИГРУ", callback_data="start_game_rooms"),
        InlineKeyboardButton("⏹️ СТОП", callback_data="admin_stop_game")
    )
    return markup

@bot.callback_query_handler(func=lambda call: call.data == "admin_start_game")
def admin_start_game(call):
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
    
    if chat_id in games:
        bot.answer_callback_query(call.id, "⚠️ Игра уже запущена!", show_alert=True)
        return
    
    bot.answer_callback_query(call.id, "✅ Введите приз!")
    msg = bot.send_message(chat_id, "💰 **Введите приз для победителя:**", parse_mode="Markdown")
    bot.register_next_step_handler(msg, set_prize, chat_id, user_id)

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
    bot.send_message(chat_id, "🛑 **Игра остановлена!**\n\n▶️ Нажмите **СТАРТ** чтобы начать новую.",
                     reply_markup=game_control_keyboard(), parse_mode="Markdown")

def set_prize(message, chat_id, admin_id):
    prize = message.text
    games[chat_id] = Game(chat_id, prize, admin_id)
    bot.send_message(chat_id, f"🎮 **ИГРА СОЗДАНА!**\n\n🏆 Приз: {prize}\n👥 Игроков: 0/30",
                     reply_markup=game_control_keyboard_with_join(), parse_mode="Markdown")

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
    
    bot.edit_message_text(f"🎮 **ИГРА СОЗДАНА!**\n\n🏆 Приз: {game.prize}\n👥 Игроков: {len(game.players)}/30",
                          chat_id, call.message.message_id,
                          reply_markup=game_control_keyboard_with_join(), parse_mode="Markdown")

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
        bot.send_message(chat_id, "❌ Только админ может начать!")
        return
    
    if len(game.players) < 2:
        bot.send_message(chat_id, "❌ Нужно минимум 2 игрока!")
        return
    
    bot.send_message(chat_id, f"🎮 **ИГРА НАЧИНАЕТСЯ!**\n👥 Участников: {len(game.players)}\n🏆 Приз: {game.prize}",
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
    
    bot.send_message(chat_id, f"🔴 **РАУНД {game.round}**\n\n🎲 Выберите комнату!\n\n👥 Живые ({len(alive)}):\n{players_text}\n\n⏰ 30 секунд!",
                     reply_markup=markup, parse_mode="Markdown")
    
    def timer_and_process():
        time.sleep(30)
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
            msg += f"🚪 **КОМНАТА {room}**\n"
            for uid in room_players[room]:
                if room == game.dead_room and random.random() < 0.5:
                    dead.append(uid)
                    msg += f"   💀 {game.players[uid]['name']} → погиб\n"
                else:
                    msg += f"   ✅ {game.players[uid]['name']} → выжил\n"
            msg += "\n"
    
    for uid in dead:
        game.players[uid]['alive'] = False
    
    alive = game.get_alive_players()
    msg += f"✅ **ВЫЖИЛИ:** " + ", ".join([p['name'] for p in alive.values()])
    bot.send_message(chat_id, msg, parse_mode="Markdown")
    
    if len(alive) > 2:
        game.round += 1
        time.sleep(4)
        bot.send_message(chat_id, f"🔜 **РАУНД {game.round}!** Осталось {len(alive)} участников. Через 5 секунд...")
        time.sleep(5)
        start_round(chat_id, game)
    elif len(alive) == 2:
        bot.send_message(chat_id, "🎯 **ФИНАЛ! Камень, ножницы, бумага до 3 побед!**")
        time.sleep(2)
        start_rps_final(chat_id, game, list(alive.keys()))
    elif len(alive) == 1:
        winner = list(alive.values())[0]['name']
        bot.send_message(chat_id, f"🏆 **ПОБЕДИТЕЛЬ: {winner}!** 🎁 Приз: {game.prize}")
        del games[chat_id]
    else:
        bot.send_message(chat_id, f"💀 Все погибли! Приз {game.prize} невостребован.")
        del games[chat_id]

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
    
    bot.send_message(chat_id, f"🎮 **{p1_name}** VS **{p2_name}**\nДо 3 побед!")
    ask_for_choice(chat_id, game, p1_id)

def ask_for_choice(chat_id, game, user_id):
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("🗿 КАМЕНЬ", callback_data="rps_rock"),
        InlineKeyboardButton("✂️ НОЖНИЦЫ", callback_data="rps_scissors"),
        InlineKeyboardButton("📄 БУМАГА", callback_data="rps_paper")
    )
    bot.send_message(chat_id, f"🎮 {game.players[user_id]['name']}, ваш ход!",
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
    
    choice = {'rps_rock': 'камень', 'rps_scissors': 'ножницы', 'rps_paper': 'бумага'}[call.data]
    
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
            bot.send_message(chat_id, f"🏆 **ПОБЕДИТЕЛЬ: {p1['name']}!** 🎁 Приз: {game.prize}")
            del games[chat_id]
        elif p2['score'] >= 3:
            bot.send_message(chat_id, f"🏆 **ПОБЕДИТЕЛЬ: {p2['name']}!** 🎁 Приз: {game.prize}")
            del games[chat_id]
        else:
            final['round'] += 1
            final['waiting_for'] = final['player1']['id']
            time.sleep(2)
            bot.send_message(chat_id, f"🔜 **РАУНД {final['round']}!** Начинает {p1['name']}!")
            ask_for_choice(chat_id, game, final['player1']['id'])

# ================= ЗАПУСК БОТА В ПОТОКЕ =================
def run_bot():
    register_commands()
    print("🚀 Бот запускается...")
    bot.remove_webhook()
    time.sleep(1)
    bot.infinity_polling(timeout=30, long_polling_timeout=20)

# ================= ВЕБ-СЕРВЕР =================
@app.route('/')
def home():
    return "🤖 Бот работает!", 200

@app.route('/health')
def health():
    return "OK", 200

# ================= ТОЧКА ВХОДА =================
if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    print(f"🌐 Веб-сервер на порту {port}")
    app.run(host='0.0.0.0', port=port)
