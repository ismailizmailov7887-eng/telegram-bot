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

games = {}
duels = {}

# --- КЛАССЫ СОСТОЯНИЙ ---

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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def register_commands():
    commands = [
        BotCommand("start", "Главное меню"),
        BotCommand("duel", "Создать дуэль 1v1"),
        BotCommand("start_game", "Запустить 3 двери (админ)"),
        BotCommand("stop_game", "Остановить игру 3 двери"),
        BotCommand("help", "Помощь")
    ]
    bot.set_my_commands(commands)

# --- ОБРАБОТКА КОМАНД ---

@bot.message_handler(commands=['start', 'help'])
def send_help(message):
    bot.reply_to(message, "🎮 **МЕНЮ ИГР**\n\n🎲 /duel — Создать дуэль на кубиках\n🚪 /start_game — Игра '3 двери' (для админов)", parse_mode="Markdown")

@bot.message_handler(commands=['duel'])
def start_duel_process(message):
    chat_id = message.chat.id
    if chat_id in duels:
        return bot.reply_to(message, "⚠️ В этом чате уже есть активная дуэль или заявка!")
    
    msg = bot.send_message(chat_id, "💰 Введите приз для дуэли (например: 100 звезд):")
    bot.register_next_step_handler(msg, save_duel_prize, chat_id)

def save_duel_prize(message, chat_id):
    if not message.text or message.text.startswith('/'): return
    
    duel = Duel(message.from_user.id, message.from_user.first_name, message.text)
    duels[chat_id] = duel
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎲 ПРИСОЕДИНИТЬСЯ", callback_data="join_duel"))
    markup.add(InlineKeyboardButton("❌ ОТМЕНИТЬ", callback_data="cancel_duel"))
    
    bot.send_message(chat_id, f"🎲 **НОВАЯ ДУЭЛЬ**\n\n👤 Создатель: {duel.creator_name}\n🏆 Приз: {duel.prize}\n\nЖдем соперника...", 
                     reply_markup=markup, parse_mode="Markdown")

# --- ОБРАБОТКА КНОПОК ---

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    if call.data == "join_duel":
        duel = duels.get(chat_id)
        if not duel or duel.started: return bot.answer_callback_query(call.id, "Дуэль уже недоступна")
        if user_id == duel.creator_id: return bot.answer_callback_query(call.id, "Нельзя играть с собой!")
        
        duel.player2_id = user_id
        duel.player2_name = call.from_user.first_name
        duel.started = True
        duel.current_turn = duel.creator_id
        duel.scores = {duel.creator_id: [], duel.player2_id: []}
        duel.roll_count = {duel.creator_id: 0, duel.player2_id: 0}
        
        bot.edit_message_text(f"🎲 **ДУЭЛЬ НАЧАТА!**\n\n👤 {duel.creator_name} VS 👤 {duel.player2_name}\n\n"
                             f"🎯 Первым ходит {duel.creator_name}.\nОтправьте команду /dice или просто 🎲", 
                             chat_id, call.message.message_id, parse_mode="Markdown")

    elif call.data == "cancel_duel":
        duel = duels.get(chat_id)
        if duel and (user_id == duel.creator_id or user_id == duel.player2_id):
            del duels[chat_id]
            bot.edit_message_text("❌ Дуэль отменена.", chat_id, call.message.message_id)
        else:
            bot.answer_callback_query(call.id, "Только участники могут отменить!")

# --- ОБРАБОТКА КУБИКОВ И ТЕКСТА ---

@bot.message_handler(func=lambda message: message.chat.id in duels, content_types=['dice', 'text'])
def duel_dice_handler(message):
    chat_id = message.chat.id
    duel = duels[chat_id]
    if not duel.started: return

    user_id = message.from_user.id
    if user_id != duel.current_turn: return

    # Проверка команды (игнорируем юзернейм бота в команде)
    is_dice_cmd = False
    if message.text and message.text.split('@')[0] == '/dice':
        is_dice_cmd = True
    
    # Если пришел настоящий кубик или верная команда
    if (message.dice and message.dice.emoji == "🎲") or is_dice_cmd:
        if is_dice_cmd:
            # Бросаем кубик за игрока, если он ввел текст
            dice_msg = bot.send_dice(chat_id, reply_to_message_id=message.message_id)
            val = dice_msg.dice.value
        else:
            val = message.dice.value

        duel.scores[user_id].append(val)
        duel.roll_count[user_id] += 1
        total = sum(duel.scores[user_id])
        
        # Задержка для красоты (ждем анимацию)
        time.sleep(3)
        bot.reply_to(message, f"📊 Бросок {duel.roll_count[user_id]}/3: **{val}**\nВсего: **{total}**", parse_mode="Markdown")

        if duel.roll_count[user_id] >= 3:
            if user_id == duel.creator_id:
                duel.current_turn = duel.player2_id
                bot.send_message(chat_id, f"🎯 Твой ход, {duel.player2_name}! Кидай 🎲")
            else:
                finalize_duel(chat_id, duel)

def finalize_duel(chat_id, duel):
    s1 = sum(duel.scores[duel.creator_id])
    s2 = sum(duel.scores[duel.player2_id])
    
    text = f"🏁 **ФИНАЛ**\n\n👤 {duel.creator_name}: {s1}\n👤 {duel.player2_name}: {s2}\n\n"
    if s1 > s2: text += f"🏆 Победитель: **{duel.creator_name}**"
    elif s2 > s1: text += f"🏆 Победитель: **{duel.player2_name}**"
    else: text += "🤝 **НИЧЬЯ!**"
    
    bot.send_message(chat_id, text + f"\n🎁 Приз: {duel.prize}", parse_mode="Markdown")
    if chat_id in duels: del duels[chat_id]

# --- ОСТАЛЬНЫЕ КОМАНДЫ (3 ДВЕРИ) ---

@bot.message_handler(commands=['stop_game'])
def stop_all(message):
    if message.chat.id in games:
        del games[message.chat.id]
        bot.reply_to(message, "🛑 Игра '3 двери' остановлена.")
    if message.chat.id in duels:
        del duels[message.chat.id]
        bot.reply_to(message, "🛑 Дуэль удалена.")

# --- ЗАПУСК ---

@app.route('/')
def home(): return "OK", 200

def run_bot():
    register_commands()
    print("🚀 Бот запущен и готов к играм!")
    bot.infinity_polling(skip_pending=True)

if __name__ == '__main__':
    threading.Thread(target=run_bot).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
