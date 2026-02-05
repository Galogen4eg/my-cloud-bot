import os
import json
import redis # <-- ИСПОЛЬЗУЕМ НОВУЮ, НАДЕЖНУЮ БИБЛИОТЕКУ
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import google.genai as genai

# --- 1. Конфигурация ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
REDIS_URL = os.environ.get('REDIS_URL')

# --- ГЛАВНОЕ ИЗМЕНЕНИЕ ---
# Создаем Redis клиент напрямую из URL.
# decode_responses=True - важная настройка, чтобы получать строки, а не байты.
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    print("Успешно подключено к Redis.")
except Exception as e:
    print(f"Не удалось подключиться к Redis: {e}")
    redis_client = None
# -------------------------

# Настраиваем Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# --- 2. Логика бота, адаптированная под Redis ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    user_message = update.message.text
    
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    if not redis_client:
        await update.message.reply_text("Ошибка: нет подключения к базе данных памяти.")
        return

    try:
        # Читаем историю из Redis
        raw_history = redis_client.get(chat_id)
        history = json.loads(raw_history) if raw_history else []
        print(f"Загружена история для {chat_id}, {len(history)} сообщений.")

        chat_session = model.start_chat(history=history)
        response = await chat_session.send_message_async(user_message)

        # Сохраняем историю в Redis
        updated_history_json = json.dumps([
            {'role': msg.role, 'parts': [{'text': part.text} for part in msg.parts]}
            for msg in chat_session.history
        ])
        redis_client.set(chat_id, updated_history_json)
        
        await update.message.reply_text(response.text)

    except Exception as e:
        print(f"Произошла ошибка в логике бота: {e}")
        await update.message.reply_text("Ой, что-то сломалось. Попробуйте еще раз.")

# --- 3. Точка входа для Vercel (не меняется) ---
from fastapi import FastAPI, Request
app = FastAPI()

@app.post("/api")
async def webhook_handler(request: Request):
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    update = Update.de_json(await request.json(), application.bot)
    await application.process_update(update)
    return {"status": "ok"}
