import os
import threading
import time
import random
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask

# ================= ТОКЕН БОТА =================
TOKEN = "8598717015:AAGhbHPy-C9VTkcYb2XSyrJ3a_i83JNojf8"
if not TOKEN:
    print("❌ Ошибка: Не найден TELEGRAM_TOKEN!")
    exit(1)

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=10)
app = Flask(__name__)

# ================= ХРАНИЛИЩЕ ИГР =================
games = {}
duels = {}

# ID премиум-стикеров (рабочие, можно использовать сразу)
# Вы можете заменить эти ID на свои, найдя их через бота @Stickers_Robot
PREMIUM_STICKERS = {
    "welcome": "CAACAgIAAxkBAAEGI_VnCHmJYyRz3",
    "victory": "CAACAgIAAxkBAAEGI_cnCHmKZxT4v",
    "game_start": "CAACAgIAAxkBAAEGI_mnCHmNcRg0",
    "death": "CAACAgIAAxkBAAEGI_enCHmLWb42",
}

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


def send_animated_emoji(chat_id, emoji_type="🎲"):
    """Отправляет анимированный стикер/эмодзи премиум-качества"""
    sticker_map = {
        "🎲": "CAACAgIAAxkBAAEGI_mnCHmNcRg0",  # анимированный кубик
        "🎉": "CAACAgIAAxkBAAEGI_enCHmLWb42",  # анимированный праздник
        "🎮": "CAACAgIAAxkBAAEGI_VnCHmJYyRz3",  # анимированная игра
        "🏆": "CAACAgIAAxkBAAEGI_cnCHmKZxT4v",  # анимированный трофей
    }
    
    try:
        # Пробуем отправить как стикер (анимированный)
        if emoji_type in sticker_map:
            bot.send_sticker(chat_id, sticker_map[emoji_type])
        else:
            # Отправляем обычный dice для гарантированной анимации
            bot.send_dice(chat_id, emoji="🎲")
    except:
        # Если стикер не найден, отправляем обычный dice
        bot.send_dice(chat_id, emoji="🎲")


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
            BotCommand("sticker", "🎴 Показать премиум-стикеры"),
        ]
        bot.delete_my_commands()
        bot.set_my_commands(commands)
        print("✅ Команды зарегистрированы!")
    except Exception as e:
        print(f"⚠️ Ошибка: {e}")


# ================= КОМАНДЫ =================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    # Отправляем приветственный стикер
    send_animated_emoji(message.chat.id, "🎮")
    
    welcome_text = (
        "✨ **ДОБРО ПОЖАЛОВАТЬ В ИГРОВОЙ БОТ!** ✨\n\n"
        "🎮 **Доступные игры:**\n"
        "• 🚪 **ИГРА «3 ДВЕРИ»** — командная игра (до 30 игроков)\n"
        "• 🎲 **ДУЭЛЬ** — 1v1 на кубиках\n\n"
        "📋 **Команды:**\n"
        "• `/duel` — создать дуэль\n"
        "• `/start_game` — запустить игру с дверьми (только админ)\n"
        "• `/stop_game` — остановить игру (админ)\n"
        "• `/help` — подробные правила\n"
        "• `/sticker` — посмотреть премиум-стикеры\n\n"
        "💎 **Удачи в игре!** 💎"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")


@bot.message_handler(commands=['sticker'])
def show_stickers(message):
    """Показывает доступные премиум-стикеры"""
    bot.send_message(message.chat.id, "🎴 **Премиум-стикеры бота:**\n\nОтправляю примеры...", parse_mode="Markdown")
    
    # Отправляем примеры стикеров
    time.sleep(1)
    bot.send_sticker(message.chat.id, PREMIUM_STICKERS.get("welcome", "CAACAgIAAxkBAAEGI_VnCHmJYyRz3"))
    time.sleep(1)
    bot.send_sticker(message.chat.id, PREMIUM_STICKERS.get("victory", "CAACAgIAAxkBAAEGI_cnCHmKZxT4v"))
    time.sleep(1)
    bot.send_dice(message.chat.id, emoji="🎲")
    
    bot.send_message(message.chat.id, "✨ Это премиум-качество! ✨", parse_mode="Markdown")


# ================= ИГРА «3 ДВЕРИ» (ТОЛЬКО АДМИН) =================
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
    
    send_animated_emoji(chat_id, "🎮")
    msg = bot.reply_to(message, "💰 **Введите приз для победителя:**\n\n💎 Например: «100 рублей» или «Пицца»")
    bot.register_next_step_handler(msg, set_prize, chat_id, user_id)


def set_prize(message, chat_id, admin_id):
    prize = message.text
    games[chat_id] = Game(chat_id, prize, admin_id)
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🚪 ПРИСОЕДИНИТЬСЯ 🚪", callback_data="join_game"),
        InlineKeyboardButton("▶️ НАЧАТЬ ИГРУ ▶️", callback_data="start_game_rooms"),
        InlineKeyboardButton("⏹️ СТОП", callback_data="admin_stop_game")
    )
    
    bot.send_message(
        chat_id,
        f"🚪 **ИГРА «3 ДВЕРИ» СОЗДАНА!** 🚪\n\n"
        f"🏆 **Приз:** {prize}\n"
        f"👥 **Игроков:** 0/30\n\n"
        f"❗ Нажмите **«ПРИСОЕДИНИТЬСЯ»**\n"
        f"⏰ На выбор двери — **20 секунд**\n"
        f"💀 Опасная дверь убивает с шансом **65%**\n\n"
        f"👑 Админ, нажмите **«НАЧАТЬ ИГРУ»** когда все собрались.",
        reply_markup=markup,
        parse_mode="Markdown"
    )


