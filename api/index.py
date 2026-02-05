import os
import json
import redis
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from groq import Groq

# --- 1. Конфигурация ---
GROQ_API_KEY = os.environ.get('GROQ_API_KEY')
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
REDIS_URL = os.environ.get('REDIS_URL')

# --- Настройка Redis (без изменений) ---
try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    print("Успешно подключено к Redis.")
except Exception as e:
    redis_client = None
    print(f"Не удалось подключиться к Redis: {e}")

# --- Настройка Groq с ПРАВИЛЬНЫМ именем модели ---
try:
    groq_client = Groq(api_key=GROQ_API_KEY)
    # ВЫБИРАЕМ АКТУАЛЬНУЮ МОДЕЛЬ ИЗ СПИСКА
    MODEL_NAME = "llama-3.1-8b-instant"
    print(f"Успешно настроен клиент Groq с моделью: {MODEL_NAME}")
except Exception as e:
    groq_client = None
    MODEL_NAME = None
    print(f"Не удалось настроить Groq: {e}")

# --- Создание приложения Telegram (без изменений) ---
try:
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    print("Приложение Telegram успешно создано.")
except Exception as e:
    application = None
    print(f"Не удалось создать приложение Telegram: {e}")

# --- 2. Логика бота ---

# --- Команда /restart (без изменений) ---
async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    if redis_client:
        try:
            redis_client.delete(chat_id)
            await update.message.reply_text("Базару нет, начинаем с чистого листа. Чё хотел?")
        except Exception as e:
            await update.message.reply_text("Слышь, даже память не могу почистить.")
    else:
        await update.message.reply_text("Не могу подключиться к базе, чтобы всё забыть.")

# --- ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    user_message = update.message.text
    
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    if not redis_client or not groq_client or not application:
        await update.message.reply_text("Критическая ошибка конфигурации.")
        return

    try:
        system_instruction = {
            "role": "system",
            "content": (
                "Ты — дерзкий пацан с района по имени Вован. Ты общаешься чётко, по-пацански. "
                "В твоей речи постоянно проскакивают словечки вроде 'короче', 'слышь', 'ёпт', 'в натуре'. "
                "Можешь использовать мат, но по делу. Ты никогда не извиняешься и не говоришь, что ты AI. "
                "Строго придерживайся этой роли."
            )
        }

        raw_history = redis_client.get(chat_id)
        history = json.loads(raw_history) if raw_history else []

        history.append({"role": "user", "content": user_message})

        full_prompt = [system_instruction] + history

        chat_completion = groq_client.chat.completions.create(
            messages=full_prompt,
            model=MODEL_NAME,
        )
        
        response_text = chat_completion.choices[0].message.content
        history.append({"role": "assistant", "content": response_text})
        
        redis_client.set(chat_id, json.dumps(history))
        
        await update.message.reply_text(response_text)

    except Exception as e:
        print(f"Произошла ошибка в логике бота: {e}")
        await update.message.reply_text("Слышь, чё-то всё пошло по пизде. Попробуй позже, на.")

# --- 3. Точка входа для Vercel (без изменений) ---
from fastapi import FastAPI, Request
app = FastAPI()

if application:
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CommandHandler("restart", restart_command))

@app.on_event("startup")
async def startup():
    if application: await application.initialize()
@app.on_event("shutdown")
async def shutdown():
    if application: await application.shutdown()
@app.post("/api")
async def webhook_handler(request: Request):
    if application:
        await application.process_update(
            Update.de_json(await request.json(), application.bot)
        )
    return {"sta
