#!/usr/bin/env python3
"""
Create new Telegram session with phone number
"""

import asyncio
import os
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

load_dotenv()

API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH', '')
SESSION_NAME = os.getenv('SESSION_NAME', 'gift_claimer_session')

async def create_session_phone():
    """Create new session with phone number"""
    if not API_ID or not API_HASH:
        print("ERROR: API_ID и API_HASH должны быть указаны в .env файле")
        return
    
    print(f"[SESSION] Создание сессии: {SESSION_NAME}")
    print(f"[API] API_ID: {API_ID}")
    print(f"[HASH] API_HASH: {API_HASH[:8]}...{API_HASH[-4:]}")
    print("=" * 50)
    
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    
    try:
        await client.connect()
        print("[CONNECT] Подключено к Telegram...")
        
        if not await client.is_user_authorized():
            print("[AUTH] Пользователь не авторизован")
            
            # Ввод номера телефона
            phone = input("[PHONE] Введите номер телефона (+XXX...): ")
            await client.send_code_request(phone)
            
            # Ввод кода подтверждения
            code = input("[CODE] Введите код подтверждения: ")
            await client.sign_in(phone, code)
            
            print("[SUCCESS] Вход выполнен!")
        else:
            print("[AUTH] Пользователь уже авторизован!")
        
        # Проверка авторизации
        me = await client.get_me()
        print(f"[USER] Сессия создана для: {me.first_name} @{me.username}")
        print(f"[PHONE] Телефон: {me.phone}")
        print(f"[ID] ID: {me.id}")
        
        # Создание StringSession для Railway
        string_session = client.session.save()
        print("\n" + "=" * 50)
        print("[STRING] STRING SESSION ДЛЯ RAILWAY:")
        print("=" * 50)
        print(string_session)
        print("=" * 50)
        print("\n[INFO] Скопируйте эту строку и добавьте в .env:")
        print("STRING_SESSION=" + string_session)
        
    except SessionPasswordNeededError:
        print("[2FA] Требуется двухфакторная аутентификация")
        password = input("[PASS] Введите пароль 2FA: ")
        await client.sign_in(password=password)
        print("[SUCCESS] Двухфакторная аутентификация пройдена!")
        
        # Повторная проверка после 2FA
        me = await client.get_me()
        string_session = client.session.save()
        print("\n" + "=" * 50)
        print("[STRING] STRING SESSION ДЛЯ RAILWAY:")
        print("=" * 50)
        print(string_session)
        print("=" * 50)
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        
    finally:
        await client.disconnect()
        print("[DISCONNECT] Соединение закрыто")

if __name__ == "__main__":
    asyncio.run(create_session_phone())
