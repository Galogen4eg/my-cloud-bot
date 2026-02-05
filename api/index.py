import os
import json
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import google.genai as genai
from vercel_kv import VercelKV # Импорт остается таким же

# --- 1. Конфигурация ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')

# --- ГЛАВНОЕ ИЗМЕНЕНИЕ ---
# Мы вручную читаем URL из переменных окружения
# и передаем его для создания клиента KV.
redis_url_from_env = os.environ.get('REDIS_URL')
kv_client = VercelKV(url=redis_url_from_env)
# -------------------------

# Настраиваем Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# --- 2. Логика бота (не меняется) ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    user_message = update.message.text
    
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    try:
        raw_history = kv_client.get(chat_id)
        history = json.loads(raw_history) if raw_history else []
        print(f"Загружена история для {chat_id}, {len(history)} сообщений.")

        chat_session = model.start_chat(history=history)
        response = await chat_session.send_message_async(user_message)

        updated_history_json = json.dumps([
            {'role': msg.role, 'parts': [{'text': part.text} for part in msg.parts]}
            for msg in chat_session.history
        ])
        kv_client.set(chat_id, updated_history_json)
        
        await update.message.reply_text(response.text)

    except Exception as e:
        print(f"Произошла ошибка: {e}")
        await update.message.reply_text("Ой, произошла ошибка. Пожалуйста, попробуйте еще раз.")

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

