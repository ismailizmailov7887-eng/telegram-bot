import telebot
import random
import time
import threading
import os
from telebot import types
from flask import Flask

# --- КОНФИГУРАЦИЯ ---
TOKEN = "8598717015:AAGhbHPy-C9VTkcYb2XSyrJ3a_i83JNojf8"
bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=10)
app = Flask(__name__)

games = {}  # Для командных игр {chat_id: Game}
duels = {}  # Для дуэлей {chat_id: Duel}

def escape(text):
    """Экранирование символов для MarkdownV2"""
    chars = '_*[]()~`>#+-=|{}.!'
    for char in chars:
        text = str(text).replace(char, f'\\{char}')
    return text

# --- КЛАССЫ ЛОГИКИ ---

class Game:
    def __init__(self, chat_id, admin_id, prize):
        self.chat_id = chat_id
        self.admin_id = admin_id
        self.prize = prize
        self.players = {} # {user_id: name}
        self.status = "LOBBY" # LOBBY, PLAYING, FINISHED, RPS
        self.round = 1
        self.max_players = 30
        self.choices = {} # {user_id: door_num}
        self.rps_data = {} # Для финальной битвы

class Duel:
    def __init__(self, chat_id, creator_id, creator_name):
        self.chat_id = chat_id
        self.p1 = {"id": creator_id, "name": creator_name, "score": 0, "rolls": []}
        self.p2 = None
        self.status = "WAITING"
        self.created_at = time.time()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def is_admin(chat_id, user_id):
    if chat_id > 0: return True # Личка
    admins = bot.get_chat_administrators(chat_id)
    return any(admin.user.id == user_id for admin in admins)

def get_progress_bar(seconds, total=20):
    filled = int((seconds / total) * 10)
    bar = "█" * filled + "░" * (10 - filled)
    return f"`{bar}` {seconds} секунд"

# --- ОБРАБОТЧИКИ КОМАНД ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    text = (
        "✨ *Добро пожаловать в Игровой Бот\\!* ✨\n\n"
        "🎮 *Доступные команды:*\n"
        "┣ `/duel` — Вызвать кого\\-то на дуэль 🎲\n"
        "┣ `/start_game` — Запустить игру в двери 🚪 \\(Админ\\)\n"
        "┣ `/help` — Правила игр 📜\n"
        "┗ `/cancel_duel` — Отмена дуэли ❌"
    )
    bot.send_message(message.chat.id, text, parse_mode='MarkdownV2')

@bot.message_handler(commands=['help'])
def send_help(message):
    text = (
        "📖 *Правила игр:*\n\n"
        "🚪 *3 Двери:* Админ запускает игру\\. Игроки заходят в лобби\\. "
        "В каждом раунде нужно выбрать одну из 3 дверей\\. Одна из них — ловушка \\(65% шанс гибели\\)\\. "
        "Последние двое сразятся в Камень\\-Ножницы\\-Бумага\\!\n\n"
        "🎲 *Дуэль:* Бросаем кубики 3 раза\\. У кого сумма больше — тот победил\\! ✨"
    )
    bot.send_message(message.chat.id, text, parse_mode='MarkdownV2')

# --- ЛОГИКА ДУЭЛЕЙ ---

@bot.message_handler(commands=['duel'])
def start_duel(message):
    chat_id = message.chat.id
    if chat_id in duels:
        bot.reply_to(message, "❌ В этом чате уже ожидается или идет дуэль!")
        return

    duels[chat_id] = Duel(chat_id, message.from_user.id, message.from_user.first_name)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🤝 ПРИСОЕДИНИТЬСЯ", callback_data="join_duel"))
    
    msg = bot.send_message(
        chat_id, 
        f"🎲 **{escape(message.from_user.first_name)}** бросает вызов\\!\n"
        f"⏰ У оппонента есть 60 секунд, чтобы принять вызов\\.",
        parse_mode='MarkdownV2', reply_markup=markup
    )
    
    # Таймер авто-закрытия
    threading.Thread(target=duel_timeout, args=(chat_id, msg.message_id)).start()

def duel_timeout(chat_id, msg_id):
    time.sleep(60)
    if chat_id in duels and duels[chat_id].status == "WAITING":
        bot.edit_message_text("❌ Срок ожидания дуэли истек\\. Никто не пришел\\...", chat_id, msg_id, parse_mode='MarkdownV2')
        duels.pop(chat_id, None)

@bot.message_handler(commands=['cancel_duel'])
def cancel_duel(message):
    chat_id = message.chat.id
    if chat_id in duels:
        d = duels[chat_id]
        if message.from_user.id in [d.p1['id'], (d.p2['id'] if d.p2 else None)]:
            duels.pop(chat_id)
            bot.send_message(chat_id, "❌ Дуэль отменена участником\\.", parse_mode='MarkdownV2')

# --- ЛОГИКА КОМАНДНОЙ ИГРЫ ---

@bot.message_handler(commands=['start_game'])
def init_game(message):
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "❌ Только **админ** может запускать игру\\!", parse_mode='MarkdownV2')
        return
    
    msg = bot.send_message(message.chat.id, "💎 Введите **ПРИЗ** для победителя:", parse_mode='MarkdownV2')
    bot.register_next_step_handler(msg, process_prize_step)

