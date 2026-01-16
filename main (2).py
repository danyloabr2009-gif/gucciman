#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Gift Claimer - FINAL EDITION v7.0
Специально для кнопки "Активировать чек" и других подарков.
"""

import asyncio
import os
import sys
from datetime import datetime
from telethon import TelegramClient, events
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from telethon.errors import SessionPasswordNeededError
import qrcode

# ============================================================================
# НАСТРОЙКИ
# ============================================================================
API_ID = 38562987
API_HASH = "a638356724cb39be09d9e245c431d0a4"

TARGET_CHANNELS = [
    -1003066572414,      # ID канала
    -1002781987569,      # ID второго канала
]

# Бот по умолчанию (используется, если не удалось определить бота из ссылки)
DEFAULT_GIFT_BOT = "anonimgifterbot"

# Цвета
CYAN = '\033[96m'
MAGENTA = '\033[95m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
GRAY = '\033[90m'
RESET = '\033[0m'
BOLD = '\033[1m'

client = TelegramClient('gift_claimer_session', API_ID, API_HASH)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def rgb_text(text, r, g, b):
    return f"\033[38;2;{r};{g};{b}m{text}{RESET}"

# ============================================================================
# ЛОГИКА ЛОВЛИ (С УЛУЧШЕННЫМ РАСПОЗНАВАНИЕМ)
# ============================================================================
async def smart_claim(event):
    message = event.message
    
    if not message.buttons:
        return False

    for row in message.buttons:
        for btn in row:
            # Текст кнопки (приводим к нижнему регистру)
            btn_text = (btn.text or "").lower()
            
            # === ⛔ ЧЕРНЫЙ СПИСОК (ИГНОРИРОВАТЬ) ===
            blacklist = [
                'разб', 'unban', 'report', 'жал', 'rule', 'правил', 
                'verify', 'kick', 'ban', 'mute', 'admin', 'отмен'
            ]
            if any(bad_word in btn_text for bad_word in blacklist):
                continue

            # === ✅ БЕЛЫЙ СПИСОК (СЛОВА-ТРИГГЕРЫ) ===
            # Если текст кнопки содержит эти слова - это наш клиент
            whitelist = [
                'активировать', 'получить', 'забрать', 'claim', 'get', 
                'view', 'open', 'открыть', 'чек', 'gift', 'подарок'
            ]
            is_gift_text = any(good_word in btn_text for good_word in whitelist)

            # --- ВАРИАНТ 1: Callback-кнопка (без ссылки) ---
            # Жмем, если есть data И (текст подходит ИЛИ текста нет вообще)
            if btn.data and (is_gift_text or not btn_text):
                try:
                    await client(GetBotCallbackAnswerRequest(
                        peer=event.chat_id,
                        msg_id=message.id,
                        data=btn.data
                    ))
                    print(f"\n{GREEN}⚡ [GIFT] Нажал кнопку: {BOLD}{btn.text or '[Без текста]'}{RESET}")
                    return True
                except Exception as e:
                    # Ошибки тут не важны, главное попытка
                    return True

            # --- ВАРИАНТ 2: URL-кнопка (Активировать чек) ---
            if btn.url:
                url = btn.url.lower()
                start_param = None
                target_bot = None

                # 1. Ищем параметр запуска (код подарка)
                if "start=" in url:
                    start_param = url.split("start=")[1].split("&")[0]
                elif "startapp=" in url:
                    start_param = url.split("startapp=")[1].split("&")[0]
                
                # 2. Если код найден, ищем, какому боту его слать
                if start_param:
                    # Пытаемся вытащить юзернейм бота из ссылки
                    if "t.me/" in url:
                        try:
                            target_bot = url.split("t.me/")[1].split("?")[0].replace("/", "")
                        except: pass
                    elif "tg://resolve" in url:
                         try:
                             target_bot = url.split("domain=")[1].split("&")[0]
                         except: pass
                    
                    # Если не вышло, но текст кнопки "правильный" - используем дефолтного бота
                    if not target_bot and is_gift_text:
                         target_bot = DEFAULT_GIFT_BOT

                    # 3. Отправляем команду боту
                    if target_bot:
                        try:
                            print(f"\n{MAGENTA}⚡ [GIFT] Активация по ссылке для @{target_bot}{RESET}")
                            await client.send_message(target_bot, f"/start {start_param}")
                            print(f"{GREEN}⚡ [GIFT] Команда /start отправлена!{RESET}")
                            return True
                        except Exception as e:
                             print(f"{RED}❌ Ошибка отправки /start: {e}{RESET}")
                             return True
    
    return False

# ============================================================================
# ОБРАБОТЧИК СООБЩЕНИЙ
# ============================================================================
@client.on(events.NewMessage(chats=TARGET_CHANNELS))
async def handler(event):
    # Сначала - ловля
    was_gift = await smart_claim(event)

    # Потом - логи
    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        message = event.message
        
        chat_title = "Channel"
        sender_name = "User"
        try:
            chat = await event.get_chat()
            if hasattr(chat, 'title'): chat_title = chat.title
            sender = await message.get_sender()
            if hasattr(sender, 'first_name'): sender_name = sender.first_name
        except: pass

        text = (message.text or "").replace('\n', ' ')
        
        if was_gift:
            print(f"{MAGENTA}>>> Обработано в {timestamp}{RESET}")
        else:
            display_text = (text[:60] + '...') if len(text) > 60 else text
            if not display_text and message.media: display_text = "[Медиа]"
            print(f"{CYAN}[{timestamp}]{RESET} {GRAY}{chat_title[:15]}{RESET} | {BOLD}{sender_name}{RESET}: {display_text}")

    except Exception:
        pass

# ============================================================================
# ВХОД И ЗАПУСК
# ============================================================================
async def login_system():
    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"{GREEN}✅ Вход выполнен: {me.first_name} (@{me.username}){RESET}")
        return True

    print(f"\n{YELLOW}⚠ ТРЕБУЕТСЯ ВХОД (QR){RESET}")
    qr_login = await client.qr_login()
    qr = qrcode.QRCode()
    qr.add_data(qr_login.url)
    qr.make()
    qr.print_ascii(invert=True)
    
    try:
        await qr_login.wait()
    except SessionPasswordNeededError:
        print(f"\n{RED}🔒 ВВЕДИТЕ 2FA ПАРОЛЬ!{RESET}")
        pwd = input(f"{CYAN}⌨ Пароль: {RESET}")
        await client.sign_in(password=pwd)
        print(f"{GREEN}✅ Пароль принят!{RESET}")
    return True

async def main():
    clear_screen()
    print("\n")
    print(rgb_text("╔════════════════════════════════════════════╗", 255, 100, 0))
    print(rgb_text("║      FINAL EDITION v7.0 (GIFT HUNTER)      ║", 255, 200, 0))
    print(rgb_text("╚════════════════════════════════════════════╝", 255, 100, 0))
    print(f"{GRAY}   Распознает кнопки 'Активировать чек'.{RESET}\n")
    
    await client.connect()
    if await login_system():
        print(f"\n{CYAN}👀 Мониторинг запущен...{RESET}")
        await client.run_until_disconnected()

if __name__ == "__main__":
    try:
        client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n🛑 Стоп.")