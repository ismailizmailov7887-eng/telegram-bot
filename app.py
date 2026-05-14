import os
import threading
import time
import random
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask

# --- НАСТРОЙКИ ---
TOKEN = "8598717015:AAELFLybH7mxCCx02t23f9ufHYZI90Zolw4"
bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

# Словари для хранения комнат (chat_id является ключом)
games = {}
duels = {}

# --- КЛАССЫ ДЛЯ ЛОГИКИ КОМНАТ ---

class GameDoors:
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

class DuelRoom:
    def __init__(self, creator_id, creator_name, prize):
        self.creator_id, self.creator_name, self.prize = creator_id, creator_name, prize
        self.player2_id = self.player2_name = None
        self.started = False
        self.current_turn = None
        self.scores = {}
        self.roll_count = {}

# --- ОСНОВНЫЕ КОМАНДЫ ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    rules = (
        "🎮 **ДОБРО ПОЖАЛОВАТЬ!**\n\n"
        "📜 **ПРАВИЛА ИГР:**\n\n"
        "🎲 **Дуэль 1v1:**\n"
        "1. Создаете дуэль командой /duel.\n"
        "2. Оппонент жмет кнопку 'Принять'.\n"
        "3. Каждый по очереди кидает кубик (/dice) 3 раза.\n"
        "4. Бот суммирует очки и объявляет победителя.\n\n"
        "🚪 **3 Двери:**\n"
        "1. Админ запускает сбор (/start_game).\n"
        "2. Игроки вступают в группу.\n"
        "3. В каждом раунде нужно выбрать одну из 3-х дверей.\n"
        "4. За одной из дверей — ловушка (вылет)! Последний выживший забирает приз.\n\n"
        "🛑 **Команды управления:**\n"
        "/stop — Остановить все игры в этом чате."
    )
    bot.reply_to(message, rules, parse_mode="Markdown")

@bot.message_handler(commands=['stop', 'stop_game'])
def stop_all(message):
    cid = message.chat.id
    if cid in games: del games[cid]
    if cid in duels: del duels[cid]
    bot.reply_to(message, "🛑 Комната очищена. Все игры остановлены.")

# --- ЛОГИКА: 3 ДВЕРИ ---

@bot.message_handler(commands=['start_game'])
def cmd_start_doors(message):
    cid = message.chat.id
    if cid in games: return bot.reply_to(message, "⚠️ Игра уже запущена!")
    msg = bot.send_message(cid, "🎁 Введите название приза для игры '3 Двери':")
    bot.register_next_step_handler(msg, process_doors_prize, cid)

def process_doors_prize(message, cid):
    if not message.text or message.text.startswith('/'): return
    games[cid] = GameDoors(cid, message.text, message.from_user.id)
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🚪 ВСТУПИТЬ", callback_data="join_doors"))
    markup.add(InlineKeyboardButton("▶️ НАЧАТЬ ИГРУ", callback_data="start_doors_round"))
    
    bot.send_message(cid, f"🚪 **ИГРА 3 ДВЕРИ**\n\n🏆 Приз: {message.text}\n\nНажмите кнопку ниже, чтобы вступить в игру!", reply_markup=markup)

# --- ЛОГИКА: ДУЭЛЬ ---

@bot.message_handler(commands=['duel'])
def cmd_start_duel(message):
    cid = message.chat.id
    if cid in duels: return bot.reply_to(message, "⚠️ Дуэль уже создана в этом чате.")
    msg = bot.send_message(cid, "💰 Напишите приз дуэли:")
    bot.register_next_step_handler(msg, process_duel_prize, cid)

def process_duel_prize(message, cid):
    if not message.text or message.text.startswith('/'): return
    duels[cid] = DuelRoom(message.from_user.id, message.from_user.first_name, message.text)
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎲 ПРИНЯТЬ ВЫЗОВ", callback_data="join_duel"),
               InlineKeyboardButton("❌ ОТМЕНА", callback_data="cancel_duel"))
    bot.send_message(cid, f"🎲 **ВЫЗОВ НА ДУЭЛЬ**\n\n👤 Создатель: {message.from_user.first_name}\n🏆 Приз: {message.text}\n\nЖдем второго игрока...", reply_markup=markup)