def process_prize_step(message):
    prize = message.text
    chat_id = message.chat.id
    games[chat_id] = Game(chat_id, message.from_user.id, prize)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🚪 ПРИСОЕДИНИТЬСЯ", callback_data="join_game"))
    markup.add(types.InlineKeyboardButton("▶️ НАЧАТЬ ИГРУ", callback_data="start_game_now"))
    
    bot.send_message(
        chat_id,
        f"✨ *ИГРА НАЧИНАЕТСЯ\\!* ✨\n\n"
        f"💎 Приз: *{escape(prize)}*\n"
        f"👥 Игроков: 0/30\n\n"
        f"Жмите кнопку ниже, чтобы войти в лобби\\!",
        parse_mode='MarkdownV2', reply_markup=markup
    )

@bot.message_handler(commands=['stop_game'])
def stop_game(message):
    if is_admin(message.chat.id, message.from_user.id):
        games.pop(message.chat.id, None)
        bot.send_message(message.chat.id, "❌ Игра принудительно остановлена\\.", parse_mode='MarkdownV2')

# --- CALLBACK HANDLERS ---

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    uid = call.from_user.id
    cid = call.message.chat.id
    name = call.from_user.first_name

    # --- ДУЭЛЬ ---
    if call.data == "join_duel":
        if cid in duels and duels[cid].status == "WAITING":
            if duels[cid].p1['id'] == uid:
                bot.answer_callback_query(call.id, "Вы уже создатель!")
                return
            duels[cid].p2 = {"id": uid, "name": name, "score": 0, "rolls": []}
            duels[cid].status = "READY"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🎲 НАЧАТЬ ДУЭЛЬ", callback_data="run_duel"))
            bot.edit_message_text(
                f"🎲 Дуэль: **{escape(duels[cid].p1['name'])}** vs **{escape(name)}**\n"
                f"Нажмите кнопку, чтобы бросить кубики\\!",
                cid, call.message.message_id, parse_mode='MarkdownV2', reply_markup=markup
            )

    elif call.data == "run_duel":
        if cid in duels and duels[cid].status == "READY":
            d = duels[cid]
            if uid not in [d.p1['id'], d.p2['id']]: return
            duels.pop(cid) # Удаляем из активных
            threading.Thread(target=execute_duel, args=(cid, d)).start()

    # --- КОМАНДНАЯ ИГРА ---
    elif call.data == "join_game":
        if cid in games and games[cid].status == "LOBBY":
            if len(games[cid].players) >= 30:
                bot.answer_callback_query(call.id, "Лобби полно!")
                return
            games[cid].players[uid] = name
            bot.answer_callback_query(call.id, "Вы в игре! ✅")
            
    elif call.data == "start_game_now":
        if cid in games and games[cid].status == "LOBBY":
            if uid != games[cid].admin_id:
                bot.answer_callback_query(call.id, "Только админ может запустить!")
                return
            if len(games[cid].players) < 2:
                bot.answer_callback_query(call.id, "Нужно минимум 2 игрока!")
                return
            games[cid].status = "PLAYING"
            run_door_round(cid)

    elif call.data.startswith("door_"):
        if cid in games and games[cid].status == "PLAYING":
            door = int(call.data.split("_")[1])
            if uid in games[cid].players:
                games[cid].choices[uid] = door
                bot.answer_callback_query(call.id, f"Вы выбрали дверь {door} 🚪")

    elif call.data.startswith("rps_"):
        if cid in games and games[cid].status == "RPS":
            choice = call.data.split("_")[1]
            if uid in games[cid].players:
                games[cid].rps_data[uid] = choice
                bot.answer_callback_query(call.id, "Выбор сделан!")

# --- ИГРОВЫЕ ЦИКЛЫ ---

def execute_duel(cid, d):
    bot.send_message(cid, f"🔥 Дуэль начинается между **{escape(d.p1['name'])}** и **{escape(d.p2['name'])}**\\!", parse_mode='MarkdownV2')
    
    for i in range(1, 4):
        time.sleep(1)
        for player in [d.p1, d.p2]:
            msg = bot.send_dice(cid)
            val = msg.dice.value
            player['rolls'].append(val)
            player['score'] += val
            bot.send_message(cid, f"🎯 **{escape(player['name'])}** бросок #{i}: выпало **{val}**", parse_mode='MarkdownV2')
            time.sleep(3)
    
    res = (f"🏆 *ИТОГИ ДУЭЛИ* 🏆\n\n"
           f"👤 **{escape(d.p1['name'])}**: {d.p1['score']} очков\n"
           f"👤 **{escape(d.p2['name'])}**: {d.p2['score']} очков\n\n")
    
    if d.p1['score'] > d.p2['score']:
        res += f"👑 Победитель: **{escape(d.p1['name'])}**"
    elif d.p2['score'] > d.p1['score']:
        res += f"👑 Победитель: **{escape(d.p2['name'])}**"
    else:
        res += "🤝 *Ничья!*"
    
    bot.send_message(cid, res, parse_mode='MarkdownV2')

