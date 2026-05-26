import os
import json
import random
from fastapi import FastAPI, Request, Response
from vk_api import VkApi
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
TOKEN = os.getenv("VK_TOKEN")
CONFIRMATION_CODE = os.getenv("CONFIRMATION_CODE")
vk = VkApi(token=TOKEN)

# Простое хранилище состояний (в памяти, для демо)
user_states = {}

def get_keyboard():
    """Возвращает JSON-строку с кнопками"""
    return json.dumps({
        "one_time": False,
        "inline": False,
        "buttons": [
            [
                {"action": {"type": "text", "label": "📝 Сгенерировать пост", "payload": "{\"cmd\":\"generate\"}"}, "color": "primary"},
                {"action": {"type": "text", "label": "#️⃣ Хэштеги", "payload": "{\"cmd\":\"hashtags\"}"}, "color": "secondary"}
            ],
            [
                {"action": {"type": "text", "label": "👑 Премиум", "payload": "{\"cmd\":\"premium\"}"}, "color": "positive"}
            ]
        ]
    })

def send_message(peer_id: int, text: str, keyboard=None):
    """Отправляет сообщение от имени сообщества"""
    params = {
        "peer_id": peer_id,
        "message": text,
        "random_id": random.randint(1, 10**9)
    }
    if keyboard:
        params["keyboard"] = keyboard
    vk.method("messages.send", params)

def generate_post_template(topic: str) -> str:
    return f"✨ Пост на тему: {topic}\n\nЭто шаблонный ответ. В следующем шаге подключим нейросеть для реальной генерации текста!\n\n#SMM #Контент"

def generate_hashtags(topic: str) -> str:
    return f"#реклама #{topic} #бизнес #маркетинг #vk #smm #контент #продвижение"

@app.post("/webhook")
async def webhook(request: Request):
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

            # Определяем команду из кнопки или текста
            cmd = None
            if payload_str:
                try:
                    payload = json.loads(payload_str)
                    cmd = payload.get("cmd")
                except Exception:
                    pass

            # Обработка команд
            if cmd == "generate" or text.lower() == "сгенерировать пост":
                user_states[peer_id] = "waiting_topic"
                send_message(peer_id, "📝 Напиши тему для поста:", get_keyboard())

            elif cmd == "hashtags" or text.lower() == "хэштеги":
                user_states[peer_id] = "waiting_hashtag_topic"
                send_message(peer_id, "#️⃣ Напиши тему для подбора хэштегов:", get_keyboard())

            elif cmd == "premium":
                send_message(peer_id, "👑 Премиум даст доступ к AI-генерации, аналитике и шаблонам. Скоро подключим оплату!", get_keyboard())

            elif peer_id in user_states:
                state = user_states[peer_id]
                if state == "waiting_topic":
                    post = generate_post_template(text)
                    send_message(peer_id, post, get_keyboard())
                    del user_states[peer_id]
                elif state == "waiting_hashtag_topic":
                    tags = generate_hashtags(text)
                    send_message(peer_id, tags, get_keyboard())
                    del user_states[peer_id]
                else:
                    send_message(peer_id, "👋 Привет! Выбери действие в меню:", get_keyboard())
            else:
                send_message(peer_id, "👋 Привет! Я SMM-бот. Выбери действие:", get_keyboard())

    except Exception as e:
        print(f"❌ Ошибка в webhook: {e}")

    return Response(content="ok", media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)