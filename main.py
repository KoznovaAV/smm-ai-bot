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
    if not groq_client:
        return "⚠️ AI-ключ не настроен."
    
    try:
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_role},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=800,
            temperature=0.75
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

    # --- Кнопка "Сгенерировать пост" ---
    if cmd == "generate":
        user_states[peer_id] = {"state": "waiting_topic", "last_topic": None, "last_style": None}
        send_message(peer_id, "📝 **Напиши тему для поста**\n\n💡 *Примеры форматов:*\n• 'Кофе' — стандартный пост\n• 'Кофе, строго' — деловой стиль\n• 'Кофе, весело, с эмодзи' — яркий пост\n• 'Кофе, список' — структурированный список\n• 'Кофе, история' — повествование", get_keyboard())

    # --- Кнопка "Хэштеги" ---
    elif cmd == "hashtags":
        user_states[peer_id] = {"state": "waiting_hashtag_topic", "last_topic": None}
        send_message(peer_id, "#️⃣ Напиши тему для подбора хэштегов:", get_keyboard())

    # --- Кнопка "Премиум" ---
    elif cmd == "premium":
        send_message(peer_id, "👑 **Премиум-функции:**\n\n• Безлимитная генерация\n• Расширенная аналитика\n• Экспорт постов\n• Приоритетная поддержка\n\nСкоро подключение оплаты!", get_keyboard())

    # --- Обработка текстовых сообщений ---
    elif text:
        text_lower = text.lower().strip()
        
        if peer_id in user_states:
            state_data = user_states[peer_id]
            state = state_data.get("state")
            
            # --- Ожидание темы поста ---
            if state == "waiting_topic":
                # Расширенные ключевые слова для стилей
                style_map = {
                    "строго": {"name": "ДЕЛОВОЙ", "emoji": "💼", "format": "formal"},
                    "серьезно": {"name": "ДЕЛОВОЙ", "emoji": "💼", "format": "formal"},
                    "научно": {"name": "НАУЧНЫЙ", "emoji": "🔬", "format": "academic"},
                    "официально": {"name": "ОФИЦИАЛЬНЫЙ", "emoji": "📋", "format": "official"},
                    "весело": {"name": "ЛЕГКИЙ", "emoji": "😊", "format": "casual"},
                    "легко": {"name": "ДРУЖЕЛЮБНЫЙ", "emoji": "✨", "format": "friendly"},
                    "позитивно": {"name": "ВДОХНОВЛЯЮЩИЙ", "emoji": "🌟", "format": "inspirational"},
                    "эмоционально": {"name": "ЯРКИЙ", "emoji": "🔥", "format": "emotional"},
                    "список": {"name": "СТРУКТУРА", "emoji": "📋", "format": "list"},
                    "структура": {"name": "СТРУКТУРА", "emoji": "📊", "format": "structured"},
                    "история": {"name": "ПОВЕСТВОВАНИЕ", "emoji": "📖", "format": "narrative"},
                    "инструкция": {"name": "ИНСТРУКЦИЯ", "emoji": "📌", "format": "tutorial"},
                    "гайд": {"name": "ГАЙД", "emoji": "", "format": "guide"},
                    "советы": {"name": "СОВЕТЫ", "emoji": "💡", "format": "tips"},
                }
                
                # Определяем стиль
                detected_style = "СТАНДАРТНЫЙ"
                format_type = "balanced"
                style_emoji = "✍️"
                
                for keyword, style_info in style_map.items():
                    if keyword in text_lower:
                        detected_style = style_info["name"]
                        format_type = style_info["format"]
                        style_emoji = style_info["emoji"]
                        text = text_lower.replace(keyword, "").replace(",", "").strip()
                        break
                
                state_data["last_topic"] = text
                state_data["last_style"] = detected_style
                
                # 🔥 ПРОДВИНУТЫЙ СИСТЕМНЫЙ ПРОМПТ (как у Claude)
                system_prompt = f"""Ты — профессиональный контент-мейкер с талантом к красивому форматированию. Твой стиль похож на Claude AI: thoughtful, detailed, well-structured.

📝 **ЗАДАЧА:**
Создай качественный пост для ВКонтакте на тему: "{text}"

🎨 **СТИЛЬ:** {detected_style} {style_emoji}

🎯 **ФОРМАТИРОВАНИЕ (критически важно):**

1. **ЗАГОЛОВОК:** 
   - Используй **жирный текст** 
   - Добавь 1-2 релевантных эмодзи в начале или конце
   - Пример: "☕️ Кофе: энергия и вдохновение"

2. **АБЗАЦЫ И ОТСТУПЫ:**
   - Обязательно делай пустую строку между абзацами
   - Каждый абзац — 2-4 предложения
   - Не пиши "стеной текста"!

3. **СПИСКИ:**
   - Для маркированных списков используй: • или — или ✓
   - Для нумерованных: 1. 2. 3.
   - Добавляй эмодзи перед пунктами, если уместно
   - Пример: "☕️ Утренний кофе" или "✓ Польза для здоровья"

4. **ЭМОДЗИ (интеллектуальное использование):**
   - Используй эмодзи КОНТЕКСТНО: кофе → ☕️, здоровье → 💚, энергия → ⚡️
   - Не ставь эмодзи после каждого слова
   - 1-2 эмодзи в заголовке, 1 эмодзи на абзац — оптимально
   - Для списков: ✓ • → ➤ ✨ 

5. **ВЫДЕЛЕНИЕ:**
   - **Жирный текст** для подзаголовков и ключевых мыслей
   - *Курсив* для акцентов (редко)

6. **СТРУКТУРА ПОСТА:**
   - Заголовок с эмодзи
   - Введение (1 абзац)
   - Основная часть (2-3 абзаца или список)
   - Заключение или призыв к действию
   - 1-2 эмодзи в конце

📌 **ПРИМЕР ХОРОШЕГО ФОРМАТИРОВАНИЯ:**

**☕️ Кофе: искусство пробуждения**

Кофе — это не просто напиток, а настоящий ритуал, который помогает нам начать день с энергией и вдохновением.

**Почему мы любим кофе:**

✓ **Энергия** — кофеин дарит бодрость и концентрацию
✓ **Настроение** — аромат свежего кофе поднимает дух
✓ **Традиции** — у каждого свой любимый способ приготовления

**Совет бариста:**
Попробуйте приготовить кофе альтернативным способом — пуровер или кемекс раскроют новые грани вкуса! ☕️✨

А какой ваш любимый способ приготовления кофе? Делитесь в комментариях! 👇

 **КРИТИЧЕСКИ ВАЖНО:**
- Грамотность на 100%
- Естественное форматирование (не роботизированное)
- Эмодзи как акценты, не как спам
- Воздух между абзацами
- Читаемость и эстетика

Пиши так, чтобы пост хотелось сохранить в закладки! 💫"""

                ai_text = generate_ai_response(f"Тема: {text}", system_prompt)
                send_message(peer_id, ai_text, get_keyboard())
                state_data["state"] = "menu"

            # --- Ожидание темы для хэштегов ---
            elif state == "waiting_hashtag_topic":
                system_prompt = """Ты эксперт по SEO и хэштегам для ВКонтакте.

Подбери 10-15 релевантных хэштегов на русском языке.

Формат:
- Только хэштеги через пробел
- Без лишних слов
- Смешивай популярные (#кофе) и узкоспециализированные (#кофемания)
- Добавляй 1-2 эмодзи в начале или конце строки

Пример: #кофе #утро #энергия #кофемания #бодрость ☕️"""
                
                ai_text = generate_ai_response(f"Тема: {text}", system_prompt)
                send_message(peer_id, ai_text, get_keyboard())
                state_data["state"] = "menu"
            
            # --- Меню (перегенерация) ---
            elif state == "menu":
                last_topic = state_data.get("last_topic")
                last_style = state_data.get("last_style", "стандартный")
                
                if last_topic:
                    # Проверяем команды
                    if any(kw in text_lower for kw in ["перегенерируй", "еще раз", "заново", "другой вариант"]):
                        # Перегенерируем с тем же стилем
                        send_message(peer_id, f"🔄 Перегенерирую пост на тему \"{last_topic}\" в стиле \"{last_style}\"...", None)
                        state_data["state"] = "waiting_topic"
                        await process_user_action(peer_id, f"{last_topic}, {last_style.lower()}", "")
                    
                    elif any(kw in text_lower for kw in ["измени стиль", "другой стиль", "поменяй стиль"]):
                        send_message(peer_id, f"📌 Последняя тема: **{last_topic}**\n\nНапиши новый стиль:\n• строго / весело / научно / список / история", get_keyboard())
                        state_data["state"] = "waiting_style_change"
                    
                    elif any(kw in text_lower for kw in ["строго", "весело", "научно", "список", "история"]):
                        # Меняем стиль и перегенерируем
                        state_data["state"] = "waiting_topic"
                        await process_user_action(peer_id, f"{last_topic}, {text_lower}", "")
                    
                    else:
                        # Новая тема
                        send_message(peer_id, f"📌 Последняя тема: **{last_topic}** ({last_style})\n\nНапиши:\n• 'перегенерируй' — создать заново\n• 'весело/строго' — изменить стиль\n• новую тему для поста", get_keyboard())
                        state_data["state"] = "waiting_topic"
                else:
                    send_message(peer_id, "👋 Выбери действие в меню:", get_keyboard())
        
        else:
            # Первое сообщение от пользователя
            user_states[peer_id] = {"state": "menu", "last_topic": None, "last_style": None}
            send_message(peer_id, "👋 **Привет! Я SMM AI Assistant** ✨\n\nЯ создаю качественный контент для ВКонтакте с помощью искусственного интеллекта.\n\n**Что я умею:**\n✓ Генерировать посты в разных стилях\n✓ Подбирать хэштеги\n✓ Форматировать текст с эмодзи\n✓ Запоминать контекст\n\nВыбери действие в меню!", get_keyboard())

    else:
        if peer_id in user_states:
            send_message(peer_id, "Выбери действие в меню:", get_keyboard())
        else:
            user_states[peer_id] = {"state": "menu", "last_topic": None}
            send_message(peer_id, "👋 Привет! Я SMM AI Assistant. Выбери действие:", get_keyboard())

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