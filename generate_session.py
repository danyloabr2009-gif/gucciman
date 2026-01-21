#!/usr/bin/env python3
"""
Create new Telegram session with QR code
"""

import asyncio
import os
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

# Загрузка переменных из .env
load_dotenv()

API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH', '')
SESSION_NAME = os.getenv('SESSION_NAME', 'gift_claimer_session')

async def create_session():
    """Create new session with QR code"""
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
            print("[QR] Попытка входа через QR код...")
            
            qr_login = await client.qr_login()
            print("[QR] QR код сгенерирован!")
            
            # Показать QR код в консоли
            try:
                qr_login.print_ascii(invert=True)
                print("\n[SCAN] Отсканируйте QR код в приложении Telegram")
                print("[WAIT] Ожидание сканирования...")
                
                # Ожидание сканирования
                await qr_login.wait()
                print("[SUCCESS] QR код успешно отсканирован!")
                
            except Exception as e:
                print(f"[ERROR] Ошибка QR кода: {e}")
                print("[LINK] Попробуйте открыть ссылку:")
                print(f"[URL] {qr_login.url}")
                print("[WAIT] Ожидание...")
                await qr_login.wait()
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
        
    except Exception as e:
        print(f"[ERROR] Ошибка: {e}")
        
    finally:
        await client.disconnect()
        print("[DISCONNECT] Соединение закрыто")

if __name__ == "__main__":
    asyncio.run(create_session())