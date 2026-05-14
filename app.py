import os
import threading
import time
import random
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask

# ================= ТОКЕН БОТА =================
TOKEN = os.environ.get("8598717015:AAGhbHPy-C9VTkcYb2XSyrJ3a_i83JNojf8")
if not TOKEN:
    print("❌ Ошибка: Не найден TELEGRAM_TOKEN!")
    exit(1)

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
            BotCommand("start_game", "🎮 Запустить групповую игру (админ)"),
            BotCommand("stop_game", "⏹️ Остановить игру (админ)"),
            BotCommand("duel", "🎲 Создать дуэль 1v1"),
        ]
        bot.delete_my_commands()
        bot.set_my_commands(commands)
        print("✅ Команды зарегистрированы!")
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")

# ================= КОМАНДА СТАРТ =================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "🤖 **Игровой бот**\n\n"
                 "🎮 **Команды:**\n"
                 "• `/start_game` - запустить групповую игру (админ)\n"
                 "• `/stop_game` - остановить игру (админ)\n"
                 "• `/duel` - создать дуэль 1v1 на кубиках\n\n"
                 "🎲 **Дуэль:**\n"
                 "• 2 игрока\n"
                 "• Каждый кидает кубик 3 раза\n"
                 "• Вписываете результат в кнопки 1-6\n"
                 "• Победитель — у кого сумма больше",
                 parse_mode="Markdown")

# ================= ДУЭЛИ =================
@bot.message_handler(commands=['duel'])
def create_duel(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    if chat_id in duels:
        bot.reply_to(message, "⚠️ В этом чате уже есть активная дуэль!")
        return
    
    duel = Duel(user_id, user_name)
    duels[chat_id] = duel
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎲 ПРИСОЕДИНИТЬСЯ", callback_data="join_duel"))
    
    bot.send_message(chat_id, f"🎲 **ДУЭЛЬ СОЗДАНА!**\n\n"
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
        bot.answer_callback_query(call.id, "❌ Вы создали дуэль!")
        return
    
    if duel.player2_id is not None:
        bot.answer_callback_query(call.id, "❌ Мест нет!")
        return
    
    duel.player2_id = user_id
    duel.player2_name = user_name
    bot.answer_callback_query(call.id, f"✅ Вы присоединились!")
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("🎲 НАЧАТЬ ДУЭЛЬ", callback_data="start_duel"),
        InlineKeyboardButton("❌ ОТМЕНА", callback_data="cancel_duel")
    )
    
    bot.edit_message_text(f"🎲 **ДУЭЛЬ**\n\n"
                         f"👤 {duel.creator_name} VS 👤 {duel.player2_name}\n\n"
                         f"✅ Оба собрались!\n"
                         f"🎯 Нажмите **«НАЧАТЬ ДУЭЛЬ»**",
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
    
    if user_id != duel.creator_id:
        bot.answer_callback_query(call.id, "❌ Только создатель!")
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
    for i in range(1, 7):
        markup.add(InlineKeyboardButton(f"🎲 {i}", callback_data=f"roll_{i}"))
    
    if duel.roll_count[user_id] >= 3:
        other_id = duel.creator_id if user_id == duel.player2_id else duel.player2_id
        other_name = duel.creator_name if user_id == duel.player2_id else duel.player2_name
        
        if duel.roll_count[other_id] >= 3:
            score1 = sum(duel.scores[duel.creator_id])
            score2 = sum(duel.scores[duel.player2_id])
            result = f"🎲 **ИТОГ**\n\n👤 {duel.creator_name}: {score1}\n👤 {duel.player2_name}: {score2}\n\n"
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
            bot.send_message(chat_id, f"✅ **{player_name}** завершил! Сумма: {current_sum}\n\n🎯 **Ход {other_name}!**",
                             reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(chat_id, f"🎲 **{player_name}**, бросок #{duel.roll_count[user_id]}!\n📊 Сумма: {current_sum}\nОсталось: {3 - duel.roll_count[user_id]}\n\n👇 Ваш следующий бросок:",
                         reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "cancel_duel")
def cancel_duel(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    
    if chat_id not in duels:
        bot.answer_callback_query(call.id, "❌ Нет дуэли!")
        return
    
    duel = duels[chat_id]
    
    if user_id != duel.creator_id:
        bot.answer_callback_query(call.id, "❌ Только создатель!")
        return
    
    del duels[chat_id]
    bot.answer_callback_query(call.id, "✅ Отменено!")
    bot.edit_message_text("❌ **Дуэль отменена.**", chat_id, call.message.message_id, parse_mode="Markdown")

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
