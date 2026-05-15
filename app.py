import os
import threading
import time
import random
import telebot
from telebot import types
from flask import Flask

# --- НАСТРОЙКИ ---
TOKEN = "8598717015:AAELFLybH7mxCCx02t23f9ufHYZI90Zolw4"
bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

games = {}
duels = {}

# --- КЛАССЫ ЛОГИКИ ---

class GameDoors:
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

# --- КОМАНДЫ И МЕНЮ ---

@bot.message_handler(commands=['start', 'help'])
def cmd_start(message):
    markup = types.InlineKeyboardMarkup()
    
    btn_info = types.InlineKeyboardButton(text="Info", url='https://t.me/direcode_bot')
    btn_accept = types.InlineKeyboardButton(text="Accept", url='https://t.me/direcode_bot')
    btn_reject = types.InlineKeyboardButton(text="Reject", url='https://t.me/direcode_bot')
    btn_settings = types.InlineKeyboardButton(text="Settings", url='https://t.me/direcode_bot')

    markup.row(btn_accept, btn_reject)
    markup.row(btn_info, btn_settings)
    
    text = '<b>Добро пожаловать в Direcode bot!</b> <tg-emoji emoji-id="5372878077250519677">✅</tg-emoji>'
    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=markup)

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
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🚪 Вступить", callback_data="join_doors"))
    markup.add(types.InlineKeyboardButton("▶️ Начать игру", callback_data="start_doors_round"))
    
    text_doors = (
        f"🚪 <b>Игра 3 Двери</b>\n\n"
        f"🏆 Приз: <b>{message.text}</b>\n\n"
        f"Нажмите кнопку ниже, чтобы вступить!"
    )
    bot.send_message(cid, text_doors, parse_mode='HTML', reply_markup=markup)

# --- ЛОГИКА: ДУЭЛЬ ---

@bot.message_handler(commands=['duel'])
def cmd_start_duel(message):
    cid = message.chat.id
    if cid in duels: return bot.reply_to(message, "⚠️ Дуэль уже создана.")
    msg = bot.send_message(cid, "💰 Напишите приз дуэли:")
    bot.register_next_step_handler(msg, process_duel_prize, cid)

def process_duel_prize(message, cid):
    if not message.text or message.text.startswith('/'): return
    duels[cid] = DuelRoom(message.from_user.id, message.from_user.first_name, message.text)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎲 Принять вызов", callback_data="join_duel"),
               types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_duel"))
    
    text_create = (
        f"🎲 <b>Вызов на дуэль</b>\n\n"
        f"👤 Организатор: <b>{message.from_user.first_name}</b>\n"
        f"🏆 На кону: <b>{message.text}</b>\n\n"
        f"Ожидаем второго участника..."
    )
    bot.send_message(cid, text_create, parse_mode='HTML', reply_markup=markup)

# --- CALLBACKS (КНОПКИ) ---

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    cid, uid = call.message.chat.id, call.from_user.id

    if call.data == "join_doors":
        if cid in games and games[cid].add_player(uid, call.from_user.first_name):
            bot.answer_callback_query(call.id, "✅ Вы в игре!")
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка входа.")

    elif call.data == "start_doors_round":
        game = games.get(cid)
        if not game or uid != game.admin_id: 
            return bot.answer_callback_query(call.id, "Только админ!")
        if len(game.get_alive_players()) < 1: 
            return bot.answer_callback_query(call.id, "Нет игроков!")
        
        game.choosing_phase, game.choices = True, {}
        game.dead_door = random.randint(1, 3)
        
        markup = types.InlineKeyboardMarkup().row(
            types.InlineKeyboardButton("🚪 1", callback_data="door_1"),
            types.InlineKeyboardButton("🚪 2", callback_data="door_2"),
            types.InlineKeyboardButton("🚪 3", callback_data="door_3")
        )
        text_round = f"🚀 <b>Раунд {game.round}</b>\n\nВыберите дверь! У вас есть 20 секунд."
        bot.send_message(cid, text_round, parse_mode='HTML', reply_markup=markup)
        threading.Timer(20.0, finish_doors_round, [cid]).start()

    elif call.data.startswith("door_"):
        game = games.get(cid)
        if game and game.choosing_phase and uid in game.get_alive_players():
            game.choices[uid] = int(call.data.split("_")[1])
            bot.answer_callback_query(call.id, "Выбрано!")

    elif call.data == "join_duel":
        d = duels.get(cid)
        if d and not d.started and uid != d.creator_id:
            d.player2_id, d.player2_name = uid, call.from_user.first_name
            d.started, d.current_turn = True, d.creator_id
            d.scores = {d.creator_id: [], uid: []}
            d.roll_count = {d.creator_id: 0, uid: 0}
            
            text_start = (
                f"🎲 <b>Дуэль началась!</b>\n\n"
                f"👤 {d.creator_name} 🆚 {d.player2_name} 👤\n\n"
                f"🎯 Первым ходит <b>{d.creator_name}</b>.\n"
                f"Отправьте команду <code>/dice</code> или бросьте кубик!"
            )
            bot.edit_message_text(text_start, cid, call.message.message_id, parse_mode='HTML')

    elif call.data == "cancel_duel":
        if cid in duels and duels[cid].creator_id == uid:
            del duels[cid]
            bot.edit_message_text("❌ Дуэль отменена.", cid, call.message.message_id)

