import os
import random
import json
from fastapi import FastAPI, Request
from vk_api import VkApi
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

TOKEN = os.getenv("VK_TOKEN")
CONFIRMATION_CODE = os.getenv("CONFIRMATION_CODE")
GROUP_ID = os.getenv("GROUP_ID")

print(f"🔍 DEBUG: CONFIRMATION_CODE = '{CONFIRMATION_CODE}'")
print(f"🔍 DEBUG: TOKEN загружен = {TOKEN is not None}")

vk = VkApi(token=TOKEN)

def send_message(peer_id: int, text: str):
    print(f"📤 ОТПРАВЛЯЮ: peer_id={peer_id}, text='{text}'")
    try:
        vk.method("messages.send", {
            "peer_id": peer_id,
            "message": text,
            "random_id": random.randint(1, 10**9)
        })
        print("✅ Сообщение отправлено успешно")
    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        event_type = data.get("type")
        
        print(f"\n{'='*50}")
        print(f"📩 ПОЛУЧЕНО СОБЫТИЕ: {event_type}")
        print(f"📦 Полные данные: {json.dumps(data, indent=2, ensure_ascii=False)}")
        print(f"{'='*50}\n")

        if event_type == "confirmation":
            print(f"✅ Отправляю подтверждение: '{CONFIRMATION_CODE}'")
            return CONFIRMATION_CODE

        if event_type == "message_new":
            print("📨 Обработка нового сообщения...")
            msg = data["object"]["message"]
            peer_id = msg["peer_id"]
            text = msg.get("text", "").strip()
            
            print(f"👤 От: peer_id={peer_id}")
            print(f"💬 Текст: '{text}'")
            
            if text:
                reply = f"🔄 Вы написали: {text}"
                send_message(peer_id, reply)
            else:
                print("⚠️ Пустое сообщение или только вложение")

    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()

    return "ok"

if __name__ == "__main__":
    import uvicorn
    print("\n🚀 ЗАПУСК СЕРВЕРА...")
    print("📡 Слушаю http://0.0.0.0:8000")
    print("⏳ Жду события от VK...\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)