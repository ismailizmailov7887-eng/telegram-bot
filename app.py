import os
import threading
import time
import random
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask

# --- НАСТРОЙКИ ---
TOKEN = "8598717015:AAGhbHPy-C9VTkcYb2XSyrJ3a_i83JNojf8"# Или вставьте токен строкой "ВАШ_ТОКЕН"
bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

# Хранилища данных
games = {}
duels = {}

# --- КЛАССЫ ИГР ---

class Game:
    def __init__(self, chat_id, prize, admin_id):
        self.chat_id = chat_id
        self.prize = prize
        self.admin_id = admin_id
        self.players = {}  # {user_id: {'name': name, 'alive': True}}
        self.round = 1
        self.choosing_phase = False
        self.choices = {}
        self.dead_door = None

    def add_player(self, user_id, name):
        if user_id not in self.players:
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
        self.current_turn = None
        self.scores = {}
        self.roll_count = {}

# --- ГЛАВНЫЕ КОМАНДЫ ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    text = (
        "🎮 **ДОБРО ПОЖАЛОВАТЬ В ИГРОВОЙ БОТ!**\n\n"
        "Доступные игры:\n"
        "1️⃣ **3 Двери** — Выживайте, выбирая правильные двери.\n"
        "   • `/start_game` — Запустить сбор игроков.\n"
        "2️⃣ **Дуэль 1v1** — Соревнование на кубиках.\n"
        "   • `/duel` — Создать вызов.\n\n"
        "⚙️ `/stop` — Остановить любую игру в этом чате."
    )
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=['stop', 'stop_game'])
def stop_everything(message):
    cid = message.chat.id
    if cid in games: del games[cid]
    if cid in duels: del duels[cid]
    bot.reply_to(message, "🛑 Все игры в этом чате принудительно остановлены.")

# --- ЛОГИКА: ИГРА 3 ДВЕРИ ---

@bot.message_handler(commands=['start_game'])
def init_doors(message):
    cid = message.chat.id
    if cid in games: return bot.reply_to(message, "⚠️ Игра уже запущена!")
    
    msg = bot.send_message(cid, "🎁 Введите приз для игры '3 Двери':")
    bot.register_next_step_handler(msg, process_doors_prize, cid)

def process_doors_prize(message, cid):
    if not message.text or message.text.startswith('/'): return
    game = Game(cid, message.text, message.from_user.id)
    games[cid] = game
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🚪 ВОЙТИ В ИГРУ", callback_data="join_doors"))
    markup.add(InlineKeyboardButton("▶️ НАЧАТЬ РАУНД 1", callback_data="start_doors_round"))
    
    bot.send_message(cid, f"🚪 **ИГРА: 3 ДВЕРИ**\n\n🏆 Приз: {game.prize}\n👤 Админ: {message.from_user.first_name}\n\nЖмите кнопку, чтобы вступить!", reply_markup=markup)

# --- ЛОГИКА: ДУЭЛЬ ---

@bot.message_handler(commands=['duel'])
def init_duel(message):
    cid = message.chat.id
    if cid in duels: return bot.reply_to(message, "⚠️ Дуэль уже идет.")
    msg = bot.send_message(cid, "💰 Введите приз для дуэли:")
    bot.register_next_step_handler(msg, process_duel_prize, cid)

def process_duel_prize(message, cid):
    if not message.text or message.text.startswith('/'): return
    duel = Duel(message.from_user.id, message.from_user.first_name, message.text)
    duels[cid] = duel
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎲 ПРИНЯТЬ ВЫЗОВ", callback_data="join_duel"),
               InlineKeyboardButton("❌ ОТМЕНА", callback_data="cancel_duel"))
    bot.send_message(cid, f"🎲 **ДУЭЛЬ 1v1**\n\n👤 От: {duel.creator_name}\n🏆 Приз: {duel.prize}\n\nЖдем оппонента...", reply_markup=markup)

# --- ОБРАБОТКА КНОПОК (CALLBACK) ---

