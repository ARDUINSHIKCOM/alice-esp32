from flask import Flask, request, jsonify
from datetime import datetime
import requests

app = Flask(__name__)

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8934033344:AAG1ugT8wbAHI7nawdeDgtcYuMPmcOHbxdA"

# Универсальный Chat ID (обновляется автоматически)
CHAT_ID = None

# ===== ХРАНИЛИЩЕ =====
state = {
    "gas": 0, "gas_d": 0, "water": 0, "sound": 0,
    "temp": 0, "hum": 0, "distance": 0,
    "servo": 0, "buzzer": 0, "rgb": [0, 0, 0],
    "alarm": False, "guard": False
}

log = []
MAX_LOG = 50

def add_log(event_type, value):
    log.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "type": event_type,
        "value": value
    })
    if len(log) > MAX_LOG:
        log.pop(0)

def send_telegram(text):
    global CHAT_ID
    if CHAT_ID is None:
        print("Chat ID не установлен. Напиши /start боту.")
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": CHAT_ID, "text": text}, timeout=5)
    except Exception as e:
        print("Telegram error:", e)

# ===== ESP32 =====
@app.route('/esp32/set', methods=['POST'])
def esp32_set():
    data = request.json
    for k in ["gas","gas_d","water","sound","temp","hum","distance"]:
        if k in data: state[k] = data[k]
    
    if data.get("gas", 0) > 2000:
        add_log("Утечка газа", data["gas"])
        send_telegram(f"⚠️ УТЕЧКА ГАЗА! Уровень: {data['gas']}")
    if data.get("water", 0) == 1:
        add_log("Протечка воды", 100)
        send_telegram("⚠️ ПРОТЕЧКА ВОДЫ!")
    if data.get("temp", 0) > 30:
        add_log("Высокая температура", data["temp"])
        send_telegram(f"🌡️ Высокая температура: {data['temp']}°C")
    if data.get("hum", 0) > 80:
        add_log("Высокая влажность", data["hum"])
        send_telegram(f"💧 Высокая влажность: {data['hum']}%")
    if data.get("sound", 0) > 2000:
        add_log("Громкий звук", data["sound"])
        send_telegram(f"🔊 Громкий звук: {data['sound']}")
    if data.get("distance", 999) < 50 and data.get("distance", 0) > 0:
        add_log("Объект рядом", data["distance"])
        send_telegram(f"👁️ Объект рядом: {data['distance']} см")
    
    return jsonify({"ok": True})

@app.route('/esp32/get', methods=['GET'])
def esp32_get():
    return jsonify({
        "servo": state["servo"],
        "buzzer": state["buzzer"],
        "rgb": state["rgb"],
        "alarm": state["alarm"],
        "guard": state["guard"]
    })

