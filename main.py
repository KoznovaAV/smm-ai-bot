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

user_context = {}
DEFAULT_SETTINGS = {"style": "balanced", "length": "medium", "emoji": "normal"}

# ================= КЛАВИАТУРЫ =================

def get_main_keyboard():
    return json.dumps({
        "one_time": False, "inline": False,
        "buttons": [
            [{"action": {"type": "text", "label": "📝 Сгенерировать пост", "payload": json.dumps({"cmd":"generate"})}, "color": "primary"}],
            [{"action": {"type": "text", "label": "#️⃣ Хэштеги", "payload": json.dumps({"cmd":"hashtags"})}, "color": "secondary"},
             {"action": {"type": "text", "label": "️ Настройки", "payload": json.dumps({"cmd":"settings"})}, "color": "default"}],
            [{"action": {"type": "text", "label": "👑 Премиум", "payload": json.dumps({"cmd":"premium"})}, "color": "positive"}]
        ]
    })

def get_settings_keyboard(settings):
    # Вспомогательная функция для кнопок
    def btn(label, cmd, is_active=False):
        return {
            "action": {"type": "text", "label": label, "payload": json.dumps({"cmd": cmd})},
            "color": "primary" if is_active else "default"
        }

    # Прямой выбор (без циклов)
    len_opts = [("🔹 Коротко", "set_len_short"), ("🔸 Средне", "set_len_medium"), ("🔺 Длинно", "set_len_long")]
    emoji_opts = [("😶 Без", "set_emoji_off"), ("✨ Мало", "set_emoji_minimal"), ("🎨 Норма", "set_emoji_normal"), ("🌈 Много", "set_emoji_rich")]
    style_opts = [(" Строго", "set_style_strict"), ("😊 Легко", "set_style_casual"), ("📋 Список", "set_style_list"), ("📖 История", "set_style_story"), ("⚖️ Баланс", "set_style_balanced")]

    rows = []
    # Длина
    rows.append([btn(l, c, settings["length"] == c.split("_")[-1]) for l, c in len_opts])
    # Эмодзи
    rows.append([btn(e, c, settings["emoji"] == c.split("_")[-1]) for e, c in emoji_opts])
    # Стиль
    rows.append([btn(s, c, settings["style"] == c.split("_")[-1]) for s, c in style_opts])
    # Выход
    rows.append([{"action": {"type": "text", "label": "🔙 В главное меню", "payload": json.dumps({"cmd": "back"})}, "color": "negative"}])

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
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    text = text.replace('**', '').replace('__', '')
    # Нормализация
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()

# ================= ПРОМПТ =================

def build_system_prompt(topic, settings):
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

    return f"""Ты — senior SMM-копирайтер. Пишешь тексты для ВКонтакте.
ТЕМА: {topic}
НАСТРОЙКИ: Стиль: {style_map[settings['style']]} | Объем: {len_map[settings['length']]} | Эмодзи: {emoji_map[settings['emoji']]}

 ЖЕСТКИЕ ЗАПРЕТЫ (AI-КЛИШЕ):
1. НИКОГДА не используй: "В современном мире", "Стоит отметить", "Безусловно", "Является", "Данный текст", "Нельзя не упомянуть".
2. НИКОГДА не используй Markdown (**, *, #, _). ВК его не понимает.
3. Не пиши шаблонными фразами. Пиши как живой человек.

✅ ПРАВИЛА РУССКОГО КОПИРАЙТИНГА:
1. Грамматика и пунктуация: 100% проверка. Согласование падежей обязательно.
2. Активный залог вместо пассивного. ("Мы сделали" вместо "Было сделано").
3. Короткие предложения (10-15 слов). Длинное → разбей на два.
4. ЗАГОЛОВКИ заглавными буквами. Пустая строка между абзацами.
5. Списки через • или ✓.
6. В конце: вопрос или призыв к действию.

Пример структуры:
ЗАГОЛОВОК ТЕМЫ

Вводный абзац, цепляющий внимание...

• Пункт 1
• Пункт 2

Заключение и вопрос аудитории?"""

# ================= ФУНКЦИИ =================

def send_message(peer_id: int, text: str, keyboard=None):
    try:
        params = {"peer_id": peer_id, "message": clean_vk_text(text), "random_id": random.randint(1, 10**9)}
        if keyboard: params["keyboard"] = keyboard
        vk.method("messages.send", params)
    except Exception as e:
        print(f"❌ Send error: {e}")

def generate_ai_response(prompt: str, system_role: str) -> str:
    if not groq_client: return "⚠️ AI не настроен."
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": system_role}, {"role": "user", "content": prompt}],
            max_tokens=850, temperature=0.65  # Снижена для стабильности
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"❌ Groq: {e}")
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
        send_message(peer_id, f"📝 Напишите тему или запрос.\n\n⚙️ Настройки:\n• {s['length']} | {s['emoji']} | {s['style']}", get_main_keyboard())
    elif cmd == "hashtags":
        ctx["state"] = "waiting_hash"
        send_message(peer_id, "#️⃣ Тема для хэштегов:", get_main_keyboard())
    elif cmd == "premium":
        send_message(peer_id, "👑 Премиум в разработке. Скоро: аналитика, автопостинг, шаблоны.", get_main_keyboard())
    elif cmd == "settings":
        ctx["state"] = "settings"
        send_message(peer_id, "⚙️ Настройте параметры (кликните на нужное):", get_settings_keyboard(ctx["settings"]))
    elif cmd == "back":
        ctx["state"] = "menu"
        send_message(peer_id, "🔙 Главное меню:", get_main_keyboard())

    # Прямое изменение настроек (без циклов)
    elif cmd and cmd.startswith("set_"):
        parts = cmd.split("_")
        if len(parts) == 3:
            _, param, value = parts
            if param in ["len", "emoji", "style"]:
                ctx["settings"][param] = value
                send_message(peer_id, f"✅ Изменено: {param} → {value}", get_settings_keyboard(ctx["settings"]))

    # Текстовый ввод
    elif text:
        if ctx["state"] in ["waiting", "menu"]:
            ctx["state"] = "generating"
            send_message(peer_id, "⏳ Генерирую...", None)
            prompt = build_system_prompt(text, ctx["settings"])
            ai_text = generate_ai_response(text, prompt)
            send_message(peer_id, ai_text, get_main_keyboard())
            ctx["state"] = "menu"
        elif ctx["state"] == "waiting_hash":
            sys_h = "12 релевантных хэштегов на русском. Только список через пробел. Без слов."
            send_message(peer_id, generate_ai_response(text, sys_h), get_main_keyboard())
            ctx["state"] = "menu"
        else:
            send_message(peer_id, "Выберите действие:", get_main_keyboard())

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
        print(f"❌ Webhook: {e}")
    return Response(content="ok", media_type="text/plain")