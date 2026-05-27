import os
import json
import random
from fastapi import FastAPI, Request, Response, BackgroundTasks
from vk_api import VkApi
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
TOKEN = os.getenv("VK_TOKEN")
CONFIRMATION_CODE = os.getenv("CONFIRMATION_CODE")
vk = VkApi(token=TOKEN)

# Временное хранилище состояний (в памяти)
user_states = {}

def get_keyboard():
    return json.dumps({
        "one_time": False,
        "inline": False,
        "buttons": [
            [{"action": {"type": "text", "label": "📝 Сгенерировать пост", "payload": "{\"cmd\":\"generate\"}"}, "color": "primary"},
             {"action": {"type": "text", "label": "#️⃣ Хэштеги", "payload": "{\"cmd\":\"hashtags\"}"}, "color": "secondary"}],
            [{"action": {"type": "text", "label": "👑 Премиум", "payload": "{\"cmd\":\"premium\"}"}, "color": "positive"}]
        ]
    })

def send_message(peer_id: int, text: str, keyboard=None):
    """Функция отправки (выполняется в фоне)"""
    try:
        params = {"peer_id": peer_id, "message": text, "random_id": random.randint(1, 10**9)}
        if keyboard:
            params["keyboard"] = keyboard
        vk.method("messages.send", params)
    except Exception as e:
        print(f"❌ Ошибка отправки сообщения: {e}")

# Функция, которая будет работать в фоне
async def process_user_action(peer_id, text, payload_str, current_state):
    # Определяем команду
    cmd = None
    if payload_str:
        try:
            payload = json.loads(payload_str)
            cmd = payload.get("cmd")
        except Exception:
            pass

    # Логика обработки
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
            # Здесь будет генерация ИИ в будущем
            post_text = f"✨ Пост на тему: {text}\n\nЭто тестовый ответ. Скоро здесь будет нейросеть!\n\n#SMM #Тест"
            send_message(peer_id, post_text, get_keyboard())
            del user_states[peer_id]
            
        elif state == "waiting_hashtag_topic":
            tags = f"#{text} #бизнес #реклама #smm #vk"
            send_message(peer_id, tags, get_keyboard())
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

        # 1. Мгновенный ответ на подтверждение
        if event_type == "confirmation":
            return Response(content=CONFIRMATION_CODE, media_type="text/plain")

        # 2. Если новое сообщение — ставим задачу в фон и сразу отдаем "ok"
        if event_type == "message_new":
            msg = data["object"]["message"]
            peer_id = msg["peer_id"]
            text = msg.get("text", "").strip()
            payload_str = msg.get("payload", "")
            
            # Запускаем обработку в фоне, чтобы не блокировать ответ ВК
            background_tasks.add_task(process_user_action, peer_id, text, payload_str, user_states.get(peer_id))

    except Exception as e:
        print(f"❌ Ошибка в webhook: {e}")

    # 3. Самое важное: отдаем "ok" СРАЗУ, не дожидаясь ответа бота
    return Response(content="ok", media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)