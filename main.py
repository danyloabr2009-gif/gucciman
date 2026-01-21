#!/usr/bin/env python3
"""
Simple Telegram Gift Claimer Bot
Only presses 'Активировать чек' button
"""

import asyncio
import os
from datetime import datetime
from telethon import TelegramClient
from telethon.events import NewMessage
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from dotenv import load_dotenv

# ============================================================================
# CONFIGURATION
# ============================================================================
load_dotenv()

API_ID = int(os.getenv('API_ID', '38562987'))
API_HASH = os.getenv('API_HASH', 'a638356724cb39be09d9e245c431d0a4')
TARGET_CHANNELS = [int(x.strip()) for x in os.getenv('TARGET_CHANNELS', '-1003066572414').split(',') if x.strip()]
GIFT_BOT = "anonimgifterbot"
SESSION_NAME = "gift_claimer_session"

# ============================================================================
# CLIENT SETUP
# ============================================================================
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

# ============================================================================
# STATISTICS
# ============================================================================
stats = {
    'detected': 0,
    'claimed': 0,
    'failed': 0,
    'start_time': None
}

# ============================================================================
# CORE CLAIM LOGIC
# ============================================================================
async def claim_gift_check(message):
    """Simple gift check claim - only presses 'Активировать чек' button"""
    global stats
    
    try:
        # Check if message has buttons
        if not message.reply_markup or not message.reply_markup.inline_keyboard:
            return
        
        # Get first button
        button = message.reply_markup.inline_keyboard[0][0]
        button_text = (button.text or "").lower()
        
        # Check if it's the "Активировать чек" button
        if "активировать чек" in button_text:
            stats['detected'] += 1
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{timestamp}] [GIFT] ЧЕК ОБНАРУЖЕН: {button.text}")
            
            # Only press callback buttons (not URL)
            if button.data:
                await client(GetBotCallbackAnswerRequest(
                    peer=message.chat.id,
                    message_id=message.id,
                    callback_data=button.data
                ))
                
                stats['claimed'] += 1
                print(f"[{timestamp}] [SUCCESS] ЧЕК АКТИВИРОВАН! Всего: {stats['claimed']}")
                
                # Log to saved messages
                try:
                    await client.send_message('me', f"[GIFT] Чек активирован | {message.chat.title} | {timestamp}")
                except:
                    pass
            else:
                print(f"[{timestamp}] [SKIP] Кнопка не callback, пропускаем")
    
    except Exception as e:
        stats['failed'] += 1
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [ERROR] Ошибка: {e}")

# ============================================================================
# MESSAGE HANDLER
# ============================================================================
@client.on(NewMessage(chats=TARGET_CHANNELS))
async def gift_detector(event):
    """Detect gift checks from anonimgifterbot"""
    message = event.message
    
    # Check if message is from gift bot
    if message.from_user and message.from_user.username == GIFT_BOT:
        await claim_gift_check(message)
    
    # Also check forwarded messages via bot
    elif message.via_bot and message.via_bot.username == GIFT_BOT:
        await claim_gift_check(message)

# ============================================================================
# MAIN FUNCTION
# ============================================================================
async def main():
    """Main execution"""
    global stats
    
    print("=" * 60)
    print("[GIFT] Simple Gift Claimer Bot v1.0")
    print("=" * 60)
    print(f"[MONITOR] Каналов: {len(TARGET_CHANNELS)}")
    print(f"[TARGET] Бот: @{GIFT_BOT}")
    print(f"[SEARCH] Кнопки: 'Активировать чек'")
    print("=" * 60)
    
    try:
        # Try to start with existing session
        try:
            await client.start()
            me = await client.get_me()
            print(f"[SUCCESS] Подключено: {me.first_name} (@{me.username or 'no_username'})")
            print(f"[PHONE] Телефон: {me.phone}")
        except Exception as session_error:
            # If session is invalid, try QR login
            if "session" in str(session_error).lower() or "auth_key" in str(session_error).lower():
                print("[QR] Сессия недействительна, пробуем QR код...")
                
                # Delete old session files
                try:
                    if os.path.exists(f"{SESSION_NAME}.session"):
                        os.remove(f"{SESSION_NAME}.session")
                    if os.path.exists(f"{SESSION_NAME}.session-journal"):
                        os.remove(f"{SESSION_NAME}.session-journal")
                except:
                    pass
                
                # Create new client and try QR login
                client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
                await client.connect()
                
                qr_login = await client.qr_login()
                print("[QR] QR код сгенерирован!")
                print("[SCAN] Отсканируйте QR код в Telegram:")
                print("Настройки → Устройства → Подключить устройство")
                
                try:
                    qr_login.print_ascii(invert=True)
                    print("\n[WAIT] Ожидание сканирования...")
                    await qr_login.wait()
                    print("[SUCCESS] QR код успешно отсканирован!")
                    
                    me = await client.get_me()
                    print(f"[SUCCESS] Подключено: {me.first_name} (@{me.username or 'no_username'})")
                    print(f"[PHONE] Телефон: {me.phone}")
                    
                except Exception as qr_error:
                    print(f"[ERROR] Ошибка QR кода: {qr_error}")
                    print("[LINK] Попробуйте открыть ссылку:")
                    print(f"[URL] {qr_login.url}")
                    print("[WAIT] Ожидание...")
                    await qr_login.wait()
                    
                    me = await client.get_me()
                    print(f"[SUCCESS] Подключено: {me.first_name} (@{me.username or 'no_username'})")
                    print(f"[PHONE] Телефон: {me.phone}")
            else:
                raise session_error
        
        stats['start_time'] = datetime.now()
        print("\n[RUN] Ожидаю подарочные чеки...")
        print("(Ctrl+C для остановки)\n")
        
        # Keep running
        await client.run_until_disconnected()
        
    except KeyboardInterrupt:
        print("\n[STOP] Остановка по запросу пользователя...")
    except Exception as e:
        print(f"\n[ERROR] Ошибка: {e}")
    finally:
        await client.disconnect()
        print("[STOP] Бот остановлен")

# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[STOP] Программа завершена")
