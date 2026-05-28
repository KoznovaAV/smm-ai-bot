import os
import json
import random
import re
import sys
import logging
from fastapi import FastAPI, Request, Response, BackgroundTasks
from vk_api import VkApi
from dotenv import load_dotenv
from yandex_ai_studio_sdk import AIStudio
from yandex_ai_studio_sdk.auth import APIKeyAuth

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI()
TOKEN = os.getenv("VK_TOKEN")
CONFIRMATION_CODE = os.getenv("CONFIRMATION_CODE")
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")

if not YANDEX_API_KEY:
    logger.error("❌ YANDEX_API_KEY не найден!")
if not YANDEX_FOLDER_ID:
    logger.warning("⚠️ YANDEX_FOLDER_ID не найден!")
else:
    logger.info(f"✅ Yandex настроен: folder={YANDEX_FOLDER_ID[:10]}...")

# Инициализация официального SDK
ai_sdk = None
if YANDEX_API_KEY and YANDEX_FOLDER_ID:
    try:
        ai_sdk = AIStudio(
            folder_id=YANDEX_FOLDER_ID,
            auth=APIKeyAuth(YANDEX_API_KEY)
        )
        logger.info("✅ AI Studio SDK инициализирован успешно")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации SDK: {e}")

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
    emoji_opts = [("😶 Без", "set_emoji_off"), ("✨ Мало", "set_emoji_minimal"), ("🎨 Норма", "set_emoji_normal"), ("🌈 Много", "set_emoji_rich")]
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
    # Удаляем Markdown
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    # Удаляем заголовки Markdown и цитаты
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    # Чистим остаточные символы
    text = text.replace('**', '').replace('__', '')
    # Нормализуем переносы и пробелы
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

🎯 ТВОЯ ЗАДАЧА:
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
    if not ai_sdk:
        return "⚠️ AI не настроен. Проверь ключи в Render."
    
    try:
        logger.info("📡 Запрос к YandexGPT через AI Studio SDK...")
        
        model = ai_sdk.models.completions("yandexgpt")
        model = model.configure(
            temperature=0.4,
            max_tokens=900
        )
        
        messages = [
            {"role": "system", "text": system_role},
            {"role": "user", "text": prompt}
        ]
        
        result = model.run(messages)
        
        if result and result.alternatives and len(result.alternatives) > 0:
            logger.info("✅ YandexGPT ответил успешно")
            return result.alternatives[0].text.strip()
        else:
            logger.warning("⚠️ Пустой ответ от модели")
            return "⚠️ Нейросеть вернула пустой ответ. Попробуйте другую тему."
        
    except Exception as e:
        sys.stderr.write(f"🤖 YANDEX SDK ERROR: {type(e).__name__}: {e}\n")
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

    # Кнопки главного меню
    if cmd == "generate":
        ctx["state"] = "waiting"
        s = ctx["settings"]
        send_message(peer_id, f"📝 Напишите тему или просто попросите: «сделай пост про...», «текст на тему...», «напиши историю про...».\n\n⚙️ Настройки:\n• {s['length']} | {s['emoji']} | {s['style']}", get_main_keyboard())
    
    elif cmd == "hashtags":
        ctx["state"] = "waiting_hash"
        # Исправлено: стабильный эмодзи вместо составного #️⃣
        send_message(peer_id, "🔍 Напишите тему для подбора хэштегов:", get_main_keyboard())
    
    elif cmd == "premium":
        send_message(peer_id, "👑 Премиум в разработке. Скоро: аналитика, автопостинг, шаблоны.", get_main_keyboard())
    
    elif cmd == "settings":
        ctx["state"] = "settings"
        send_message(peer_id, "⚙️ Настройте параметры (кликните на нужное):", get_settings_keyboard(ctx["settings"]))
    
    elif cmd == "back":
        ctx["state"] = "menu"
        send_message(peer_id, "🔙 Главное меню:", get_main_keyboard())
    
    # Прямое изменение настроек (фикс маппинга ключей)
    elif cmd and cmd.startswith("set_"):
        parts = cmd.split("_")
        if len(parts) == 3:
            _, param, value = parts
            key_map = {"len": "length", "emoji": "emoji", "style": "style"}
            actual_key = key_map.get(param, param)
            ctx["settings"][actual_key] = value
            send_message(peer_id, f"✅ Применено: {actual_key} → {value}", get_settings_keyboard(ctx["settings"]))
    
    # 🔧 ИСПРАВЛЕНО: Обработка текстового ввода (правильный порядок if/elif)
    elif text:
        text_clean = text.strip()
        
        # Состояние: ожидание темы для поста
        if ctx["state"] in ["waiting", "menu"]:
            ctx["state"] = "generating"
            send_message(peer_id, "⏳ Генерирую...", None)
            prompt = build_system_prompt(text_clean, ctx["settings"])
            ai_text = generate_ai_response(text_clean, prompt)
            send_message(peer_id, ai_text, get_main_keyboard())
            ctx["state"] = "menu"
        
        # Состояние: ожидание темы для хэштегов (фикс: теперь внутри elif text)
        elif ctx["state"] == "waiting_hash":
            sys_h = "Сгенерируй 15 релевантных хэштегов на русском. Формат: только хэштеги через пробел. Без текста, без приветствий, без пояснений. Строго начинай с #."
            raw_response = generate_ai_response(text_clean, sys_h)
            
            # Оставляем ТОЛЬКО слова, начинающиеся с # (фильтр мусора)
            clean_hashtags = re.findall(r'#[\wа-яА-ЯёЁ]+', raw_response)
            final_hash = " ".join(clean_hashtags) if clean_hashtags else raw_response.strip()
            
            send_message(peer_id, final_hash, get_main_keyboard())
            ctx["state"] = "menu"
        
        # Неизвестное состояние
        else:
            send_message(peer_id, "Выберите действие в меню:", get_main_keyboard())
    
    # Если нет текста и нет команды
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