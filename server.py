from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(__name__)

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

# ===== ESP32 =====
@app.route('/esp32/set', methods=['POST'])
def esp32_set():
    data = request.json
    for k in ["gas","gas_d","water","sound","temp","hum","distance"]:
        if k in data: state[k] = data[k]
    
    if data.get("gas", 0) > 2000:
        add_log("Утечка газа", data["gas"])
    if data.get("water", 0) == 1:
        add_log("Протечка воды", 100)
    if data.get("temp", 0) > 30:
        add_log("Высокая температура", data["temp"])
    if data.get("hum", 0) > 80:
        add_log("Высокая влажность", data["hum"])
    if data.get("sound", 0) > 2000:
        add_log("Громкий звук", data["sound"])
    if data.get("distance", 999) < 50:
        add_log("Объект рядом", data["distance"])
    
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
    
    if "что произошло" in cmd or "что случилось" in cmd:
        if log:
            last = log[-1]
            text = f"{last['time']} — {last['type']}, значение {last['value']}"
        else:
            text = "Всё спокойно, событий не было."
    elif "протечка" in cmd or "вода" in cmd:
        text = "Протечка есть!" if state["water"] else "Протечки нет."
    elif "газ" in cmd:
        text = f"Уровень газа: {state['gas']}"
    elif "температура" in cmd:
        text = f"Температура {state['temp']} градусов, влажность {state['hum']} процентов."
    elif "влажность" in cmd:
        text = f"Влажность {state['hum']} процентов."
    elif "расстояние" in cmd:
        text = f"Расстояние {state['distance']} сантиметров."
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
    else:
        text = "Не поняла команду."
    
    return jsonify({
        "response": {"text": text, "tts": text, "end_session": False},
        "version": "1.0"
    })

@app.route('/health')
def health():
    return "OK"

@app.route('/log')
def get_log():
    return jsonify(log)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
