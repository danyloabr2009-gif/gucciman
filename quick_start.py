#!/usr/bin/env python3
"""
Quick Start Gift Claimer - Simple version
"""

import asyncio
import os
from telethon import TelegramClient
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Your credentials
API_ID = 38562987
API_HASH = "a638356724cb39be09d9e245c431d0a4"
SESSION_NAME = "gift_claimer_session"

async def main():
    """Quick start session creation"""
    print("=" * 50)
    print("[GIFT] Gift Claimer - Quick Start")
    print("=" * 50)
    print(f"[API] API_ID: {API_ID}")
    print(f"[HASH] API_HASH: {API_HASH[:8]}...{API_HASH[-4:]}")
    print("=" * 50)
    
    # Create client
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    
    try:
        print("[CONNECT] Connecting to Telegram...")
        await client.connect()
        
        if not await client.is_user_authorized():
            print("[AUTH] Please authorize:")
            phone = input("Enter phone number (+XXX...): ")
            
            try:
                await client.send_code_request(phone)
                print("[CODE] Verification code sent to Telegram")
                code = input("Enter verification code: ")
                
                await client.sign_in(phone, code)
                print("[SUCCESS] Successfully authorized!")
            except Exception as sign_in_error:
                error_msg = str(sign_in_error).lower()
                if "password" in error_msg or "2fa" in error_msg:
                    print("[2FA] Two-factor authentication required")
                    password = input("Enter 2FA password: ")
                    await client.sign_in(password=password)
                    print("[SUCCESS] Successfully authorized with 2FA!")
                elif "invalid" in error_msg or "code" in error_msg:
                    print("[ERROR] Invalid verification code")
                    print("[RETRY] Please check the code and try again")
                    return
                else:
                    print(f"[ERROR] Sign in error: {sign_in_error}")
                    raise sign_in_error
        
        # Get user info
        me = await client.get_me()
        print(f"[USER] User: {me.first_name} @{me.username or 'no_username'}")
        print(f"[PHONE] Phone: {me.phone}")
        print(f"[ID] ID: {me.id}")
        
        # Create string session
        string_session = client.session.save()
        print("\n" + "=" * 50)
        print("[STRING] STRING SESSION:")
        print("=" * 50)
        print(string_session)
        print("=" * 50)
        print("\n[SUCCESS] Session created successfully!")
        print("[READY] Now you can run: python simple_main.py")
        
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        print("\n[TIPS] Try these solutions:")
        print("1. Check your internet connection")
        print("2. Verify API credentials are correct")
        print("3. Try with different phone number")
        print("4. Check if Telegram is accessible")
        
    finally:
        await client.disconnect()
        print("[DISCONNECT] Disconnected")

if __name__ == "__main__":
    asyncio.run(main())
