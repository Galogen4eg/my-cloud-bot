import os
import json
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import google.genai as genai  # <-- ИЗМЕНЕНИЕ 1
from vercel_kv.redis import VercelKV  # <-- ИЗМЕНЕНИЕ 2

# --- 1. Конфигурация ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')

# Создаем объект для работы с KV
kv_client = VercelKV()  # <-- ИЗМЕНЕНИЕ 3

# Настраиваем Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# --- 2. Логика бота с обновленным кодом ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    user_message = update.message.text
    
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    try:
        # Загружаем историю, используя новый kv_client
        raw_history = kv_client.get(chat_id)  # <-- ИЗМЕНЕНИЕ 4
        history = json.loads(raw_history) if raw_history else []
        print(f"Загружена история для {chat_id}, {len(history)} сообщений.")

        chat_session = model.start_chat(history=history)
        response = await chat_session.send_message_async(user_message)

        # Сохраняем историю, используя новый kv_client
        updated_history_json = json.dumps([
            {'role': msg.role, 'parts': [{'text': part.text} for part in msg.parts]}
            for msg in chat_session.history
        ])
        kv_client.set(chat_id, updated_history_json)  # <-- ИЗМЕНЕНИЕ 5
        
        await update.message.reply_text(response.text)

    except Exception as e:
        print(f"Произошла ошибка: {e}")
        await update.message.reply_text("Ой, произошла ошибка. Пожалуйста, попробуйте еще раз.")

# --- 3. Точка входа для Vercel ---
from fastapi import FastAPI, Request
app = FastAPI()

@app.post("/api")
async def webhook_handler(request: Request):
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    update = Update.de_json(await request.json(), application.bot)
    await application.process_update(update)
    return {"status": "ok"}
