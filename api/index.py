import os
import json
import redis
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import google.genai as genai

# --- 1. Конфигурация ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
REDIS_URL = os.environ.get('REDIS_URL')

# --- Настройка Redis ---
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    print("Успешно подключено к Redis.")
except Exception as e:
    redis_client = None
    print(f"Не удалось подключиться к Redis: {e}")

# --- Настройка Gemini с ПРАВИЛЬНЫМ именем модели ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    # Используем имя из списка, который мы получили
    model = genai.GenerativeModel("models/gemini-pro-latest") 
    print("Успешно настроена модель Gemini: models/gemini-pro-latest")
except Exception as e:
    model = None
    print(f"Не удалось настроить Gemini: {e}")

# --- Создание приложения Telegram ---
try:
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    print("Приложение Telegram успешно создано.")
except Exception as e:
    application = None
    print(f"Не удалось создать приложение Telegram: {e}")

# --- 2. Логика бота ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    user_message = update.message.text
    
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    if not redis_client or not model or not application:
        error_message = "Критическая ошибка конфигурации. "
        if not redis_client: error_message += "Нет подключения к базе. "
        if not model: error_message += "Нет подключения к AI. "
        if not application: error_message += "Ошибка приложения Telegram. "
        await update.message.reply_text(error_message)
        return

    try:
        raw_history = redis_client.get(chat_id)
        history = json.loads(raw_history) if raw_history else []
        
        chat_session = model.start_chat(history=history)
        response = await chat_session.send_message_async(user_message)

        updated_history_json = json.dumps([
            {'role': msg.role, 'parts': [{'text': part.text} for part in msg.parts]}
            for msg in chat_session.history
        ])
        redis_client.set(chat_id, updated_history_json)
        
        await update.message.reply_text(response.text)

    except Exception as e:
        print(f"Произошла ошибка в логике бота: {e}")
        await update.message.reply_text("Ой, что-то сломалось. Попробуйте еще раз.")

# --- 3. Точка входа для Vercel ---
from fastapi import FastAPI, Request
app = FastAPI()

if application:
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app.on_event("startup")
async def startup():
    if application:
        await application.initialize()

@app.on_event("shutdown")
async def shutdown():
    if application:
        await application.shutdown()

@app.post("/api")
async def webhook_handler(request: Request):
    if application:
        await application.process_update(
            Update.de_json(await request.json(), application.bot)
        )
    return {"status": "ok"}
