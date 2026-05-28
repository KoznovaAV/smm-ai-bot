import os
import json
import random
import re
import sys
import logging
from fastapi import FastAPI, Request, Response, BackgroundTasks
from vk_api import VkApi
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# Настройка логирования (гарантированно попадает в Render)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI()
TOKEN = os.getenv("VK_TOKEN")
CONFIRMATION_CODE = os.getenv("CONFIRMATION_CODE")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY")

if not YANDEX_API_KEY:
    logger.error("❌ YANDEX_API_KEY не найден в переменных среды Render!")

# Клиент YandexGPT через OpenAI-совместимый API
ai_client = OpenAI(
    api_key=YANDEX_API_KEY,
    base_url="https://llm.api.cloud.yandex.net/foundationModels/v1/openai/v1"
)

vk = VkApi(token=TOKEN)
user_context = {}
DEFAULT_SETTINGS = {"style": "balanced", "length": "medium", "emoji": "normal"}

# ================= КЛАВИАТУРЫ =================

def get_main_keyboard():
    return json.dumps({
        "one_time": False, "inline": False,
        "buttons": [
            [{"action": {"type": "text", "label": "📝 Сгенерировать пост", "payload": json.dumps({"cmd":"generate"})}, "color": "primary"}],
            [{"action": {"type": "text", "label": "#️⃣ Хэштеги", "payload": json.dumps({"cmd":"hashtags"})}, "color": "secondary"},
             {"action": {"type": "text", "label": "⚙️ Настройки", "payload": json.dumps({"cmd":"settings"})}, "color": "default"}],
            [{"action": {"type": "text", "label": "👑 Премиум", "payload": json.dumps({"cmd":"premium"})}, "color": "positive"}]
        ]
    })

def get_settings_keyboard(settings):
    def btn(label, cmd, is_active=False):
        return {
            "action": {"type": "text", "label": label, "payload": json.dumps({"cmd": cmd})},
            "color": "primary" if is_active else "default"
        }

    len_opts = [("🔹 Коротко", "set_len_short"), ("🔸 Средне", "set_len_medium"), ("🔺 Длинно", "set_len_long")]
    emoji_opts = [(" Без", "set_emoji_off"), ("✨ Мало", "set_emoji_minimal"), ("🎨 Норма", "set_emoji_normal"), ("🌈 Много", "set_emoji_rich")]
    style_opts = [("👔 Строго", "set_style_strict"), ("😊 Легко", "set_style_casual"), ("📋 Список", "set_style_list"), ("📖 История", "set_style_story"), ("⚖️ Баланс", "set_style_balanced")]

    rows = [
        [btn(l, c, settings["length"] == c.split("_")[-1]) for l, c in len_opts],
        [btn(e, c, settings["emoji"] == c.split("_")[-1]) for e, c in emoji_opts],
        [btn(s, c, settings["style"] == c.split("_")[-1]) for s, c in style_opts],
        [{"action": {"type": "text", "label": "🔙 В главное меню", "payload": json.dumps({"cmd": "back"})}, "color": "negative"}]
    ]
    return json.dumps({"one_time": False, "inline": False, "buttons": rows})

# ================= ОЧИСТКА ТЕКСТА =================

def clean_vk_text(text: str) -> str:
    if not text: return ""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    text = text.replace('**', '').replace('__', '')
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()

# ================= ПРОМПТ =================

def build_system_prompt(user_message, settings):
    style_map = {
        "balanced": "Сбалансированный, профессиональный тон.",
        "strict": "Деловой, сухой, фактологичный. Без воды и эмоций.",
        "casual": "Легкий, дружеский, с живыми оборотами.",
        "list": "Четкая структура: тезис → пункты → вывод.",
        "story": "Повествование от первого лица или вовлекающая история."
    }
    len_map = {
        "short": "До 300 знаков. Только суть.",
        "medium": "400-600 знаков. Стандарт для ленты ВК.",
        "long": "До 1000 знаков. Детальный разбор."
    }
    emoji_map = {
        "off": "Без эмодзи.",
        "minimal": "1-2 эмодзи в заголовке.",
        "normal": "3-5 эмодзи как акценты.",
        "rich": "5-8 эмодзи, ярко, но без спама."
    }

    return f"""Ты — senior SMM-редактор для ВКонтакте.
ПОЛЬЗОВАТЕЛЬ НАПИСАЛ: "{user_message}"

 ТВОЯ ЗАДАЧА:
1. Понять суть запроса (тему, стиль, формат) из сообщения пользователя.
2. Написать готовый пост строго по настройкам ниже.

⚙️ НАСТРОЙКИ:
Стиль: {style_map[settings['style']]} | Объем: {len_map[settings['length']]} | Эмодзи: {emoji_map[settings['emoji']]}

📜 ПРАВИЛА ТЕКСТА:
• Язык: Живой современный русский. Допускаются устоявшиеся профессионализмы (дедлайн, фича, чек, трафик, кейс, лиды), если они уместны.
• Запрещено: прямые английские вставки, машинные кальки ("является", "данный текст", "стоит отметить", "в современном мире").
• Грамматика: 100% точность падежей, окончаний и согласований.
• Тон: Избегай канцеляризмов. Пиши как живой эксперт или друг.
• Структура: ЗАГОЛОВОК ЗАГЛАВНЫМИ → Вступление → Основная часть → Вывод/Вопрос.
• Оформление: Пустая строка между абзацами. Списки через • или ✓. Никакого Markdown (**, *, #, _).
• Эмодзи: СТРОГО по настройкам. Не добавляй лишние.

Генерируй сразу готовый текст для публикации."""

