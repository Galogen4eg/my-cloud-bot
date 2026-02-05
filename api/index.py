import os
import json
import redis
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
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
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.message.chat_id)
    user_message = update.message.text
    
    await context.bot.send_chat_action(chat_id=chat_id, action='typing')

    if not redis_client or not model or not application:
        await update.message.reply_text("Критическая ошибка конфигурации.")
        return

    try:
        # --- ГЛАВНОЕ ИЗМЕНЕНИЕ: "БРУТАЛЬНЫЙ" МЕТОД ---

        # 1. Формируем "сценарий" для актера
        # Системная инструкция, которую мы будем давать КАЖДЫЙ раз
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
        # "Фальшивый" ответ, чтобы модель поняла, как начать
        model_ack = {'role': 'model', 'parts': [{'text': "Базару нет, я в теме."}]}

        # Загружаем старую историю
        raw_history = redis_client.get(chat_id)
        history = json.loads(raw_history) if raw_history else []

        # Добавляем новый вопрос пользователя в историю
        history.append({'role': 'user', 'parts': [{'text': user_message}]})

        # Собираем полный "пакет" для отправки: инструкция + история
        full_prompt = [system_instruction, model_ack] + history

        # 2. Вызываем актера на сцену
        # Используем базовый метод, а не сессию
        response = await model.generate_content_async(full_prompt)
        
        # 3. Сохраняем результат
        # Добавляем ответ модели в историю для следующего раза
        history.append({'role': 'model', 'parts': [{'text': response.text}]})

        # Сохраняем обновленную историю в Redis
        redis_client.set(chat_id, json.dumps(history))
        
        # Отправляем ответ пользователю
        await update.message.reply_text(response.text)

    except Exception as e:
        print(f"Произошла ошибка в логике бота: {e}")
        await update.message.reply_text("Слышь, чё-то всё пошло по пизде. Попробуй позже, на.")

# --- 3. Точка входа для Vercel (остается без изменений) ---
from fastapi import FastAPI, Request
app = FastAPI()
if application:
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
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
    return {"status": "ok"}
