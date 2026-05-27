import os
import json
import random
from fastapi import FastAPI, Request, Response, BackgroundTasks
from vk_api import VkApi
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

app = FastAPI()
TOKEN = os.getenv("VK_TOKEN")
CONFIRMATION_CODE = os.getenv("CONFIRMATION_CODE")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

vk = VkApi(token=TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

user_states = {}

def get_keyboard():
    return json.dumps({
        "one_time": False,
        "inline": False,
        "buttons": [
            [{"action": {"type": "text", "label": " Сгенерировать пост", "payload": "{\"cmd\":\"generate\"}"}, "color": "primary"},
             {"action": {"type": "text", "label": "#️⃣ Хэштеги", "payload": "{\"cmd\":\"hashtags\"}"}, "color": "secondary"}],
            [{"action": {"type": "text", "label": "👑 Премиум", "payload": "{\"cmd\":\"premium\"}"}, "color": "positive"}]
        ]
    })

def send_message(peer_id: int, text: str, keyboard=None):
    try:
        params = {"peer_id": peer_id, "message": text, "random_id": random.randint(1, 10**9)}
        if keyboard:
            params["keyboard"] = keyboard
        vk.method("messages.send", params)
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")

def generate_ai_response(user_prompt: str, system_role: str) -> str:
    if not groq_client:
        return "️ AI-ключ не настроен. Обратись к администратору."
    try:
        response = groq_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": system_role},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=600,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Ошибка Groq API: {e}")
        return f"⚠️ Нейросеть временно недоступна. Попробуй позже."

async def process_user_action(peer_id, text, payload_str):
    cmd = None
    if payload_str:
        try:
            payload = json.loads(payload_str)
            cmd = payload.get("cmd")
        except Exception:
            pass

    if cmd == "generate" or text.lower() == "сгенерировать пост":
        user_states[peer_id] = "waiting_topic"
        send_message(peer_id, "📝 Напиши тему для поста:", get_keyboard())

    elif cmd == "hashtags" or text.lower() == "хэштеги":
        user_states[peer_id] = "waiting_hashtag_topic"
        send_message(peer_id, "#️⃣ Напиши тему для подбора хэштегов:", get_keyboard())

    elif cmd == "premium":
        send_message(peer_id, "👑 Премиум: безлимитная генерация, аналитика, экспорт. Скоро подключение оплаты!", get_keyboard())

    elif peer_id in user_states:
        state = user_states[peer_id]
        if state == "waiting_topic":
            system = "Ты опытный SMM-специалист. Пиши вовлекающие посты для ВКонтакте. Используй эмодзи, разбивай на абзацы, добавляй призыв к действию. Длина: до 800 символов. Только текст поста, без лишних комментариев."
            ai_text = generate_ai_response(f"Тема поста: {text}", system)
            send_message(peer_id, ai_text, get_keyboard())
            del user_states[peer_id]

        elif state == "waiting_hashtag_topic":
            system = "Ты эксперт по хэштегам. Верни ровно 10 релевантных хэштегов на русском языке, разделенных пробелом. Без лишних слов, без нумерации."
            ai_text = generate_ai_response(f"Тема: {text}", system)
            send_message(peer_id, ai_text, get_keyboard())
            del user_states[peer_id]
        else:
            send_message(peer_id, "👋 Привет! Выбери действие:", get_keyboard())
    else:
        send_message(peer_id, "👋 Привет! Я SMM-бот. Выбери действие:", get_keyboard())

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        event_type = data.get("type")

        if event_type == "confirmation":
            return Response(content=CONFIRMATION_CODE, media_type="text/plain")

        if event_type == "message_new":
            msg = data["object"]["message"]
            peer_id = msg["peer_id"]
            text = msg.get("text", "").strip()
            payload_str = msg.get("payload", "")

            background_tasks.add_task(process_user_action, peer_id, text, payload_str)

    except Exception as e:
        print(f"❌ Ошибка в webhook: {e}")

    return Response(content="ok", media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)