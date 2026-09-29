import os
import threading
import asyncio
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

from google import genai
from google.genai import types
from groq import Groq

# ================= Configuration =================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TARGET_BOT_USERNAME = "ghost475_bot"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 4 Fallback Groq API Keys loaded safely from environment
GROQ_KEYS = [
    os.getenv("GROQ_KEY_1"),
    os.getenv("GROQ_KEY_2"),
    os.getenv("GROQ_KEY_3"),
    os.getenv("GROQ_KEY_4"),
]
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# ================= Render Dummy Server =================
# Render requires a web server to pass health checks, otherwise it kills the bot.
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is running!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

# ================= Bot Logic =================
async def handle_bot_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.from_user:
        return

    # DEBUG PRINT: Show all incoming group messages in your Mac Terminal / Render Logs
    sender_username = message.from_user.username or "NoUsername"
    print(f"📩 Received message from @{sender_username}: {message.text or message.caption}")

    # Check if message is from the ghost bot (case-insensitive)
    if sender_username.lower() == TARGET_BOT_USERNAME.lower():
        print("✅ Message identified from target ghost bot! Generating reply...")
        prompt_text = message.caption or message.text or "Analyze this image."

        # Case 1: Image attached -> Use Gemini
        if message.photo:
            await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")
            try:
                photo_file = await message.photo[-1].get_file()
                image_bytes = await photo_file.download_as_bytearray()
                
                response = gemini_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        types.Part.from_bytes(data=bytes(image_bytes), mime_type="image/jpeg"),
                        prompt_text,
                    ],
                )
                answer = response.text
            except Exception as e:
                answer = f"Error processing image with Gemini: {e}"

        # Case 2: Text only -> Use Groq with Fallbacks
        elif message.text:
            await context.bot.send_chat_action(chat_id=message.chat_id, action="typing")
            answer = "Error: All Groq API keys failed or are invalid."
            
            for i, key in enumerate(GROQ_KEYS):
                if not key or "YOUR_GROQ_KEY" in key:
                    continue
                    
                try:
                    groq_client = Groq(api_key=key)
                    chat_completion = groq_client.chat.completions.create(
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant providing concise answers."},
                            {"role": "user", "content": prompt_text},
                        ],
                        model="llama-3.3-70b-versatile",
                    )
                    answer = chat_completion.choices[0].message.content
                    break
                except Exception as e:
                    print(f"⚠️ Groq Key {i+1} failed: {e}. Trying next...")
                    continue
        else:
            return

        # Reply directly in group
        await message.reply_text(answer)
        print("🚀 Reply sent successfully!")

if __name__ == "__main__":
    # Start the dummy web server on a background thread for Render
    threading.Thread(target=run_web_server, daemon=True).start()

    # Start the Telegram Bot
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO) & (~filters.COMMAND), handle_bot_message))
    
    print("Responder Bot running with Groq Fallbacks + Gemini Vision...")
    
    # --- Fix for Render (Python 3.14+ asyncio loop handling) ---
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # -----------------------------------------------------------
    
    app.run_polling()
