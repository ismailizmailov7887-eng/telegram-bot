import os
import threading
import time
import random
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from flask import Flask

TOKEN = os.environ.get("TELEGRAM_TOKEN")
bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=20)
app = Flask(__name__)

games = {}
duels = {}

# --- КЛАССЫ ---
class Game:
    def __init__(self, chat_id, prize, admin_id):
        self.chat_id, self.prize, self.admin_id = chat_id, prize, admin_id
        self.players, self.round, self.choosing_phase = {}, 1, False

class Duel:
    def __init__(self, creator_id, creator_name, prize):
        self.creator_id, self.creator_name, self.prize = creator_id, creator_name, prize
        self.player2_id = None
        self.started = False
        self.scores = {}
        self.roll_count = {}
        self.current_turn = None

# --- КОМАНДЫ (ПРИОРИТЕТ 1) ---

@bot.message_handler(commands=['stop_game', 'stop'])
def stop_all(message):
    cid = message.chat.id
    removed = False
    if cid in games: 
        del games[cid]
        removed = True
    if cid in duels: 
        del duels[cid]
        removed = True
    
    if removed:
        bot.reply_to(message, "🛑 **Все игры в этом чате остановлены и очищены!**", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ Нет активных игр для остановки.")

@bot.message_handler(commands=['duel'])
def create_duel_cmd(message):
    if message.chat.id in duels:
        return bot.reply_to(message, "⚠️ Дуэль уже создана!")
    msg = bot.send_message(message.chat.id, "💰 Введите приз:")
    bot.register_next_step_handler(msg, save_duel, message.chat.id)

def save_duel(message, cid):
    if message.text and not message.text.startswith('/'):
        duels[cid] = Duel(message.from_user.id, message.from_user.first_name, message.text)
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🎲 ВСТУПИТЬ", callback_data="join_duel"),
                   InlineKeyboardButton("❌ ОТМЕНА", callback_data="cancel_duel"))
        bot.send_message(cid, f"🎲 **ДУЭЛЬ**\nПриз: {message.text}\nЖдем игрока...", reply_markup=markup, parse_mode="Markdown")

# --- ОБРАБОТКА КНОПОК ---

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    cid, uid = call.message.chat.id, call.from_user.id
    
    if call.data == "join_duel":
        d = duels.get(cid)
        if d and not d.started and uid != d.creator_id:
            d.player2_id, d.player2_name = uid, call.from_user.first_name
            d.started, d.current_turn = True, d.creator_id
            d.scores = {d.creator_id: [], uid: []}
            d.roll_count = {d.creator_id: 0, uid: 0}
            bot.edit_message_text(f"🎲 **ДУЭЛЬ: {d.creator_name} VS {d.player2_name}**\n\n🎯 Ходит: {d.creator_name}\nОтправьте /dice", cid, call.message.message_id, parse_mode="Markdown")
    
    elif call.data == "cancel_duel":
        if cid in duels and (uid == duels[cid].creator_id):
            del duels[cid]
            bot.edit_message_text("❌ Дуэль отменена создателем.", cid, call.message.message_id)

# --- ИГРОВАЯ ЛОГИКА (DICE) ---

@bot.message_handler(content_types=['dice'])
def handle_real_dice(message):
    process_roll(message, is_text=False)

@bot.message_handler(func=lambda m: m.text and m.text.split('@')[0] == '/dice')
def handle_text_dice(message):
    process_roll(message, is_text=True)

def process_roll(message, is_text):
    cid, uid = message.chat.id, message.from_user.id
    if cid not in duels: return
    d = duels[cid]
    
    if not d.started or d.current_turn != uid: return

    if is_text:
        dice_msg = bot.send_dice(cid, reply_to_message_id=message.message_id)
        val = dice_msg.dice.value
    else:
        if message.dice.emoji != "🎲": return
        val = message.dice.value

    d.scores[uid].append(val)
    d.roll_count[uid] += 1
    
    time.sleep(3.5) # Ждем анимацию
    bot.reply_to(message, f"📊 Бросок {d.roll_count[uid]}/3: **{val}** (Всего: {sum(d.scores[uid])})", parse_mode="Markdown")

    if d.roll_count[uid] >= 3:
        if uid == d.creator_id:
            d.current_turn = d.player2_id
            bot.send_message(cid, f"🎯 Теперь ход {d.player2_name}!")
        else:
            s1, s2 = sum(d.scores[d.creator_id]), sum(d.scores[d.player2_id])
            res = f"🏁 **ИТОГ**\n{d.creator_name}: {s1}\n{d.player2_name}: {s2}\n\n"
            if s1 > s2: res += f"🏆 Победил {d.creator_name}!"
            elif s2 > s1: res += f"🏆 Победил {d.player2_name}!"
            else: res += "🤝 Ничья!"
            bot.send_message(cid, res, parse_mode="Markdown")
            del duels[cid]

# --- ЗАПУСК ---
if __name__ == '__main__':
    threading.Thread(target=lambda: bot.infinity_polling(skip_pending=True)).start()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
