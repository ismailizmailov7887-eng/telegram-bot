import os
import threading
import time
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask

# --- НАСТРОЙКИ ---
TOKEN = "8598717015:AAGhbHPy-C9VTkcYb2XSyrJ3a_i83JNojf8" # Замените на ваш токен
bot = telebot.TeleBot(TOKEN, threaded=True)
app = Flask(__name__)

# Хранилище игр (в памяти)
duels = {}
games = {}

# --- КЛАССЫ ---
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

# --- КОМАНДЫ ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.reply_to(message, "🎮 Бот готов! Используйте /duel для игры 1 на 1 или /start_game для 3 дверей.")

@bot.message_handler(commands=['stop_game', 'stop'])
def stop_all(message):
    cid = message.chat.id
    if cid in duels: del duels[cid]
    if cid in games: del games[cid]
    bot.reply_to(message, "🛑 Все активные игры в этом чате остановлены.")

@bot.message_handler(commands=['duel'])
def init_duel(message):
    cid = message.chat.id
    if cid in duels:
        return bot.reply_to(message, "⚠️ В этом чате уже создана дуэль.")
    
    msg = bot.send_message(cid, "💰 Введите приз для дуэли:")
    bot.register_next_step_handler(msg, process_prize, cid)

def process_prize(message, cid):
    if not message.text or message.text.startswith('/'): return
    
    prize = message.text
    duels[cid] = Duel(message.from_user.id, message.from_user.first_name, prize)
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🎲 ПРИНЯТЬ ВЫЗОВ", callback_data="join_duel"))
    markup.add(InlineKeyboardButton("❌ ОТМЕНА", callback_data="cancel_duel"))
    
    bot.send_message(cid, f"🎲 **ДУЭЛЬ**\n\n👤 Создатель: {message.from_user.first_name}\n🏆 Приз: {prize}\n\nОжидание соперника...", 
                     reply_markup=markup, parse_mode="Markdown")

# --- КНОПКИ ---
@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    cid = call.message.chat.id
    uid = call.from_user.id

    if call.data == "join_duel":
        duel = duels.get(cid)
        if not duel or duel.started: return bot.answer_callback_query(call.id, "Дуэль недоступна.")
        if uid == duel.creator_id: return bot.answer_callback_query(call.id, "Нельзя играть с самим собой!")

        duel.player2_id = uid
        duel.player2_name = call.from_user.first_name
        duel.started = True
        duel.current_turn = duel.creator_id
        duel.scores = {duel.creator_id: [], uid: []}
        duel.roll_count = {duel.creator_id: 0, uid: 0}

        bot.edit_message_text(f"🎲 **ДУЭЛЬ НАЧАЛАСЬ!**\n\n{duel.creator_name} 🆚 {duel.player2_name}\n\n"
                              f"🎯 Первым ходит: {duel.creator_name}\nБросайте /dice (3 раза)", 
                              cid, call.message.message_id, parse_mode="Markdown")

    elif call.data == "cancel_duel":
        if cid in duels and duels[cid].creator_id == uid:
            del duels[cid]
            bot.edit_message_text("❌ Дуэль отменена.", cid, call.message.message_id)
        else:
            bot.answer_callback_query(call.id, "Только создатель может отменить.")

# --- ЛОГИКА КУБИКОВ ---
@bot.message_handler(content_types=['dice', 'text'])
def dice_logic(message):
    cid = message.chat.id
    if cid not in duels: return
    
    duel = duels[cid]
    if not duel.started: return
    
    uid = message.from_user.id
    if uid != duel.current_turn: return

    # Проверяем: пришел анимированный кубик или текст команды /dice (с учетом юзернейма)
    is_dice = False
    val = 0

    if message.dice and message.dice.emoji == "🎲":
        is_dice = True
        val = message.dice.value
    elif message.text and message.text.split('@')[0].lower() == '/dice':
        # Если пришел текст /dice, бот сам кидает кубик
        res = bot.send_dice(cid, reply_to_message_id=message.message_id)
        is_dice = True
        val = res.dice.value
    
    if is_dice:
        duel.scores[uid].append(val)
        duel.roll_count[uid] += 1
        
        time.sleep(3.5) # Ждем завершения анимации кубика
        bot.reply_to(message, f"🎲 Выпало: {val}\n📊 Всего очков: {sum(duel.scores[uid])}")

        if duel.roll_count[uid] >= 3:
            if uid == duel.creator_id:
                duel.current_turn = duel.player2_id
                bot.send_message(cid, f"🎯 Очередь {duel.player2_name}! Кидай /dice")
            else:
                finish_duel(cid, duel)

def finish_duel(cid, duel):
    s1 = sum(duel.scores[duel.creator_id])
    s2 = sum(duel.scores[duel.player2_id])
    
    res = f"🏁 **ДУЭЛЬ ОКОНЧЕНА**\n\n👤 {duel.creator_name}: {s1}\n👤 {duel.player2_name}: {s2}\n\n"
    if s1 > s2: res += f"🏆 Победил **{duel.creator_name}**!"
    elif s2 > s1: res += f"🏆 Победил **{duel.player2_name}**!"
    else: res += "🤝 Ничья!"
    
    bot.send_message(cid, res + f"\n🎁 Приз: {duel.prize}", parse_mode="Markdown")
    if cid in duels: del duels[cid]

# --- FLASK ---
@app.route('/')
def index(): return "Running", 200

if __name__ == '__main__':
    # Установка команд в меню
    bot.set_my_commands([
        BotCommand("start", "Запуск"),
        BotCommand("duel", "Создать дуэль"),
        BotCommand("stop", "Остановить всё")
    ])
    
    print("🚀 Бот запущен!")
    # skip_pending=True ОЧЕНЬ ВАЖНО, чтобы бот не захлебнулся старыми сообщениями
    threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True)).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