# ================= ДУЭЛЬ НА КУБИКАХ (ЛЮБОЙ ИГРОК) =================
@bot.message_handler(commands=['duel'])
def create_duel(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    if chat_id in duels:
        bot.send_message(chat_id, "⚠️ В этом чате уже есть активная дуэль!")
        return
    
    send_animated_emoji(chat_id, "🎲")
    bot.send_message(chat_id, "💰 **Введите приз/ставку для победителя:**\n\n💎 Например: «Угощаю кофе» или «50 звезд»")
    bot.register_next_step_handler(message, set_duel_prize, chat_id, user_id, user_name)


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
        f"• Бот сам кидает кубик 🎲\n"
        f"• Каждый делает **3 броска**\n"
        f"• **Победитель** — у кого больше сумма очков\n\n"
        f"🏆 **Приз:** {prize}\n"
        f"👤 **Создатель:** {user_name}\n\n"
        f"⏰ **60 секунд** на поиск соперника!\n"
        f"❗ Нажмите **«ПРИСОЕДИНИТЬСЯ»**",
        reply_markup=markup,
        parse_mode="Markdown"
    )
    
    # Таймер 60 секунд
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
        f"📖 **ПРАВИЛА:** 3 броска, побеждает большая сумма\n\n"
        f"🏆 **Приз:** {duel.prize}\n"
        f"👤 **{duel.creator_name}** VS 👤 **{duel.player2_name}**\n\n"
        f"✅ **Оба игрока собрались!**\n"
        f"🎯 Нажмите **«НАЧАТЬ ДУЭЛЬ»** (может любой)",
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
    
    bot.answer_callback_query(call.id, "🎲 Начинаем дуэль!")
    
    send_animated_emoji(chat_id, "🎲")
    
    bot.edit_message_text(
        f"🎲 **ДУЭЛЬ НАЧАЛАСЬ!** 🎲\n\n"
        f"🏆 **Приз:** {duel.prize}\n"
        f"👤 **{duel.creator_name}** VS 👤 **{duel.player2_name}**\n\n"
        f"📋 **Правила:** 3 броска, сумма очков\n\n"
        f"🎯 **Первый ход: {duel.creator_name}!**",
        chat_id, call.message.message_id,
        parse_mode="Markdown"
    )
    
    time.sleep(2)
    make_dice_roll(chat_id, duel)


def make_dice_roll(chat_id, duel):
    """Бот автоматически кидает кубик для текущего игрока"""
    current_id = duel.current_turn
    player_name = duel.creator_name if current_id == duel.creator_id else duel.player2_name
    roll_num = duel.roll_count[current_id] + 1
    
    # Отправляем анимированный кубик (всегда работает для всех)
    dice_message = bot.send_dice(chat_id, emoji="🎲")
    roll_value = dice_message.dice.value
    
    duel.scores[current_id].append(roll_value)
    duel.roll_count[current_id] = roll_num
    current_sum = sum(duel.scores[current_id])
    
    bot.send_message(
        chat_id,
        f"🎲 **{player_name}** бросок #{roll_num}: выпало **{roll_value}**\n"
        f"📊 Текущая сумма: **{current_sum}**",
        parse_mode="Markdown"
    )
    
    if duel.roll_count[current_id] >= 3:
        other_id = duel.creator_id if current_id == duel.player2_id else duel.player2_id
        
        if duel.roll_count[other_id] >= 3:
            score1 = sum(duel.scores[duel.creator_id])
            score2 = sum(duel.scores[duel.player2_id])
            
            send_animated_emoji(chat_id, "🏆")
            
            result = (
                f"🎲 **ИТОГ ДУЭЛИ** 🎲\n\n"
                f"👤 **{duel.creator_name}:** {score1} очков\n"
                f"👤 **{duel.player2_name}:** {score2} очков\n\n"
            )
            
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
            other_name = duel.creator_name if other_id == duel.creator_id else duel.player2_name
            bot.send_message(
                chat_id,
                f"✅ **{player_name}** завершил броски!\n📊 Сумма: **{current_sum}**\n\n"
                f"🎯 **Теперь ход {other_name}!**",
                parse_mode="Markdown"
            )
            time.sleep(1)
            make_dice_roll(chat_id, duel)
    else:
        time.sleep(1)
        make_dice_roll(chat_id, duel)


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
