import os
import json
import random
import re
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

# Хранилище контекста пользователей
user_context = {}
DEFAULT_SETTINGS = {"style": "balanced", "length": "medium", "emoji": "normal"}

def get_main_keyboard():
    return json.dumps({
        "one_time": False, "inline": False,
        "buttons": [
            [{"action": {"type": "text", "label": " Сгенерировать пост", "payload": "{\"cmd\":\"generate\"}"}, "color": "primary"}],
            [{"action": {"type": "text", "label": "#️⃣ Хэштеги", "payload": "{\"cmd\":\"hashtags\"}"}, "color": "secondary"},
             {"action": {"type": "text", "label": "⚙️ Настройки", "payload": "{\"cmd\":\"settings\"}"}, "color": "default"}],
            [{"action": {"type": "text", "label": "👑 Премиум", "payload": "{\"cmd\":\"premium\"}"}, "color": "positive"}]
        ]
    })

def get_settings_keyboard(settings):
    style_map = {"balanced": "️ Баланс", "strict": " Строго", "casual": "😊 Легко", "list": "📋 Список", "story": "📖 История"}
    len_map = {"short": "🔹 Коротко", "medium": "🔸 Средне", "long": "🔺 Подробно"}
    emoji_map = {"off": "😶 Без", "minimal": "✨ Мало", "normal": "🎨 Норма", "rich": "🌈 Много"}
    
    return json.dumps({
        "one_time": False, "inline": False,
        "buttons": [
            [{"action": {"type": "text", "label": len_map.get(settings["length"], " Средне"), "payload": "{\"cmd\":\"len_next\"}"}, "color": "primary"},
             {"action": {"type": "text", "label": emoji_map.get(settings["emoji"], "🎨 Норма"), "payload": "{\"cmd\":\"emoji_next\"}"}, "color": "positive"}],
            [{"action": {"type": "text", "label": style_map.get(settings["style"], "⚖️ Баланс"), "payload": "{\"cmd\":\"style_next\"}"}, "color": "secondary"},
             {"action": {"type": "text", "label": "🔄 Сброс", "payload": "{\"cmd\":\"reset\"}"}, "color": "default"}],
            [{"action": {"type": "text", "label": " В меню", "payload": "{\"cmd\":\"back\"}"}, "color": "default"}]
        ]
    })

def clean_vk_text(text: str) -> str:
    """Полная очистка от Markdown для ВКонтакте"""
    if not text: return ""
    # Удаляем жирный/курсив/код
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    # Удаляем заголовки и цитаты
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    # Чистим остаточные символы
    text = text.replace('**', '').replace('__', '')
    # Нормализуем переносы и пробелы
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()

def build_system_prompt(topic, settings):
    style_map = {
        "balanced": "Профессиональный, сбалансированный тон.",
        "strict": "Деловой, сухой, фактологичный стиль. Без эмоций.",
        "casual": "Легкий, дружеский, с элементами юмора.",
        "list": "Четкая структура, списки, пункты.",
        "story": "Повествовательный, вовлекающий сторителлинг."
    }
    len_map = {
        "short": "Коротко: до 300 символов. Только суть.",
        "medium": "Средне: 400-600 символов. Оптимально для ленты ВК.",
        "long": "Подробно: до 1000 символов. Глубокое погружение."
    }
    emoji_map = {
        "off": "Без эмодзи.",
        "minimal": "Минимум эмодзи (1-2 шт в заголовке).",
        "normal": "Умеренно (3-5 шт, как акценты).",
        "rich": "Ярко (5-8 шт, но без спама)."
    }

    return f"""Ты — эксперт по контенту для ВКонтакте. Твоя задача — написать готовый к публикации пост.

ТЕМА: {topic}

НАСТРОЙКИ:
- Стиль: {style_map.get(settings['style'], '')}
- Объем: {len_map.get(settings['length'], '')}
- Эмодзи: {emoji_map.get(settings['emoji'], '')}

🚫 ЖЕСТКИЕ ПРАВИЛА ФОРМАТИРОВАНИЯ (ВК НЕ ПОДДЕРЖИВАЕТ MARKDOWN):
1. ЗАПРЕЩЕНО использовать **, *, #, _, `, >. Они испортят текст.
2. ЗАГОЛОВКИ пиши ЗАГЛАВНЫМИ БУКВАМИ (например: ИСТОРИЯ КОФЕ).
3. Списки оформляй через • или ✓ или —.
4. Обязательно делай пустую строку между абзацами для «воздуха».
5. Пиши грамотно, живо и естественно.
6. В конце обязательно задай вопрос аудитории или призови к действию.

Пример идеальной структуры:
ЗАГОЛОВОК ПОСТА

Вводный абзац, цепляющий внимание...

• Пункт 1
• Пункт 2

Заключительная мысль и вопрос к читателям?"""

