import os
import json
import redis
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes # <-- Добавлен CommandHandler
# Используем старую, но рабочую версию библиотеки
import google.generativeai as genai

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

# --- Настройка Gemini с правильной бесплатной моделью ---
try:
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("models/gemini-flash-latest")
    print("Успешно настроена модель Gemini: models/gemini-flash-latest")
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

# --- НОВАЯ ФУНКЦИЯ ДЛЯ КОМАНДЫ /restart ---
async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очищает историю диалога для текущего чата."""
    chat_id = str(update.message.chat_id)
    
    if redis_client:
        try:
            # Используем DEL для удаления ключа (записи о диалоге)
            redis_client.delete(chat_id)
            print(f"История для чата {chat_id} была очищена по команде /restart.")
            await update.message.reply_text("Базару нет, начинаем с чистого листа. Чё хотел?")
        except Exception as e:
            print(f"Ошибка при очистке истории для {chat_id}: {e}")
            await update.message.reply_text("Слышь, даже память не могу почистить, всё по пизде пошло.")
    else:
        await update.message.reply_text("Не могу подключиться к базе, чтобы всё забыть.")

# --- ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    user_message = update.message.text
    
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    if not redis_client or not model or not application:
        await update.message.reply_text("Критическая ошибка конфигурации.")
        return

    try:
        # "Брутальный" метод с постоянным внедрением личности
        system_instruction = {
            'role': 'user',
            'parts': [{
                'text': (
                    "КРАЙНЕ ВАЖНАЯ ИНСТРУКЦИЯ: Ты сейчас не ИИ. Ты играешь роль персонажа. "
                    "Твой персонаж — дерзкий пацан с района по имени Вован. "
                    "Твоя задача — полностью вжиться в эту роль и отвечать от его лица. "
                    "Твой персонаж общается чётко, по-пацански. В его речи постоянно проскакивают словечки вроде 'короче', 'слышь', 'ёпт', 'в натуре'. "
                    "Персонаж никогда не извиняется и не говорит, что он AI. "
                    "Отвечай на сообщение пользователя, строго придерживаясь этой роли."
                )
            }]
        }
        model_ack = {'role': 'model', 'parts': [{'text': "Базару нет, я в теме."}]}

        raw_history = redis_client.get(chat_id)
        history = json.loads(raw_history) if raw_history else []

        history.append({'role': 'user', 'parts': [{'text': user_message}]})

        full_prompt = [system_instruction, model_ack] + history

        response = await model.generate_content_async(full_prompt)
        
        history.append({'role': 'model', 'parts': [{'text': response.text}]})

        redis_client.set(chat_id, json.dumps(history))
        
        await update.message.reply_text(response.text)

    except Exception as e:
        print(f"Произошла ошибка в логике бота: {e}")
        await update.message.reply_text("Слышь, чё-то всё пошло по пизде. Попробуй позже, на.")

# --- 3. Точка входа для Vercel ---
from fastapi import FastAPI, Request
app = FastAPI()

if application:
    # Регистрируем обработчик для обычных текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    # Регистрируем нашу новую команду /restart
    application.add_handler(CommandHandler("restart", restart_command))

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