# --- ТЕКСТ, DICE И EMOJI ID ---

@bot.message_handler(content_types=['text', 'dice'])
def handle_text_and_dice(message):
    cid, uid = message.chat.id, message.from_user.id
    
    # Получение Emoji ID
    custom_emoji_id = None
    if message.entities:
        for entity in message.entities:
            if entity.type == 'custom_emoji':
                custom_emoji_id = entity.custom_emoji_id
                break
    if custom_emoji_id:
        bot.reply_to(message, f'Emoji: <code>{message.text}</code>\nID: <code>{custom_emoji_id}</code>', parse_mode='HTML')
        return

    # Логика Дуэли
    if cid in duels:
        d = duels[cid]
        if d.started and d.current_turn == uid:
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
                
                text_roll = f"🎲 Выпало: <b>{val}</b> | Сумма: <b>{sum(d.scores[uid])}</b>"
                bot.reply_to(message, text_roll, parse_mode='HTML')
                
                if d.roll_count[uid] >= 3:
                    if uid == d.creator_id:
                        d.current_turn = d.player2_id
                        text_next = f"🎯 Ход игрока <b>{d.player2_name}</b>! Ждем <code>/dice</code>"
                        bot.send_message(cid, text_next, parse_mode='HTML')
                    else:
                        s1, s2 = sum(d.scores[d.creator_id]), sum(d.scores[d.player2_id])
                        res = (
                            f"🏁 <b>Результаты дуэли</b>\n\n"
                            f"👤 {d.creator_name}: <b>{s1}</b>\n"
                            f"👤 {d.player2_name}: <b>{s2}</b>\n\n"
                        )
                        if s1 > s2: res += f"🏆 Победитель: <b>{d.creator_name}</b>!"
                        elif s2 > s1: res += f"🏆 Победитель: <b>{d.player2_name}</b>!"
                        else: res += "🤝 Ничья!"
                        
                        bot.send_message(cid, res, parse_mode='HTML')
                        del duels[cid]

def finish_doors_round(cid):
    game = games.get(cid)
    if not game: return
    game.choosing_phase = False
    dead = game.dead_door
    
    text = f"⌛️ <b>Время вышло!</b>\n\nЛовушка была за дверью: 🚪 <b>{dead}</b>\n\n"
    for uid, data in list(game.players.items()):
        if not data['alive']: continue
        if game.choices.get(uid) == dead or uid not in game.choices:
            game.players[uid]['alive'] = False
            text += f"💀 {data['name']} — выбывает\n"
        else: 
            text += f"✅ {data['name']} — проходит дальше\n"
    
    alive = game.get_alive_players()
    if not alive:
        bot.send_message(cid, text + "\nВсе игроки выбыли!", parse_mode='HTML')
        del games[cid]
    elif len(alive) == 1:
        winner = list(alive.values())[0]['name']
        bot.send_message(cid, text + f"\n🏆 <b>Победитель: {winner}</b>\nПриз: <b>{game.prize}</b>", parse_mode='HTML')
        del games[cid]
    else:
        game.round += 1
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("➡️ Следующий раунд", callback_data="start_doors_round"))
        bot.send_message(cid, text, parse_mode='HTML', reply_markup=markup)

# --- ЗАПУСК ---
@app.route('/')
def health(): return "OK", 200

if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_my_commands([
        types.BotCommand("start", "Главное меню"),
        types.BotCommand("duel", "Создать дуэль"),
        types.BotCommand("start_game", "Игра 3 Двери"),
        types.BotCommand("stop", "Остановить игры")
    ])
    threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True)).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
