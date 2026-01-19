#!/usr/bin/env python3
"""
Reset session - delete old and create new
"""

import asyncio
import os
import glob
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

API_ID = int(os.getenv('API_ID', '0'))
API_HASH = os.getenv('API_HASH', '')
SESSION_NAME = os.getenv('SESSION_NAME', 'gift_claimer_session')

def delete_session_files():
    """Delete all session files"""
    session_patterns = [
        f"{SESSION_NAME}.session",
        f"{SESSION_NAME}.session-journal",
        f"{SESSION_NAME}.session-shm",
        f"{SESSION_NAME}.session-wal"
    ]
    
    deleted_files = []
    for pattern in session_patterns:
        for file_path in glob.glob(pattern):
            try:
                os.remove(file_path)
                deleted_files.append(file_path)
                print(f"🗑️ Удален файл: {file_path}")
            except FileNotFoundError:
                pass
            except Exception as e:
                print(f"❌ Ошибка удаления {file_path}: {e}")
    
    return deleted_files

async def reset_session():
    """Reset session - delete old and create new"""
    if not API_ID or not API_HASH:
        print("ERROR: API_ID и API_HASH должны быть указаны в .env файле")
        return
    
    print("🔄 СБРОС СЕССИИ")
    print("=" * 50)
    
    # Удаление старых файлов
    print("🗑️ Удаление старых файлов сессии...")
    deleted_files = delete_session_files()
    
    if not deleted_files:
        print("ℹ️ Старые файлы сессии не найдены")
    else:
        print(f"✅ Удалено файлов: {len(deleted_files)}")
    
    print("\n🔑 Создание новой сессии...")
    
    # Создание новой сессии
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    
    try:
        await client.connect()
        print("📡 Подключено к Telegram...")
        
        if not await client.is_user_authorized():
            print("📱 Требуется авторизация")
            print("🔍 Попытка входа через QR код...")
            
            qr_login = await client.qr_login()
            print("📷 QR код сгенерирован!")
            
            try:
                qr_login.print_ascii(invert=True)
                print("\n📱 Отсканируйте QR код в приложении Telegram")
                print("⏰ Ожидание сканирования...")
                
                await qr_login.wait()
                print("✅ QR код успешно отсканирован!")
                
            except Exception as e:
                print(f"❌ Ошибка QR кода: {e}")
                print("🔗 Откройте ссылку:")
                print(f"📱 {qr_login.url}")
                print("⏰ Ожидание...")
                await qr_login.wait()
        
        # Проверка авторизации
        me = await client.get_me()
        print(f"👤 Новая сессия создана: {me.first_name} @{me.username}")
        print(f"📞 Телефон: {me.phone}")
        print(f"🆔 ID: {me.id}")
        
        # Создание StringSession
        string_session = client.session.save()
        print("\n" + "=" * 50)
        print("🔑 НОВАЯ STRING SESSION ДЛЯ RAILWAY:")
        print("=" * 50)
        print(string_session)
        print("=" * 50)
        print("\n💡 Добавьте в .env:")
        print("STRING_SESSION=" + string_session)
        print("\n🚀 Теперь можно запускать бота!")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        
    finally:
        await client.disconnect()
        print("🔌 Соединение закрыто")

if __name__ == "__main__":
    asyncio.run(reset_session())