def run_door_round(cid):
    if cid not in games: return
    game = games[cid]
    game.choices = {}
    
    if len(game.players) <= 2:
        start_rps_finale(cid)
        return

    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("🚪 1", callback_data="door_1"),
        types.InlineKeyboardButton("🚪 2", callback_data="door_2"),
        types.InlineKeyboardButton("🚪 3", callback_data="door_3")
    )
    
    msg = bot.send_message(cid, f"🚪 *РАУНД {game.round}*\n\nВыберите дверь\\! У вас 20 секунд\\.\n{get_progress_bar(20)}", 
                          parse_mode='MarkdownV2', reply_markup=markup)
    
    for i in range(15, -1, -5):
        time.sleep(5)
        if cid not in games: return
        bot.edit_message_text(f"🚪 *РАУНД {game.round}*\n\nВыберите дверь\\! У вас {i} секунд\\.\n{get_progress_bar(i)}", 
                             cid, msg.message_id, parse_mode='MarkdownV2', reply_markup=markup)

    # Обработка результатов
    trap_door = random.randint(1, 3)
    dead_players = []
    
    for pid, name in list(game.players.items()):
        choice = game.choices.get(pid, random.randint(1, 3)) # Автовыбор
        if choice == trap_door:
            if random.random() < 0.65: # 65% шанс смерти
                dead_players.append(name)
                game.players.pop(pid)
    
    status_text = f"⌛ *РЕЗУЛЬТАТЫ РАУНДА {game.round}*\n\n"
    status_text += f"🚫 Опасная дверь была: **{trap_door}**\n\n"
    
    if dead_players:
        status_text += "💀 *СПИСОК ПОГИБШИХ:*\n" + "\n".join([f"\\- **{escape(n)}**" for n in dead_players])
    else:
        status_text += "✅ В этом раунде все выжили\\!"
    
    bot.send_message(cid, status_text, parse_mode='MarkdownV2')
    game.round += 1
    time.sleep(3)
    run_door_round(cid)

def start_rps_finale(cid):
    game = games[cid]
    game.status = "RPS"
    p_ids = list(game.players.keys())
    
    if len(p_ids) < 2:
        winner_id = p_ids[0] if p_ids else None
        if winner_id:
            bot.send_message(cid, f"👑 Победитель: **{escape(game.players[winner_id])}**\n💎 Приз: **{escape(game.prize)}**", parse_mode='MarkdownV2')
        games.pop(cid)
        return

    p1, p2 = p_ids[0], p_ids[1]
    scores = {p1: 0, p2: 0}

    while scores[p1] < 3 and scores[p2] < 3:
        game.rps_data = {}
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("🗿 Камень", callback_data="rps_rock"),
            types.InlineKeyboardButton("✂️ Ножницы", callback_data="rps_scissors"),
            types.InlineKeyboardButton("📄 Бумага", callback_data="rps_paper")
        )
        
        bot.send_message(cid, f"🔥 *ФИНАЛЬНАЯ ДУЭЛЬ* 🔥\n**{escape(game.players[p1])}** \\({scores[p1]}\\) vs **{escape(game.players[p2])}** \\({scores[p2]}\\)\n\nВыбирайте оружие\\!", 
                         parse_mode='MarkdownV2', reply_markup=markup)
        
        # Ждем пока оба выберут
        start_wait = time.time()
        while len(game.rps_data) < 2 and time.time() - start_wait < 30:
            time.sleep(1)
        
        # Если кто-то не выбрал - рандом
        for p in [p1, p2]:
            if p not in game.rps_data: game.rps_data[p] = random.choice(['rock', 'scissors', 'paper'])
        
        c1, c2 = game.rps_data[p1], game.rps_data[p2]
        emojis = {'rock': '🗿', 'scissors': '✂️', 'paper': '📄'}
        
        round_msg = f"**{escape(game.players[p1])}** {emojis[c1]} vs {emojis[c2]} **{escape(game.players[p2])}**\n"
        
        if c1 == c2:
            round_msg += "🤝 Ничья в раунде\\!"
        elif (c1=='rock' and c2=='scissors') or (c1=='scissors' and c2=='paper') or (c1=='paper' and c2=='rock'):
            round_msg += f"✅ Точка за **{escape(game.players[p1])}**\\!"
            scores[p1] += 1
        else:
            round_msg += f"✅ Точка за **{escape(game.players[p2])}**\\!"
            scores[p2] += 1
            
        bot.send_message(cid, round_msg, parse_mode='MarkdownV2')
        time.sleep(2)

    winner = game.players[p1] if scores[p1] == 3 else game.players[p2]
    bot.send_message(cid, f"🏆 **ПОБЕДИТЕЛЬ ИГРЫ: {escape(winner)}**\n💎 ПРИЗ: {escape(game.prize)}", parse_mode='MarkdownV2')
    games.pop(cid, None)

# --- FLASK & RUN ---

@app.route('/')
def home():
    return "🤖 Бот работает!", 200

def run_bot():
    bot.infinity_polling(timeout=10, long_polling_timeout=5)

if __name__ == '__main__':
    threading.Thread(target=run_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