# ===== АЛИСА =====
@app.route('/alice', methods=['POST'])
def alice():
    data = request.json
    cmd = data.get('request', {}).get('command', '').lower()
    has_data = state["temp"] != 0 or state["hum"] != 0 or state["gas"] != 0
    
    if "что произошло" in cmd or "что случилось" in cmd:
        if log:
            last = log[-1]
            text = f"{last['time']} — {last['type']}, значение {last['value']}"
        else:
            text = "Всё спокойно, событий не было."
    elif "протечка" in cmd or "вода" in cmd:
        text = "Протечка есть!" if state["water"] else "Протечки нет."
    elif "газ" in cmd:
        text = f"Уровень газа: {state['gas']}" if has_data else "Датчик газа не передаёт данные."
    elif "температура" in cmd:
        text = f"Температура {state['temp']} градусов, влажность {state['hum']} процентов." if has_data else "Датчик температуры пока не передаёт данные."
    elif "влажность" in cmd:
        text = f"Влажность {state['hum']} процентов." if has_data else "Датчик влажности пока не передаёт данные."
    elif "расстояние" in cmd:
        text = f"Расстояние {state['distance']} сантиметров." if has_data else "Датчик расстояния не передаёт данные."
    elif "включи охрану" in cmd or "включи охран" in cmd:
        state["guard"] = True
        text = "Охрана включена. Поднесите ключ."
    elif "выключи охрану" in cmd or "выключи охран" in cmd:
        state["guard"] = False
        state["alarm"] = False
        state["buzzer"] = 0
        text = "Охрана выключена."
    elif "включи тревогу" in cmd:
        state["alarm"] = True
        state["buzzer"] = 1
        text = "Тревога включена!"
    elif "выключи тревогу" in cmd:
        state["alarm"] = False
        state["buzzer"] = 0
        text = "Тревога выключена."
    elif "включи радугу" in cmd or "радуга" in cmd:
        state["rgb"] = [255, 0, 255]
        text = "Радуга включена."
    elif "красный" in cmd:
        state["rgb"] = [255, 0, 0]
        text = "Красный цвет."
    elif "зелёный" in cmd or "зеленый" in cmd:
        state["rgb"] = [0, 255, 0]
        text = "Зелёный цвет."
    elif "синий" in cmd:
        state["rgb"] = [0, 0, 255]
        text = "Синий цвет."
    elif "выключи свет" in cmd or "выключи rgb" in cmd:
        state["rgb"] = [0, 0, 0]
        text = "Свет выключен."
    elif "открой дверь" in cmd:
        state["servo"] = 90
        text = "Дверь открыта."
    elif "закрой дверь" in cmd:
        state["servo"] = 0
        text = "Дверь закрыта."
    elif "помощь" in cmd or "что ты умеешь" in cmd:
        text = "Я умею: спрашивать температуру, влажность, газ, протечку, расстояние. Включать и выключать охрану и тревогу. Управлять цветом и дверью."
    else:
        text = "Не поняла команду. Скажите: что произошло, какая температура, есть протечка."
    
    return jsonify({
        "response": {"text": text, "tts": text, "end_session": False},
        "version": "1.0"
    })

# ===== TELEGRAM WEBHOOK =====
@app.route('/webhook', methods=['POST'])
def webhook():
    global CHAT_ID
    update = request.get_json()
    if update and "message" in update:
        chat_id = str(update["message"]["chat"]["id"])
        text = update["message"].get("text", "").lower()
        
        # Универсальный Chat ID: сохраняем, кто написал
        CHAT_ID = chat_id
        print(f"Chat ID установлен: {CHAT_ID}")
        
        if text == "/start" or text == "помощь":
            send_telegram("Привет! Я бот умного дома.\n\nДоступные команды:\n/status - статус датчиков\n/guard_on - охрана ВКЛ\n/guard_off - охрана ВЫКЛ\n/alarm_on - тревога ВКЛ\n/alarm_off - тревога ВЫКЛ\n/rainbow - радуга")
        elif text == "/status":
            send_telegram(f"📊 Статус:\n🌡️ Темп: {state['temp']}°C\n💧 Влаж: {state['hum']}%\n🔥 Газ: {state['gas']}\n🚰 Вода: {'ЕСТЬ' if state['water'] else 'НЕТ'}\n📏 Расст: {state['distance']} см\n🛡️ Охрана: {'ВКЛ' if state['guard'] else 'ВЫКЛ'}")
        elif text == "/guard_on":
            state["guard"] = True
            send_telegram("🛡️ Охрана включена!")
        elif text == "/guard_off":
            state["guard"] = False
            state["alarm"] = False
            state["buzzer"] = 0
            send_telegram("🛡️ Охрана выключена!")
        elif text == "/alarm_on":
            state["alarm"] = True
            state["buzzer"] = 1
            send_telegram("🚨 Тревога включена!")
        elif text == "/alarm_off":
            state["alarm"] = False
            state["buzzer"] = 0
            send_telegram("🚨 Тревога выключена!")
        elif text == "/rainbow":
            state["rgb"] = [255, 0, 255]
            send_telegram("🌈 Радуга включена!")
        else:
            send_telegram("Не понял команду. Напиши /start для списка команд.")
    
    return "", 200

@app.route('/health')
def health():
    return "OK"

@app.route('/log')
def get_log():
    return jsonify(log)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
