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
            [{"action": {"type": "text", "label": "📝 Сгенерировать пост", "payload": "{\"cmd\":\"generate\"}"}, "color": "primary"},
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
    print(f" Вызов Groq API...")
    
    if not groq_client:
        return "️ AI-ключ не настроен."
    
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant", # Актуальная бесплатная модель
            messages=[
                {"role": "system", "content": system_role},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=600,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"❌ Groq Error: {e}")
        return f"⚠️ Нейросеть временно недоступна."

async def process_user_action(peer_id, text, payload_str):
    cmd = None
    if payload_str:
        try:
            payload = json.loads(payload_str)
            cmd = payload.get("cmd")
        except Exception:
            pass

    # --- Логика генерации поста ---
    if cmd == "generate" or text.lower() == "сгенерировать пост":
        user_states[peer_id] = "waiting_topic"
        send_message(peer_id, "📝 Напиши тему для поста.\n💡 *Совет:* Добавь стиль через запятую (например: 'Кофе, строго' или 'Кофе, весело').", get_keyboard())

    elif cmd == "hashtags" or text.lower() == "хэштеги":
        user_states[peer_id] = "waiting_hashtag_topic"
        send_message(peer_id, "#️⃣ Напиши тему для хэштегов:", get_keyboard())

    elif cmd == "premium":
        send_message(peer_id, "👑 Премиум: безлимитная генерация и аналитика. Скоро!", get_keyboard())

    # --- Обработка ответа пользователя (тема поста) ---
    elif peer_id in user_states:
        state = user_states[peer_id]
        
        if state == "waiting_topic":
            # 🧠 УМНЫЙ РЕЖИМ: Определяем стиль по ключевым словам
            text_lower = text.lower()
            style_instruction = "Профессиональный, сбалансированный стиль. Умеренное использование эмодзи."
            
            if any(w in text_lower for w in ["строго", "серьезно", "научно", "официально", "сухо"]):
                style_instruction = "СТРОГИЙ СТИЛЬ: Пиши сухо, фактологично, как в научной статье или деловом отчете. ЗАПРЕЩЕНО использовать смайлики и эмоции."
            elif any(w in text_lower for w in ["весело", "легко", "дружелюбно", "с юмором", "позитивно", "зазывающе"]):
                style_instruction = "ЛЕГКИЙ СТИЛЬ: Пиши живо, эмоционально, с юмором. Можно использовать смайлики, но не более 5 штук."
            
            # Формируем строгий системный промпт против спама смайлами
            system_prompt = f"""Ты профессиональный SMM-специалист.
Твоя задача: написать пост на тему "{text}".
Стиль: {style_instruction}

ВАЖНЫЕ ПРАВИЛА:
1. 🚫 ЗАПРЕТ НА СПАМ СМАЙЛИКАМИ: Используй МАКСИМУМ 3-4 смайлика на весь текст. Не ставь смайлик в конце каждого предложения.
2. Текст должен быть структурирован: Заголовок, Основная часть, Призыв к действию.
3. Никакой воды, только польза."""

            ai_text = generate_ai_response(f"Тема: {text}", system_prompt)
            send_message(peer_id, ai_text, get_keyboard())
            del user_states[peer_id]

        elif state == "waiting_hashtag_topic":
            system_prompt = "Ты эксперт по SEO. Подбери ровно 10 релевантных хэштегов на русском языке. Только список через пробел, без лишних слов."
            ai_text = generate_ai_response(f"Тема: {text}", system_prompt)
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