# --- ОБРАБОТКА КНОПОК (CALLBACK) ---

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    cid, uid = call.message.chat.id, call.from_user.id

    # Вход в 3 двери
    if call.data == "join_doors":
        if cid in games and games[cid].add_player(uid, call.from_user.first_name):
            bot.answer_callback_query(call.id, "✅ Вы в игре!")
        else:
            bot.answer_callback_query(call.id, "❌ Вы уже вошли или игра закрыта.")

    # Старт раунда дверей
    elif call.data == "start_doors_round":
        game = games.get(cid)
        if not game or uid != game.admin_id: 
            return bot.answer_callback_query(call.id, "Только админ может запустить!")
        
        alive = game.get_alive_players()
        if len(alive) < 1: return bot.answer_callback_query(call.id, "Недостаточно игроков!")
        
        game.choosing_phase, game.choices = True, {}
        game.dead_door = random.randint(1, 3)
        
        markup = InlineKeyboardMarkup().row(
            InlineKeyboardButton("🚪 1", callback_data="door_1"),
            InlineKeyboardButton("🚪 2", callback_data="door_2"),
            InlineKeyboardButton("🚪 3", callback_data="door_3")
        )
        bot.send_message(cid, f"🚀 **РАУНД {game.round}**\nВыберите дверь! У вас 20 секунд.", reply_markup=markup)
        threading.Timer(20.0, finish_doors_round, [cid]).start()

    # Выбор двери
    elif call.data.startswith("door_"):
        game = games.get(cid)
        if game and game.choosing_phase and uid in game.get_alive_players():
            game.choices[uid] = int(call.data.split("_")[1])
            bot.answer_callback_query(call.id, "Выбор сделан!")

    # Кнопки дуэли
    elif call.data == "join_duel":
        d = duels.get(cid)
        if d and not d.started and uid != d.creator_id:
            d.player2_id, d.player2_name = uid, call.from_user.first_name
            d.started, d.current_turn = True, d.creator_id
            d.scores = {d.creator_id: [], uid: []}
            d.roll_count = {d.creator_id: 0, uid: 0}
            bot.edit_message_text(f"🎲 **ДУЭЛЬ НАЧАТА!**\n\n{d.creator_name} 🆚 {d.player2_name}\n\n🎯 Первым ходит {d.creator_name}.\nОтправьте /dice!", cid, call.message.message_id)

    elif call.data == "cancel_duel":
        if cid in duels and duels[cid].creator_id == uid:
            del duels[cid]
            bot.edit_message_text("❌ Дуэль отменена.", cid, call.message.message_id)

# --- ЗАВЕРШЕНИЕ РАУНДА 3 ДВЕРИ ---

def finish_doors_round(cid):
    game = games.get(cid)
    if not game: return
    game.choosing_phase = False
    dead = game.dead_door
    
    text = f"⌛️ **ВРЕМЯ ВЫШЛО!**\n\nСмертельная дверь была: 🚪 **{dead}**\n\n"
    for uid, data in list(game.players.items()):
        if not data['alive']: continue
        choice = game.choices.get(uid)
        if choice == dead or choice is None:
            game.players[uid]['alive'] = False
            text += f"💀 {data['name']} — ВЫЛЕТ\n"
        else:
            text += f"✅ {data['name']} — ЖИВ\n"
    
    alive = game.get_alive_players()
    if not alive:
        text += "\nВсе проиграли! Игра окончена."
        del games[cid]
    elif len(alive) == 1:
        winner = list(alive.values())[0]['name']
        text += f"\n🏆 **ПОБЕДИТЕЛЬ: {winner}**\nПриз: {game.prize}"
        del games[cid]
    else:
        game.round += 1
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("➡️ СЛЕДУЮЩИЙ РАУНД", callback_data="start_doors_round"))
        bot.send_message(cid, text, reply_markup=markup)
        return
    bot.send_message(cid, text)

# --- ЛОГИКА КУБИКОВ (ДУЭЛЬ) ---

@bot.message_handler(content_types=['dice', 'text'])
def handle_dice_action(message):
    cid, uid = message.chat.id, message.from_user.id
    if cid not in duels: return
    d = duels[cid]
    if not d.started or d.current_turn != uid: return

    is_valid = False
    if message.dice and message.dice.emoji == "🎲":
        val, is_valid = message.dice.value, True
    elif message.text and message.text.split('@')[0].lower() == '/dice':
        res = bot.send_dice(cid, reply_to_message_id=message.message_id)
        val, is_valid = res.dice.value, True
    
    if is_valid:
        d.scores[uid].append(val)
        d.roll_count[uid] += 1
        time.sleep(3.5)
        bot.reply_to(message, f"🎲 Выпало: {val} | Сумма: {sum(d.scores[uid])}")
        
        if d.roll_count[uid] >= 3:
            if uid == d.creator_id:
                d.current_turn = d.player2_id
                bot.send_message(cid, f"🎯 Твой ход, {d.player2_name}! Кидай /dice")
            else:
                s1, s2 = sum(d.scores[d.creator_id]), sum(d.scores[d.player2_id])
                res = f"🏁 **ФИНАЛ**\n{d.creator_name}: {s1}\n{d.player2_name}: {s2}\n\n"
                if s1 > s2: res += f"🏆 Победитель: {d.creator_name}!"
                elif s2 > s1: res += f"🏆 Победитель: {d.player2_name}!"
                else: res += "🤝 Ничья!"
                bot.send_message(cid, res)
                del duels[cid]

# --- ЗАПУСК ---

@app.route('/')
def health(): return "OK", 200

if __name__ == '__main__':
    bot.set_my_commands([
        BotCommand("start", "Инфо/Правила"),
        BotCommand("duel", "Создать дуэль 1v1"),
        BotCommand("start_game", "Игра 3 Двери"),
        BotCommand("stop", "Остановить игры")
    ])
    threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True)).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