# ================= ФУНКЦИИ =================

def send_message(peer_id: int, text: str, keyboard=None):
    try:
        params = {"peer_id": peer_id, "message": clean_vk_text(text), "random_id": random.randint(1, 10**9)}
        if keyboard: params["keyboard"] = keyboard
        vk.method("messages.send", params)
    except Exception as e:
        logger.error(f"❌ Send error: {e}")

def generate_ai_response(prompt: str, system_role: str) -> str:
    try:
        logger.info("📡 Запрос к YandexGPT (model=yandexgpt)...")
        response = ai_client.chat.completions.create(
            model="yandexgpt",
            messages=[
                {"role": "system", "content": system_role},
                {"role": "user", "content": prompt}
            ],
            max_tokens=900,
            temperature=0.4,
            top_p=0.9
        )
        logger.info("✅ YandexGPT ответил успешно")
        return response.choices[0].message.content.strip()
    except Exception as e:
        # Принудительный сброс в stderr (гарантированно видно в Render)
        sys.stderr.write(f"🤖 YANDEX ERROR: {type(e).__name__}: {e}\n")
        sys.stderr.flush()
        return "⚠️ Ошибка генерации. Попробуйте позже."

# ================= ОБРАБОТЧИК =================

async def process_user_action(peer_id, text, payload_str):
    if peer_id not in user_context:
        user_context[peer_id] = {"state": "menu", "settings": DEFAULT_SETTINGS.copy()}

    ctx = user_context[peer_id]
    cmd = None
    if payload_str:
        try: cmd = json.loads(payload_str).get("cmd")
        except: pass

    if cmd == "generate":
        ctx["state"] = "waiting"
        s = ctx["settings"]
        send_message(peer_id, f"📝 Напишите тему или просто попросите: «сделай пост про...», «текст на тему...», «напиши историю про...».\n\n⚙️ Настройки:\n• {s['length']} | {s['emoji']} | {s['style']}", get_main_keyboard())
    elif cmd == "hashtags":
        ctx["state"] = "waiting_hash"
        send_message(peer_id, "#️⃣ Напишите тему для хэштегов:", get_main_keyboard())
    elif cmd == "premium":
        send_message(peer_id, "👑 Премиум в разработке. Скоро: аналитика, автопостинг, шаблоны.", get_main_keyboard())
    elif cmd == "settings":
        ctx["state"] = "settings"
        send_message(peer_id, "⚙️ Настройте параметры (кликните на нужное):", get_settings_keyboard(ctx["settings"]))
    elif cmd == "back":
        ctx["state"] = "menu"
        send_message(peer_id, "🔙 Главное меню:", get_main_keyboard())
    elif cmd and cmd.startswith("set_"):
        parts = cmd.split("_")
        if len(parts) == 3:
            _, param, value = parts
            if param in ["len", "emoji", "style"]:
                ctx["settings"][param] = value
                send_message(peer_id, f"✅ Применено: {param} → {value}", get_settings_keyboard(ctx["settings"]))
    elif text:
        if ctx["state"] in ["waiting", "menu"]:
            ctx["state"] = "generating"
            send_message(peer_id, " Генерирую...", None)
            prompt = build_system_prompt(text, ctx["settings"])
            ai_text = generate_ai_response(text, prompt)
            send_message(peer_id, ai_text, get_main_keyboard())
            ctx["state"] = "menu"
        elif ctx["state"] == "waiting_hash":
            sys_h = "12 релевантных хэштегов на русском. Только список через пробел. Без слов и объяснений."
            send_message(peer_id, generate_ai_response(text, sys_h), get_main_keyboard())
            ctx["state"] = "menu"
        else:
            send_message(peer_id, "Выберите действие:", get_main_keyboard())

# ================= РОУТЫ =================

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
        logger.error(f"❌ Webhook error: {e}")
    return Response(content="ok", media_type="text/plain")

@app.get("/test-logs")
async def test_logs():
    logger.info("🧪 Test log: check Render Runtime logs")
    sys.stderr.write("🔴 Test stderr flush\n")
    sys.stderr.flush()
    return {"status": "ok"}