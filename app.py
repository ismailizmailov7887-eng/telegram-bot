import os
import threading
import time
import random
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask

# ================= НАСТРОЙКИ =================
TOKEN = "8598717015:AAGhbHPy-C9VTkcYb2XSyrJ3a_i83JNojf8"
MAIN_CHAT = "https://t.me/Ton_dly_svoih"
MAIN_CHANNEL = "https://t.me/Ton_dly_svoih"

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=20)
app = Flask(__name__)

games = {}  # Групповые игры
duels = {}  # Дуэли 1v1

# ================= КЛАССЫ СИСТЕМЫ =================
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
        self.final_mode = False

    def add_player(self, user_id, name):
        if user_id not in self.players:
            self.players[user_id] = {'name': name, 'alive': True, 'rps_choice': None, 'rps_wins': 0}
            return True
        return False

    def get_alive_players(self):
        return {uid: data for uid, data in self.players.items() if data['alive']}

class Duel:
    def __init__(self, creator_id, creator_name):
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
        admins = bot.get_chat_administrators(chat_id)
        return any(admin.user.id == user_id for admin in admins)
    except:
        return False

# ================= БАЗОВЫЕ КОМАНДЫ =================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    text = (
        "✨ **ДОБРО ПОЖАЛОВАТЬ В ИГРОВОЙ ХАБ!** ✨\n\n"
        "Я — твой проводник в мир азарта. Здесь всё по-честному, быстро и красиво. "
        "Готов испытать свою удачу? 🎲\n\n"
        "🚀 **ЧТО ТУТ ЕСТЬ?**\n"
        "⚔️ **Дуэли 1v1** — бросай вызов другу. Бот сам считает очки кубиков!\n"
        "🌋 **Выживание** — массовая игра в комнаты. Выживет только один.\n\n"
        "🔗 **НАШИ РЕСУРСЫ:**\n"
        f"💠 [Основной канал]({MAIN_CHANNEL})\n"
        f"💬 [Наш уютный чат]({MAIN_CHAT})\n\n"
        "Жми /help, чтобы узнать правила!"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(commands=['help'])
def help_rules(message):
    text = (
        "📖 **КОДЕКС ИГРОКА**\n\n"
        "🎲 **ДУЭЛЬ (/duel):**\n"
        "Жди оппонента → Бросайте кубики. Бот сам считает сумму 3-х бросков. Победитель тот, у кого больше очков.\n\n"
        "🏆 **ВЫЖИВАНИЕ (/start_game):**\n"
        "Только для админов. Выбирай одну из 3-х дверей. В одной из них — ловушка! Кто остался последним — забирает приз.\n\n"
        "🛠 **АДМИНАМ:**\n"
        "**/admin** — управление паузой и сбросом игры."
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# ================= ЛОГИКА ДУЭЛЕЙ (АВТО-СЧЕТ) =================
@bot.message_handler(commands=['duel'])
def create_duel_cmd(message):
    chat_id = message.chat.id
    if chat_id in duels:
        bot.reply_to(message, "⏳ Дуэль уже идет, дождись финала!")
        return

    duel = Duel(message.from_user.id, message.from_user.first_name)
    duels[chat_id] = duel
    
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("⚔️ ПРИНЯТЬ ВЫЗОВ", callback_data="join_duel"))
    bot.send_message(chat_id, f"⚔️ **ВЫЗОВ БРОШЕН!**\n\nИгрок **{duel.creator_name}** ищет оппонента.\nРискнешь сразиться?", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "join_duel")
