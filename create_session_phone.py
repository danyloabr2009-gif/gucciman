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
    
    print(f"🔑 Создание сессии: {SESSION_NAME}")
    print(f"📱 API_ID: {API_ID}")
    print(f"🔐 API_HASH: {API_HASH[:8]}...{API_HASH[-4:]}")
    print("=" * 50)
    
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    
    try:
        await client.connect()
        print("📡 Подключено к Telegram...")
        
        if not await client.is_user_authorized():
            print("📱 Пользователь не авторизован")
            
            # Ввод номера телефона
            phone = input("📞 Введите номер телефона (+XXX...): ")
            await client.send_code_request(phone)
            
            # Ввод кода подтверждения
            code = input("🔢 Введите код подтверждения: ")
            await client.sign_in(phone, code)
            
            print("✅ Вход выполнен!")
        else:
            print("✅ Пользователь уже авторизован!")
        
        # Проверка авторизации
        me = await client.get_me()
        print(f"👤 Сессия создана для: {me.first_name} @{me.username}")
        print(f"📞 Телефон: {me.phone}")
        print(f"🆔 ID: {me.id}")
        
        # Создание StringSession для Railway
        string_session = client.session.save()
        print("\n" + "=" * 50)
        print("🔑 STRING SESSION ДЛЯ RAILWAY:")
        print("=" * 50)
        print(string_session)
        print("=" * 50)
        print("\n💡 Скопируйте эту строку и добавьте в .env:")
        print("STRING_SESSION=" + string_session)
        
    except SessionPasswordNeededError:
        print("🔒 Требуется двухфакторная аутентификация")
        password = input("🔑 Введите пароль 2FA: ")
        await client.sign_in(password=password)
        print("✅ Двухфакторная аутентификация пройдена!")
        
        # Повторная проверка после 2FA
        me = await client.get_me()
        string_session = client.session.save()
        print("\n" + "=" * 50)
        print("🔑 STRING SESSION ДЛЯ RAILWAY:")
        print("=" * 50)
        print(string_session)
        print("=" * 50)
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        
    finally:
        await client.disconnect()
        print("🔌 Соединение закрыто")

if __name__ == "__main__":
    asyncio.run(create_session_phone())
