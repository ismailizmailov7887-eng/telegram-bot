import os
import threading
import time
import random
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask

# ================= НАСТРОЙКИ =================
TOKEN = "8598717015:AAGhbHPy-C9VTkcYb2XSyrJ3a_i83JNojf8"
bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=20)
app = Flask(__name__)

# Сюда вставь ID стикеров, которые получишь от бота
STICKERS = {
    "START": "CAACAgIAAxkBAAEL...", # Стикер начала игры
    "WAIT": "CAACAgIAAxkBAAEL...",  # Когда просят подождать хода
    "WIN": "CAACAgIAAxkBAAEL...",   # Стикер победы
    "ERROR": "CAACAgIAAxkBAAEL...", # Стикер ошибки/текста вместо костей
    "LEAVE": "CAACAgIAAxkBAAEL..."  # При выходе из игры
}

games = {}  
duels = {}  

# ================= КЛАССЫ =================
class Game:
    def __init__(self, chat_id, prize, admin_id):
        self.chat_id = chat_id
        self.prize = prize
        self.admin_id = admin_id
        self.players = {}
        self.round = 1
        self.paused = False
        self.choosing_phase = False
        self.choices = {}
        self.dead_room = None

    def add_player(self, user_id, name):
        if user_id not in self.players:
            self.players[user_id] = {'name': name, 'alive': True}
            return True
        return False

    def get_alive_players(self):
        return {uid: data for uid, data in self.players.items() if data['alive']}

class Duel:
    def __init__(self, creator_id, creator_name, chat_id):
        self.chat_id = chat_id
        self.creator_id = creator_id
        self.creator_name = creator_name
        self.player2_id = None
        self.player2_name = None
        self.started = False
        self.scores = {}
        self.turn_count = {}
        self.current_turn = creator_id

# ================= УТИЛИТЫ =================
def is_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except: return False

# ================= ОБРАБОТКА КОМАНД =================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    text = (
        "✨ **ДОБРО ПОЖАЛОВАТЬ В ИГРОВОЙ ХАБ!** ✨\n\n"
        "Я — твой проводник в мир азарта. Здесь всё по-честному.\n\n"
        "🚀 **ЧТО ТУТ ЕСТЬ?**\n"
        "⚔️ **Дуэли 1v1** — бот сам считает очки кубиков!\n"
        "🌋 **Выживание** — массовая игра в комнаты.\n\n"
        "Жми /help, чтобы узнать правила!"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['help'])
def help_rules(message):
    text = (
        "📖 **КОДЕКС ИГРОКА**\n\n"
        "🎲 **ДУЭЛЬ (/duel):**\n"
        "Жми кнопку → Бросайте кубики. Бот считает сумму 3-х бросков.\n\n"
        "🏆 **ВЫЖИВАНИЕ (/start_game):**\n"
        "Только для админов. Выбирай дверь. В одной из них — ловушка!"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# ================= ЛОГИКА ДУЭЛЕЙ =================
@bot.message_handler(commands=['duel'])
def create_duel_cmd(message):
    chat_id = message.chat.id
    if chat_id in duels:
        bot.reply_to(message, "⏳ Дуэль уже идет!")
        return

    duel = Duel(message.from_user.id, message.from_user.first_name, chat_id)
    duels[chat_id] = duel
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⚔️ ПРИНЯТЬ", callback_data="join_duel"),
               InlineKeyboardButton("🚪 ПОКИНУТЬ", callback_data="leave_duel"))
    
    bot.send_message(chat_id, f"🎲 **РЕГИСТРАЦИЯ НА ДУЭЛЬ**\n\nСоздатель: `{duel.creator_name}`\n⏳ У вас **1 минута**, чтобы найти оппонента!", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "join_duel")