@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    cid, uid = call.message.chat.id, call.from_user.id

    # Вход в 3 двери
    if call.data == "join_doors":
        if cid in games and games[cid].add_player(uid, call.from_user.first_name):
            bot.answer_callback_query(call.id, "✅ Вы в игре!")
        else:
            bot.answer_callback_query(call.id, "Вы уже в списке или игра не найдена.")

    # Старт раунда 3 двери
    elif call.data == "start_doors_round":
        game = games.get(cid)
        if not game or uid != game.admin_id: 
            return bot.answer_callback_query(call.id, "Только админ может начать!")
        
        alive = game.get_alive_players()
        if len(alive) < 1: return bot.answer_callback_query(call.id, "Нужно минимум 1 игрок!")
        
        game.choosing_phase = True
        game.choices = {}
        game.dead_door = random.randint(1, 3)
        
        markup = InlineKeyboardMarkup()
        markup.row(InlineKeyboardButton("🚪 1", callback_data="door_1"),
                   InlineKeyboardButton("🚪 2", callback_data="door_2"),
                   InlineKeyboardButton("🚪 3", callback_data="door_3"))
        
        bot.send_message(cid, f"🚀 **РАУНД {game.round}**\nОдна из дверей ведет к вылету!\n\nУ игроков 30 секунд на выбор...", reply_markup=markup)
        threading.Timer(30, finish_doors_round, [cid]).start()

    # Выбор двери
    elif call.data.startswith("door_"):
        game = games.get(cid)
        if not game or not game.choosing_phase: return
        if uid not in game.get_alive_players(): return bot.answer_callback_query(call.id, "Вы не участвуете!")
        
        door = int(call.data.split("_")[1])
        game.choices[uid] = door
        bot.answer_callback_query(call.id, f"Вы выбрали дверь №{door}")

    # Логика дуэли (вход/отмена)
    elif call.data == "join_duel":
        d = duels.get(cid)
        if d and not d.started and uid != d.creator_id:
            d.player2_id, d.player2_name = uid, call.from_user.first_name
            d.started, d.current_turn = True, d.creator_id
            d.scores = {d.creator_id: [], uid: []}
            d.roll_count = {d.creator_id: 0, uid: 0}
            bot.edit_message_text(f"🎲 **ДУЭЛЬ НАЧАТА!**\n\n{d.creator_name} VS {d.player2_name}\n🎯 Ходит: {d.creator_name}\nКидайте /dice!", cid, call.message.message_id)
    
    elif call.data == "cancel_duel":
        if cid in duels and duels[cid].creator_id == uid:
            del duels[cid]
            bot.edit_message_text("❌ Дуэль отменена.", cid, call.message.message_id)

# --- ЛОГИКА ЗАВЕРШЕНИЯ РАУНДА 3 ДВЕРИ ---

def finish_doors_round(cid):
    game = games.get(cid)
    if not game: return
    game.choosing_phase = False
    
    dead = game.dead_door
    results_text = f"⌛️ **ВРЕМЯ ВЫШЛО!**\n\nСмертельная дверь была: 🚪 **{dead}**\n\n"
    
    for uid, data in list(game.players.items()):
        if not data['alive']: continue
        choice = game.choices.get(uid)
        if choice == dead or choice is None:
            game.players[uid]['alive'] = False
            results_text += f"💀 {data['name']} — ВЫЛЕТ\n"
        else:
            results_text += f"✅ {data['name']} — ЖИВ\n"
    
    alive_now = game.get_alive_players()
    if len(alive_now) == 0:
        results_text += f"\n😢 Все игроки выбыли. Игра окончена!"
        del games[cid]
    elif len(alive_now) == 1:
        winner = list(alive_now.values())[0]['name']
        results_text += f"\n🏆 **ПОБЕДИТЕЛЬ: {winner}**\nПриз: {game.prize}"
        del games[cid]
    else:
        game.round += 1
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("▶️ СЛЕДУЮЩИЙ РАУНД", callback_data="start_doors_round"))
        bot.send_message(cid, results_text, reply_markup=markup)
        return

    bot.send_message(cid, results_text)

# --- ЛОГИКА КУБИКОВ (ДУЭЛЬ) ---

@bot.message_handler(content_types=['dice', 'text'])
def handle_duel_action(message):
    cid, uid = message.chat.id, message.from_user.id
    if cid not in duels: return
    d = duels[cid]
    if not d.started or d.current_turn != uid: return

    is_dice = False
    if message.dice and message.dice.emoji == "🎲":
        val, is_dice = message.dice.value, True
    elif message.text and message.text.split('@')[0].lower() == '/dice':
        msg = bot.send_dice(cid, reply_to_message_id=message.message_id)
        val, is_dice = msg.dice.value, True
    
    if is_dice:
        d.scores[uid].append(val)
        d.roll_count[uid] += 1
        time.sleep(3.5)
        bot.reply_to(message, f"🎲 Выпало: {val} | Сумма: {sum(d.scores[uid])}")
        
        if d.roll_count[uid] >= 3:
            if uid == d.creator_id:
                d.current_turn = d.player2_id
                bot.send_message(cid, f"🎯 Очередь {d.player2_name}!")
            else:
                s1, s2 = sum(d.scores[d.creator_id]), sum(d.scores[d.player2_id])
                res = f"🏁 **ФИНАЛ**\n{d.creator_name}: {s1}\n{d.player2_name}: {s2}\n\n"
                res += f"🏆 Победил {d.creator_name if s1 > s2 else d.player2_name}!" if s1 != s2 else "🤝 Ничья!"
                bot.send_message(cid, res)
                del duels[cid]

# --- ЗАПУСК ---

if __name__ == '__main__':
    bot.set_my_commands([
        BotCommand("start", "Меню"),
        BotCommand("duel", "Дуэль"),
        BotCommand("start_game", "3 Двери"),
        BotCommand("stop", "Остановить")
    ])
    threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True)).start()
    app.run(host='0.0.0.0', port=5000)
