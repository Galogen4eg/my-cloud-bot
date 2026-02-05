import os
import json
import redis
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import google.generativeai as genai

# --- 1. Конфигурация ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
REDIS_URL = os.environ.get('REDIS_URL')

# --- 2. ДИАГНОСТИЧЕСКИЙ БЛОК ---
# Мы пытаемся получить список моделей и распечатать его
try:
    genai.configure(api_key=GEMINI_API_KEY)
    print("--- СПИСОК ДОСТУПНЫХ МОДЕЛЕЙ ---")
    for m in genai.list_models():
        # Нас интересуют только те модели, которые поддерживают наш метод
        if 'generateContent' in m.supported_generation_methods:
            print(m.name)
    print("---------------------------------")
    model_name_to_use = "models/gemini-1.5-flash" # Попробуем эту как запасной вариант
    model = genai.GenerativeModel(model_name_to_use)
    print(f"Успешно настроена модель: {model_name_to_use}")

except Exception as e:
    print(f"!!! КРИТИЧЕСКАЯ ОШИБКА НАСТРОЙКИ GEMINI: {e}")
    model = None

# --- Остальная конфигурация (без изменений) ---
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    print("Успешно подключено к Redis.")
except Exception as e:
    redis_client = None
    print(f"Не удалось подключиться к Redis: {e}")

# --- 3. Точка входа и логика (без изменений) ---
# ... (весь остальной код остается прежним) ...
application = Application.builder().token(TELEGRAM_TOKEN).build()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    user_message = update.message.text
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')
    if not redis_client or not model:
        await update.message.reply_text("Ошибка: нет подключения к базе или AI модели.")
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

from fastapi import FastAPI, Request
app = FastAPI()
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app.on_event("startup")
async def startup():
    await application.initialize()
@app.on_event("shutdown")
async def shutdown():
    await application.shutdown()
@app.post("/api")
async def webhook_handler(request: Request):
    await application.process_update(
        Update.de_json(await request.json(), application.bot)
    )
    return {"status": "ok"}