def join_duel_callback(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    if chat_id not in duels: return
    duel = duels[chat_id]
    
    if user_id == duel.creator_id:
        bot.answer_callback_query(call.id, "Нельзя играть с самим собой! 🤔", show_alert=True)
        return
    
    duel.player2_id = user_id
    duel.player2_name = call.from_user.first_name
    duel.started = True
    duel.scores = {duel.creator_id: 0, duel.player2_id: 0}
    duel.turn_count = {duel.creator_id: 0, duel.player2_id: 0}
    
    bot.edit_message_text(f"🏁 **ДУЭЛЬ: {duel.creator_name} VS {duel.player2_name}**\n\nПервым бросает {duel.creator_name}...", chat_id, call.message.message_id)
    time.sleep(1.5)
    run_dice_step(chat_id, duel)

def run_dice_step(chat_id, duel):
    current_id = duel.current_turn
    name = duel.creator_name if current_id == duel.creator_id else duel.player2_name
    
    bot.send_message(chat_id, f"🎲 Ход игрока **{name}**...")
    dice_msg = bot.send_dice(chat_id, emoji='🎲')
    
    duel.scores[current_id] += dice_msg.dice.value
    duel.turn_count[current_id] += 1
    
    threading.Timer(3.5, check_duel_status, args=[chat_id, duel]).start()

def check_duel_status(chat_id, duel):
    p1, p2 = duel.creator_id, duel.player2_id
    if duel.turn_count[p1] == 3 and duel.turn_count[p2] == 3:
        s1, s2 = duel.scores[p1], duel.scores[p2]
        res = f"🏁 **ИТОГИ ДУЭЛИ**\n\n👤 {duel.creator_name}: `{s1}`\n👤 {duel.player2_name}: `{s2}`\n\n"
        if s1 > s2: res += f"🏆 Победитель: **{duel.creator_name}**!"
        elif s2 > s1: res += f"🏆 Победитель: **{duel.player2_name}**!"
        else: res += "🤝 Ничья!"
        bot.send_message(chat_id, res, parse_mode="Markdown")
        del duels[chat_id]
    else:
        duel.current_turn = p2 if duel.current_turn == p1 else p1
        run_dice_step(chat_id, duel)

# ================= ГРУППОВАЯ ИГРА (КОМНАТЫ) =================
@bot.message_handler(commands=['start_game'])
def cmd_start_group(message):
    if not is_admin(message.chat.id, message.from_user.id): return
    msg = bot.send_message(message.chat.id, "💰 **ПРИЗОВОЙ ФОНД:**\nВведите награду для победителя:")
    bot.register_next_step_handler(msg, setup_group_game, message.chat.id, message.from_user.id)

def setup_group_game(message, chat_id, admin_id):
    prize = message.text
    games[chat_id] = Game(chat_id, prize, admin_id)
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🎟 УЧАСТВОВАТЬ", callback_data="join_game"), InlineKeyboardButton("🏁 СТАРТ", callback_data="start_rooms"))
    bot.send_message(chat_id, f"🏟 **АРЕНА ВЫЖИВАНИЯ**\n\n🏆 Приз: `{prize}`\n👥 Участников: 0\n\nЖми кнопку, чтобы вступить!", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "join_game")
def join_group_callback(call):
    chat_id = call.message.chat.id
    if chat_id not in games: return
    game = games[chat_id]
    if game.add_player(call.from_user.id, call.from_user.first_name):
        bot.answer_callback_query(call.id, "Ты в игре! 🍀")
        bot.edit_message_text(f"🏟 **АРЕНА ВЫЖИВАНИЯ**\n\n🏆 Приз: `{game.prize}`\n👥 Участников: {len(game.players)}\n\nОжидаем старта...", chat_id, call.message.message_id, 
                              reply_markup=call.message.reply_markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "start_rooms")
def start_rooms_callback(call):
    chat_id = call.message.chat.id
    if chat_id not in games or not is_admin(chat_id, call.from_user.id): return
    if len(games[chat_id].players) < 2:
        bot.answer_callback_query(call.id, "Нужно минимум 2 игрока! 👥", show_alert=True)
        return
    start_round_cycle(chat_id)

def start_round_cycle(chat_id):
    game = games.get(chat_id)
    if not game or game.paused: return
    
    game.choosing_phase = True
    game.choices = {}
    game.dead_room = random.choice([1, 2, 3])
    
    markup = InlineKeyboardMarkup().add(
        InlineKeyboardButton("🚪 1", callback_data="room_1"),
        InlineKeyboardButton("🚪 2", callback_data="room_2"),
        InlineKeyboardButton("🚪 3", callback_data="room_3")
    )
    bot.send_message(chat_id, f"🟥 **РАУНД {game.round}**\n\nВыбери дверь. В одной из них ловушка! 💀\nУ тебя **20 секунд**.", reply_markup=markup, parse_mode="Markdown")
    threading.Timer(20, finish_round_cycle, args=[chat_id]).start()

@bot.callback_query_handler(func=lambda call: call.data.startswith("room_"))
def pick_room_callback(call):
    chat_id = call.message.chat.id
    uid = call.from_user.id
    if chat_id not in games: return
    game = games[chat_id]
    if game.choosing_phase and uid in game.get_alive_players() and uid not in game.choices:
        game.choices[uid] = int(call.data.split("_")[1])
        bot.answer_callback_query(call.id, f"Ты за дверью {game.choices[uid]}...")

def finish_round_cycle(chat_id):
    game = games.get(chat_id)
    if not game: return
    game.choosing_phase = False
    alive = game.get_alive_players()
    
    # Кто не выбрал - рандом
    for uid in alive:
        if uid not in game.choices: game.choices[uid] = random.choice([1, 2, 3])

    res = f"⌛ **РЕЗУЛЬТАТЫ РАУНДА {game.round}:**\n\n"
    for r in [1, 2, 3]:
        players = [game.players[uid]['name'] for uid, c in game.choices.items() if c == r]
        icon = "🔥" if r == game.dead_room else "✅"
        res += f"🚪 **Дверь {r}** {icon}\n"
        for name in players:
            if r == game.dead_room and random.random() < 0.5:
                res += f"  └ 💀 {name}\n"
                for uid, data in game.players.items():
                    if data['name'] == name: data['alive'] = False
            else:
                res += f"  └ ✨ {name}\n"
    
    bot.send_message(chat_id, res, parse_mode="Markdown")
    
    still_alive = game.get_alive_players()
    if len(still_alive) > 1:
        game.round += 1
        time.sleep(5)
        start_round_cycle(chat_id)
    elif len(still_alive) == 1:
        winner = list(still_alive.values())[0]['name']
        bot.send_message(chat_id, f"🏆 **ПОБЕДА!**\nПобедитель: {winner}\nПриз: `{game.prize}`")
        del games[chat_id]
    else:
        bot.send_message(chat_id, "💀 Все погибли. Приз никому не достался.")
        del games[chat_id]

# ================= АДМИН ПАНЕЛЬ =================
@bot.message_handler(commands=['admin'])
def admin_cmd(message):
    if not is_admin(message.chat.id, message.from_user.id): return
    markup = InlineKeyboardMarkup().add(
        InlineKeyboardButton("⏸ Пауза/Пуск", callback_data="adm_pause"),
        InlineKeyboardButton("🛑 Сброс", callback_data="adm_stop")
    )
    bot.send_message(message.chat.id, "🛠 **АДМИН-ПАНЕЛЬ**", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_"))
def admin_callback(call):
    chat_id = call.message.chat.id
    if not is_admin(chat_id, call.from_user.id): return
    if call.data == "adm_pause" and chat_id in games:
        games[chat_id].paused = not games[chat_id].paused
        bot.send_message(chat_id, f"📢 Статус игры: **{'ПАУЗА' if games[chat_id].paused else 'АКТИВНА'}**")
    elif call.data == "adm_stop":
        if chat_id in games: del games[chat_id]
        if chat_id in duels: del duels[chat_id]
        bot.send_message(chat_id, "🛑 Игры остановлены админом.")

# ================= ЗАПУСК =================
def run_bot():
    bot.set_my_commands([
        BotCommand("start", "🏠 Главная"),
        BotCommand("duel", "🎲 Дуэль 1v1"),
        BotCommand("start_game", "🏆 Выживание"),
        BotCommand("admin", "🛠 Админка"),
        BotCommand("help", "📖 Правила")
    ])
    bot.infinity_polling()

if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