def join_duel(call):
    chat_id = call.message.chat.id
    if chat_id not in duels: return
    duel = duels[chat_id]
    if call.from_user.id == duel.creator_id: return bot.answer_callback_query(call.id, "Жди врага! 😈")
    
    duel.player2_id, duel.player2_name = call.from_user.id, call.from_user.first_name
    duel.started = True
    duel.scores = {duel.creator_id: 0, duel.player2_id: 0}
    duel.turn_count = {duel.creator_id: 0, duel.player2_id: 0}
    
    bot.send_sticker(chat_id, STICKERS["START"])
    bot.edit_message_text(f"🏁 **ДУЭЛЬ: `{duel.creator_name}` VS `{duel.player2_name}`**\n\nПервым бросает: `{duel.creator_name}`", chat_id, call.message.message_id, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "leave_duel")
def leave_duel(call):
    if call.message.chat.id in duels and call.from_user.id == duels[call.message.chat.id].creator_id:
        del duels[call.message.chat.id]
        bot.edit_message_text("❌ Дуэль отменена.", call.message.chat.id, call.message.message_id)

# ================= СУДЬЯ (ОТСЛЕЖИВАНИЕ ЧАТА) =================
@bot.message_handler(func=lambda m: True, content_types=['text', 'dice', 'sticker'])
def monitor_chat(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    # Чтобы получить ID стикера — отправь его боту
    if message.content_type == 'sticker':
        print(f"DEBUG STICKER ID: {message.sticker.file_id}")
    
    # Админ-команда (скрытая)
    if message.text == "/stop_game" and is_admin(chat_id, user_id):
        if chat_id in duels: del duels[chat_id]
        bot.send_sticker(chat_id, STICKERS["LEAVE"])
        bot.reply_to(message, "🛑 Игры остановлены администратором.")
        return

    if chat_id not in duels or not duels[chat_id].started: return
    duel = duels[chat_id]
    if user_id not in [duel.creator_id, duel.player2_id]: return

    # Проверка очереди
    if user_id != duel.current_turn:
        if message.content_type in ['dice', 'text']:
            bot.delete_message(chat_id, message.message_id)
            msg = bot.send_message(chat_id, f"🛑 `{message.from_user.first_name}`, сейчас не твой ход!")
            threading.Timer(3, bot.delete_message, args=[chat_id, msg.message_id]).start()
        return

    # Если кинул не кости
    if message.content_type != 'dice' or message.dice.emoji != '🎲':
        bot.send_sticker(chat_id, STICKERS["ERROR"])
        bot.reply_to(message, "⚠️ Эй! Сейчас нужно кинуть **КУБИК** 🎲")
        return

    # Засчитываем бросок
    score = message.dice.value
    duel.scores[user_id] += score
    duel.turn_count[user_id] += 1
    
    time.sleep(3.5) # Ждем пока кубик остановится

    # Проверка финала
    if duel.turn_count[duel.creator_id] == 3 and duel.turn_count[duel.player2_id] == 3:
        s1, s2 = duel.scores[duel.creator_id], duel.scores[duel.player2_id]
        bot.send_sticker(chat_id, STICKERS["WIN"])
        res = f"🏁 **ФИНАЛ ДУЭЛИ**\n\n👤 `{duel.creator_name}`: {s1}\n👤 `{duel.player2_name}`: {s2}\n\n"
        if s1 > s2: res += f"🏆 Победил `{duel.creator_name}`!"
        elif s2 > s1: res += f"🏆 Победил `{duel.player2_name}`!"
        else: res += "🤝 Ничья!"
        bot.send_message(chat_id, res, parse_mode="Markdown")
        del duels[chat_id]
    else:
        duel.current_turn = duel.player2_id if duel.current_turn == duel.creator_id else duel.creator_id
        next_name = duel.creator_name if duel.current_turn == duel.creator_id else duel.player2_name
        bot.send_message(chat_id, f"✅ Принято! Теперь ход игрока: `{next_name}`")

# ================= ЗАПУСК =================
def run_bot():
    bot.set_my_commands([
        BotCommand("start", "🏠 Главная"),
        BotCommand("duel", "🎲 Дуэль 1v1"),
        BotCommand("start_game", "🌋 Выживание"),
        BotCommand("help", "📖 Правила")
    ])
    bot.infinity_polling()

if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))

