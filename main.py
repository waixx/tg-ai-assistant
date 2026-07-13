import os
import time
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from firebase_admin import credentials, firestore, initialize_app

# -------------------------
# 1. Инициализация Firebase
# -------------------------
if not os.getenv("FB_PROJECT_ID"):
    raise ValueError("Не задана FB_PROJECT_ID в переменных окружения!")

cred_dict = {
    "type": "service_account",
    "project_id": os.getenv("FB_PROJECT_ID"),
    "private_key_id": os.getenv("FB_PRIVATE_KEY_ID"),
    "private_key": os.getenv("FB_PRIVATE_KEY").replace("\\n", "\n"),
    "client_email": os.getenv("FB_CLIENT_EMAIL"),
    "client_id": os.getenv("FB_CLIENT_ID"),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.getenv("FB_CLIENT_X509_CERT_URL"),
}
cred = credentials.Certificate(cred_dict)
initialize_app(cred)
db = firestore.client()

CHAT_COLLECTION = "chats"
PROFILE_COLLECTION = "profiles"
MAX_CONTEXT_MESSAGES = 15
DAYS_TO_KEEP = 7

def get_chat_doc(chat_id: int):
    return db.collection(CHAT_COLLECTION).document(str(chat_id))

def get_profile_doc(chat_id: int):
    return db.collection(PROFILE_COLLECTION).document(str(chat_id))

async def save_message(chat_id: int, role: str, content: str):
    doc_ref = get_chat_doc(chat_id)
    doc_ref.set(
        {
            "messages": firestore.ArrayUnion([
                {"role": role, "content": content, "ts": time.time()}
            ])
        },
        merge=True
    )
    archive_old_messages(chat_id)  # архивация сразу после сохранения

def archive_old_messages(chat_id: int):
    cutoff = time.time() - (DAYS_TO_KEEP * 24 * 60 * 60)
    doc = get_chat_doc(chat_id).get()
    if not doc.exists:
        return
    data = doc.to_dict() or {}
    messages = data.get("messages", [])
    filtered = [m for m in messages if m["ts"] >= cutoff]
    if len(filtered) < len(messages):
        get_chat_doc(chat_id).set({"messages": filtered}, merge=True)

async def get_context(chat_id: int):
    doc = get_chat_doc(chat_id).get()
    if not doc.exists:
        return []
    data = doc.to_dict() or {}
    messages = data.get("messages", [])
    messages.sort(key=lambda x: x["ts"])
    return [{"role": m["role"], "content": m["content"]} for m in messages[-MAX_CONTEXT_MESSAGES:]]

async def save_fact(chat_id: int, key: str, value: str):
    profile_doc = get_profile_doc(chat_id)
    profile = profile_doc.get().to_dict() or {}
    profile[key] = value
    profile_doc.set(profile, merge=True)

async def get_facts(chat_id: int) -> dict:
    profile = get_profile_doc(chat_id).get().to_dict() or {}
    return profile

# -------------------------
# 2. Заглушки для DeepSeek и Serp
# -------------------------
async def call_deepseek(context, user_text):
    # Сюда потом вставишь реальный вызов DeepSeek
    return "[DeepSeek: тут будет реальный ответ по контексту и запросу]"

async def call_serp(query):
    # Сюда потом вставишь реальный вызов Serp API
    return "[Serp: тут будут результаты поиска по запросу]"

# -------------------------
# 3. Обработчики бота
# -------------------------
bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
dp = Dispatcher()

@dp.message()
async def handle_message(message: types.Message):
    chat_id = message.chat.id
    user_text = message.text or ""

    await save_message(chat_id, "user", user_text)
    context = await get_context(chat_id)

    # Здесь можно сначала вызвать Serp, потом передать результаты в DeepSeek
    # search_results = await call_serp(user_text)
    # response = await call_deepseek(context + [{"role":"system","content":search_results}], user_text)

    response = await call_deepseek(context, user_text)

    await save_message(chat_id, "assistant", response)
    await message.answer(response)

@dp.command(Command("fact"))
async def cmd_fact(message: types.Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer("Используй: /fact <ключ> <значение>, например: /fact город Москва")
        return
    key, value = args[1], args[2]
    await save_fact(message.chat.id, key, value)
    await message.answer(f"Запомнил: {key} = {value}")

@dp.command(Command("facts"))
async def cmd_facts(message: types.Message):
    facts = await get_facts(message.chat.id)
    if not facts:
        await message.answer("Пока нет сохранённых фактов.")
    else:
        text = "Твои факты:\n" + "\n".join(f"- {k}: {v}" for k, v in facts.items())
        await message.answer(text)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