def send_message(peer_id: int, text: str, keyboard=None):
    try:
        clean_text = clean_vk_text(text)
        params = {"peer_id": peer_id, "message": clean_text, "random_id": random.randint(1, 10**9)}
        if keyboard: params["keyboard"] = keyboard
        vk.method("messages.send", params)
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")

def generate_ai_response(prompt: str, system_role: str) -> str:
    if not groq_client:
        return "️ AI-ключ не настроен."
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": system_role}, {"role": "user", "content": prompt}],
            max_tokens=900, temperature=0.75
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Groq Error: {e}")
        return f"⚠️ Ошибка нейросети. Попробуйте позже."

async def process_user_action(peer_id, text, payload_str):
    if peer_id not in user_context:
        user_context[peer_id] = {"state": "menu", "settings": DEFAULT_SETTINGS.copy()}

    ctx = user_context[peer_id]
    cmd = None
    if payload_str:
        try: cmd = json.loads(payload_str).get("cmd")
        except: pass

    # --- Кнопки главного меню ---
    if cmd == "generate":
        ctx["state"] = "waiting_topic"
        s = ctx["settings"]
        send_message(peer_id, f"📝 Напишите тему или просто пришлите запрос (например: «напиши пост про кофе»).\n\n⚙️ Текущие настройки:\n• Стиль: {s['style']}\n• Объем: {s['length']}\n• Эмодзи: {s['emoji']}", get_main_keyboard())

    elif cmd == "hashtags":
        ctx["state"] = "waiting_hashtag"
        send_message(peer_id, "#️⃣ Напишите тему для подбора хэштегов:", get_main_keyboard())

    elif cmd == "premium":
        send_message(peer_id, "👑 Премиум-функции в разработке! Скоро: аналитика, автопостинг, шаблоны.", get_main_keyboard())

    elif cmd == "settings":
        ctx["state"] = "settings"
        send_message(peer_id, "️ Настройки генерации. Нажимайте кнопки для переключения:", get_settings_keyboard(ctx["settings"]))

    elif cmd == "len_next":
        cycle = ["short", "medium", "long"]
        ctx["settings"]["length"] = cycle[(cycle.index(ctx["settings"]["length"]) + 1) % 3]
        send_message(peer_id, f"✅ Объем изменен: {ctx['settings']['length']}", get_settings_keyboard(ctx["settings"]))

    elif cmd == "emoji_next":
        cycle = ["off", "minimal", "normal", "rich"]
        ctx["settings"]["emoji"] = cycle[(cycle.index(ctx["settings"]["emoji"]) + 1) % 4]
        send_message(peer_id, f"✅ Эмодзи изменены: {ctx['settings']['emoji']}", get_settings_keyboard(ctx["settings"]))

    elif cmd == "style_next":
        cycle = ["balanced", "strict", "casual", "list", "story"]
        ctx["settings"]["style"] = cycle[(cycle.index(ctx["settings"]["style"]) + 1) % 5]
        send_message(peer_id, f"✅ Стиль изменен: {ctx['settings']['style']}", get_settings_keyboard(ctx["settings"]))

    elif cmd == "reset":
        ctx["settings"] = DEFAULT_SETTINGS.copy()
        send_message(peer_id, "🔄 Настройки сброшены.", get_settings_keyboard(ctx["settings"]))

    elif cmd == "back":
        ctx["state"] = "menu"
        send_message(peer_id, "🔙 Главное меню:", get_main_keyboard())

    # --- Текстовый ввод ---
    elif text:
        if ctx["state"] in ["waiting_topic", "menu"]:
            ctx["state"] = "generating"
            send_message(peer_id, "⏳ Генерирую...", None)
            system_prompt = build_system_prompt(text, ctx["settings"])
            ai_text = generate_ai_response(text, system_prompt)
            send_message(peer_id, ai_text, get_main_keyboard())
            ctx["state"] = "menu"

        elif ctx["state"] == "waiting_hashtag":
            sys_h = "Подбери 12 релевантных хэштегов на русском языке. Только список через пробел. Без лишних слов и объяснений."
            ai_hash = generate_ai_response(text, sys_h)
            send_message(peer_id, ai_hash, get_main_keyboard())
            ctx["state"] = "menu"

        else:
            send_message(peer_id, "Выберите действие в меню:", get_main_keyboard())

@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        data = await request.json()
        if data.get("type") == "confirmation":
            return Response(content=CONFIRMATION_CODE, media_type="text/plain")
        if data.get("type") == "message_new":
            msg = data["object"]["message"]
            background_tasks.add_task(process_user_action, msg["peer_id"], msg.get("text", "").strip(), msg.get("payload", ""))
    except Exception as e:
        print(f"❌ Webhook error: {e}")
    return Response(content="ok", media_type="text/plain")