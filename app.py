def escape_round_results(chat_id):
    if chat_id not in active_escapes: return
    game = active_escapes[chat_id]
    
    # Если за 30 секунд никто не выбрал, бот выбирает рандомно
    for p_id in game['players']:
        if p_id not in game['choices']:
            game['choices'][p_id] = random.randint(1, 3)

    dead_list = []
    door_data = {1: [], 2: [], 3: []}
    
    # Распределяем игроков по комнатам и определяем судьбу
    for p_id, door in game['choices'].items():
        name = game['players'][p_id]
        if door == game['dead_door'] and random.random() < 0.65:
            dead_list.append(p_id)
        else:
            door_data[door].append(name)

    # ВАЖНО: Сначала удаляем мертвых из официального списка игроков
    for p_id in dead_list:
        game['players'].pop(p_id, None)

    # Теперь формируем текст, когда список game['players'] уже обновлен
    res_text = f"📊 *РЕЗУЛЬТАТЫ РАУНДА {game['room']}*\n\n"
    for d in range(1, 4):
        p_str = ", ".join(door_data[d]) if door_data[d] else "Пусто"
        # Помечаем тех, кто был в ловушке, но выжил, и тех, кто погиб
        if d == game['dead_door']:
            icon = "💀 ЛОВУШКА"
            # Если в комнате были люди, но их нет в dead_list — они счастливчики
        else:
            icon = "✅ БЕЗОПАСНО"
        res_text += f"🚪 *КОМНАТА {d}*\n{icon}: {p_str}\n\n"

    survivors_names = list(game['players'].values())
    
    if dead_list:
        dead_names = ", ".join([bot.get_chat_member(chat_id, d_id).user.first_name for d_id in dead_list]) # Или просто хранить имена
        # Для простоты можно выводить имена из локального списка, если они там были
        res_text += f"⚰️ ПОГИБЛИ: {len(dead_list)} чел.\n"

    res_text += f"💎 *ВЫЖИЛИ:* {', '.join(survivors_names) if survivors_names else 'Никто'}\n\n"

    if not game['players']:
        res_text += "💀 *ВСЕ ПОГИБЛИ. ИГРА ОКОНЧЕНА.*"
        bot.send_message(chat_id, res_text, parse_mode="Markdown")
        active_escapes.pop(chat_id, None)
        return

    res_text += f"🔜 СЛЕДУЮЩИЙ ЭТАП через 5 секунд..."
    bot.send_message(chat_id, res_text, parse_mode="Markdown")
    
    game['room'] += 1
    threading.Timer(5.0, escape_round_start, args=(chat_id,)).start()
