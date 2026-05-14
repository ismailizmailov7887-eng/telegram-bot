import os
import threading
import time
import random
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask

# Настройка токена
TOKEN = os.environ.get("8598717015:AAGhbHPy-C9VTkcYb2XSyrJ3a_i83JNojf8")
if not TOKEN:
    print("❌ Ошибка: Не найден TELEGRAM_TOKEN!")
    exit(1)

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=20)
app = Flask(__name__)

# Хранилище данных (в памяти)
games = {}
duels = {}

# --- КЛАССЫ ---

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

# --- МЕНЮ КОМАНД ---

def register_commands():
    try:
        commands = [
            BotCommand("start", "Главное меню"),
            BotCommand("duel", "Создать дуэль 1v1"),
            BotCommand("start_game", "Запустить 3 двери (админ)"),
            BotCommand("stop_game", "Остановить игру 3 двери"),
            BotCommand("help", "Помощь")
        ]
        bot.set_my_commands(commands)
    except: pass

# --- ОБРАБОТЧИКИ КОМАНД ---

@bot.message_handler(commands=['start'])
def welcome(message):
    bot.reply_to(message, "🎮 **Игровой Бот**\n\n🚪 /start_game — Игра '3 Двери'\n🎲 /duel — Дуэль на кубиках", parse_mode="Markdown")

@bot.message_handler(commands=['duel'])
def init_duel(message):
    chat_id = message.chat.id
    if chat_id in duels:
        return bot.reply_to(message, "⚠️ В этом чате уже есть активная дуэль или заявка!")
    
    msg = bot.send_message(chat_id, "💰 Введите приз для дуэли:")
    bot.register_next_step_handler(msg, process_duel_prize, chat_id)

def process_duel_prize(message, chat_id):
    prize = message.text
    duels[chat_id] = Duel(message.from_user.id, message.from_user.first_name, prize)
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎲 ПРИСОЕДИНИТЬСЯ", callback_data="join_duel"))
    markup.add(InlineKeyboardButton("❌ ОТМЕНИТЬ ДУЭЛЬ", callback_data="cancel_duel"))
    
    bot.send_message(chat_id, f"🎲 **ДУЭЛЬ**\n\n👤 Создатель: {message.from_user.first_name}\n🏆 Приз: {prize}\n\nЖдем оппонента...", 
                     reply_markup=markup, parse_mode="Markdown")

# --- CALLBACK ОБРАБОТЧИКИ (Кнопки) ---

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    # --- ЛОГИКА ДУЭЛИ ---
    if call.data == "join_duel":
        if chat_id not in duels: return bot.answer_callback_query(call.id, "Дуэль не найдена")
        duel = duels[chat_id]
        if user_id == duel.creator_id: return bot.answer_callback_query(call.id, "Вы не можете играть с собой!")
        
        duel.player2_id = user_id
        duel.player2_name = call.from_user.first_name
        duel.started = True
        duel.current_turn = duel.creator_id
        duel.scores = {duel.creator_id: [], duel.player2_id: []}
        duel.roll_count = {duel.creator_id: 0, duel.player2_id: 0}
        
        bot.edit_message_text(f"🎲 **ДУЭЛЬ НАЧАТА!**\n\n{duel.creator_name} VS {duel.player2_name}\n\n"
                             f"🎯 Первым ходит {duel.creator_name}.\nОтправьте /dice или нажмите на 🎲", 
                             chat_id, call.message.message_id, parse_mode="Markdown")

    elif call.data == "cancel_duel":
        if chat_id in duels:
            duel = duels[chat_id]
            if user_id == duel.creator_id or user_id == duel.player2_id:
                del duels[chat_id]
                bot.edit_message_text("❌ Дуэль была отменена.", chat_id, call.message.message_id)
            else:
                bot.answer_callback_query(call.id, "Только участники могут отменить!")
        else:
            bot.answer_callback_query(call.id, "Дуэль уже завершена или не существует.")

    # --- ЛОГИКА 3 ДВЕРИ ---
    elif call.data == "join_game":
        game = games.get(chat_id)
        if not game: return bot.answer_callback_query(call.id, "Игра не найдена")
        if game.add_player(user_id, call.from_user.first_name):
            bot.answer_callback_query(call.id, "Вы зашли!")
            bot.edit_message_text(f"🚪 **ИГРА 3 ДВЕРИ**\n👥 Игроков: {len(game.players)}/30\nПриз: {game.prize}", 
                                 chat_id, call.message.message_id, 
                                 reply_markup=call.message.reply_markup)

# --- ЛОГИКА КУБИКОВ (DICE) ---

@bot.message_handler(content_types=['dice', 'text'])
def handle_rolls(message):
    chat_id = message.chat.id
    if chat_id not in duels: return

    duel = duels[chat_id]
    if not duel.started: return
    
    user_id = message.from_user.id
    if user_id != duel.current_turn: return

    # Если пришел текст /dice — кидаем кубик за игрока
    if message.text == "/dice":
        msg = bot.send_dice(chat_id)
        val = msg.dice.value
    # Если пришел именно эмодзи кубика
    elif message.dice and message.dice.emoji == "🎲":
        val = message.dice.value
    else:
        return # Игнорируем обычный текст

    # Обработка результата
    duel.scores[user_id].append(val)
    duel.roll_count[user_id] += 1
    
    total = sum(duel.scores[user_id])
    time.sleep(3) # Даем анимации прокрутиться
    bot.reply_to(message, f"📊 Результат: {val}. Всего очков: {total}")

    if duel.roll_count[user_id] == 3:
        if user_id == duel.creator_id:
            duel.current_turn = duel.player2_id
            bot.send_message(chat_id, f"🎯 Очередь {duel.player2_name}! Твой ход.")
        else:
            finish_duel(chat_id, duel)

def finish_duel(chat_id, duel):
    s1 = sum(duel.scores[duel.creator_id])
    s2 = sum(duel.scores[duel.player2_id])
    
    res = f"🏁 **КОНЕЦ ДУЭЛИ**\n\n👤 {duel.creator_name}: {s1}\n👤 {duel.player2_name}: {s2}\n\n"
    if s1 > s2: res += f"🏆 Победил {duel.creator_name}!"
    elif s2 > s1: res += f"🏆 Победил {duel.player2_name}!"
    else: res += "🤝 Ничья!"
    
    bot.send_message(chat_id, res + f"\n🎁 Приз: {duel.prize}", parse_mode="Markdown")
    if chat_id in duels: del duels[chat_id]

# --- Flask & Healthcheck ---

@app.route('/')
def index(): return "Bot is running", 200

def run_bot():
    register_commands()
    print("🚀 Бот онлайн")
    bot.infinity_polling(skip_pending=True)

if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
