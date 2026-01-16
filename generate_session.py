#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate StringSession for Railway deployment via QR code.
Run this locally, then copy the string to Railway environment variables.
"""

import asyncio
import qrcode
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

print("=" * 50)
print("StringSession Generator for Railway (QR)")
print("=" * 50)
print()

api_id = input("Enter API_ID: ").strip()
api_hash = input("Enter API_HASH: ").strip()

async def main():
    client = TelegramClient(StringSession(), int(api_id), api_hash)
    await client.connect()
    
    print("\nСканируйте QR-код в Telegram (Настройки -> Устройства -> Подключить устройство)")
    print()
    
    qr_login = await client.qr_login()
    
    # Показываем QR-код в терминале
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(qr_login.url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    
    try:
        await qr_login.wait(timeout=60)
    except SessionPasswordNeededError:
        print("\n2FA пароль требуется!")
        pwd = input("Введите пароль: ").strip()
        await client.sign_in(password=pwd)
    except asyncio.TimeoutError:
        print("\nТаймаут! QR-код истёк. Запустите скрипт заново.")
        await client.disconnect()
        return
    
    session_string = client.session.save()
    
    print("\n" + "=" * 50)
    print("SUCCESS! Your StringSession:")
    print("=" * 50)
    print()
    print(session_string)
    print()
    print("=" * 50)
    print("Copy this string and add it to Railway as STRING_SESSION")
    print("=" * 50)
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
