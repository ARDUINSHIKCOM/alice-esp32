from flask import Flask, request, jsonify
from datetime import datetime
import requests

app = Flask(__name__)

BOT_TOKEN = "8934033344:AAG1ugT8wbAHI7nawdeDgtcYuMPmcOHbxdA"
CHAT_ID = None
SERVER_URL = "https://alice-esp32.onrender.com"

# ===== ТОПЛИВО =====
fuel = {
    "100": {"name": "100-j", "price": 65, "stock": 150, "received": 0},
    "95":  {"name": "95-j",  "price": 60, "stock": 150, "received": 0},
    "92":  {"name": "92-j",  "price": 55, "stock": 150, "received": 0},
    "gas": {"name": "Gaz",   "price": 35, "stock": 150, "received": 0}
}

barcodes = {
    "8697447040151": "100",
    "4630007400679": "95",
    "4792219002130": "92",
    "4631159423264": "gas"
}

# ===== ПОЛЬЗОВАТЕЛИ =====
users = {}
current_user = None
pending_action = None
pending_fuel = None
pending_liters = 0
pending_sum = 0

# ===== ДАТЧИКИ =====
sensors = {
    "gas_a": 0, "gas_d": 0, "temp": 0, "hum": 0,
    "leak": 0, "leak_alert": False, "gas_alert": False
}

# ===== RGB =====
rgb = {"r": 0, "g": 0}

# ===== ФУНКЦИИ =====
def send_telegram(text, keyboard=None):
    global CHAT_ID
    if CHAT_ID is None:
        return
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
        if keyboard:
            data["reply_markup"] = {"keyboard": keyboard, "resize_keyboard": True}
        requests.post(url, json=data, timeout=5)
    except Exception as e:
        print("Telegram error:", e)

def send_main_menu():
    if current_user is None:
        return
    role = users.get(current_user, {}).get("role", "user")
    if role == "admin":
        kb = [
            [{"text": "Остаток"}, {"text": "Выдать бензин"}],
            [{"text": "Принять бензин"}, {"text": "Цены и RGB"}],
            [{"text": "Датчики"}, {"text": "Перезарегистрироваться"}]
        ]
    else:
        kb = [
            [{"text": "Остаток"}, {"text": "Выдать бензин"}],
            [{"text": "Принять бензин"}, {"text": "Цены и RGB"}],
            [{"text": "Датчики"}, {"text": "Перезарегистрироваться"}]
        ]
    send_telegram("Главное меню:", kb)

def send_back_menu():
    kb = [[{"text": "Назад в меню"}]]
    send_telegram("Недостаточно прав.", kb)

# ===== ESP32 =====
@app.route('/esp32/set', methods=['POST'])
def esp32_set():
    global sensors
    data = request.json
    for k in ["gas_a", "gas_d", "temp", "hum", "leak"]:
        if k in data:
            sensors[k] = data[k]

    if sensors["leak"] > 100 and not sensors["leak_alert"]:
        sensors["leak_alert"] = True
        send_telegram("⚠️ ПРОТЕЧКА БЕНЗИНА! ⚠️")
    if sensors["leak"] <= 100:
        sensors["leak_alert"] = False

    if sensors["gas_a"] > 2500 and not sensors["gas_alert"]:
        sensors["gas_alert"] = True
        send_telegram("🚨 УТЕЧКА ГАЗА! 🚨\nПокиньте территорию!\nПерекройте шланги!")
    if sensors["gas_a"] <= 2500:
        sensors["gas_alert"] = False

    return jsonify({"ok": True})

@app.route('/esp32/get', methods=['GET'])
def esp32_get():
    return jsonify({
        "rgb_r": rgb["r"],
        "rgb_g": rgb["g"],
        "fuel_100": fuel["100"]["stock"],
        "fuel_95": fuel["95"]["stock"],
        "fuel_92": fuel["92"]["stock"],
        "fuel_gas": fuel["gas"]["stock"]
    })

@app.route('/esp32/uid', methods=['POST'])
def esp32_uid():
    global current_user, pending_action
    data = request.json
    uid = data.get("uid", "").upper()

    if pending_action == "reg_mark":
        users[uid] = {"name": "Mark", "role": "admin"}
        send_telegram(f"✅ Марк зарегистрирован (UID: {uid})")
        pending_action = "reg_zhenya"
        send_telegram("Приложите ключ 2 (Женя) к NFC.")
    elif pending_action == "reg_zhenya":
        users[uid] = {"name": "Zhenya", "role": "user"}
        send_telegram(f"✅ Женя зарегистрирован (UID: {uid})")
        pending_action = None
        send_telegram("Регистрация завершена. Приложите ключ для входа.")
    elif pending_action == "login" or current_user is None:
        if uid in users:
            current_user = uid
            name = users[uid]["name"]
            role = "расширенный доступ" if users[uid]["role"] == "admin" else "малый доступ"
            send_telegram(f"Вошёл {name}, {role}.")
            send_main_menu()
        else:
            send_telegram("❌ Ключ не найден.")
    return jsonify({"ok": True})

# ===== WEBHOOK =====
@app.route('/webhook', methods=['POST'])
def webhook():
    global CHAT_ID, current_user, pending_action, pending_fuel, pending_liters, pending_sum
    update = request.get_json()
    if not update or "message" not in update:
        return "", 200

    chat_id = str(update["message"]["chat"]["id"])
    text = update["message"].get("text", "").strip()
    CHAT_ID = chat_id

    if text == "/start":
        send_telegram("Выберите режим:\nНапишите 'АЗС'.")
        return "", 200

    if text.lower() == "азс":
        send_telegram("Регистрация ключей.\nПриложите ключ 1 (Марк) к NFC.")
        pending_action = "reg_mark"
        return "", 200

    if text == "Перезарегистрироваться":
        current_user = None
        pending_action = "login"
        send_telegram("Приложите ключ для входа.")
        return "", 200

    if text == "Назад в меню" or text == "Назад" or text == "Главное меню":
        pending_action = None
        send_main_menu()
        return "", 200

    # ===== ОСТАТОК =====
    if text == "Остаток":
        msg = "⛽ Остаток топлива:\n"
        for k, v in fuel.items():
            msg += f"{v['name']}: {v['stock']} л (цена {v['price']}₽)\n"
        send_telegram(msg)
        return "", 200

    # ===== ДАТЧИКИ =====
    if text == "Датчики":
        gas_type = "Norma"
        if sensors["gas_a"] > 2500: gas_type = "CO2/Smes?"
        elif sensors["gas_a"] > 1500: gas_type = "Propan?"
        elif sensors["gas_a"] > 500: gas_type = "Metan?"
        msg = f"📊 Датчики:\n"
        msg += f"🌡️ Темп: {sensors['temp']}°C\n"
        msg += f"💧 Влаж: {sensors['hum']}%\n"
        msg += f"🔥 Газ: {sensors['gas_a']} ({gas_type})\n"
        msg += f"🚰 Протечка: {sensors['leak']}"
        send_telegram(msg)
        return "", 200

    # ===== ВЫДАТЬ БЕНЗИН =====
    if text == "Выдать бензин":
        kb = [[{"text": "100"}, {"text": "95"}], [{"text": "92"}, {"text": "Gas"}], [{"text": "Назад"}]]
        send_telegram("Выберите топливо:", kb)
        pending_action = "choose_fuel"
        return "", 200

    if pending_action == "choose_fuel" and text in ["100", "95", "92", "Gas"]:
        pending_fuel = {"100": "100", "95": "95", "92": "92", "Gas": "gas"}[text]
        pending_action = f"choose_liters_{pending_fuel}"
        kb = [[{"text": "100"}, {"text": "80"}], [{"text": "60"}, {"text": "40"}], [{"text": "20"}, {"text": "10"}], [{"text": "Назад"}]]
        send_telegram("Выберите литры:", kb)
        return "", 200

    if pending_action and pending_action.startswith("choose_liters_"):
        if text in ["100", "80", "60", "40", "20", "10"]:
            pending_liters = int(text)
            if fuel[pending_fuel]["stock"] >= pending_liters:
                pending_sum = pending_liters * fuel[pending_fuel]["price"]
                pending_action = "payment"
                send_telegram(f"Стоимость: {pending_sum}₽\nВведите сумму, которую дал клиент:")
            else:
                send_telegram("❌ Недостаточно топлива.")
                pending_action = None
                send_main_menu()
            return "", 200

    if pending_action == "payment":
        try:
            given = int(text)
            if given > pending_sum:
                change = given - pending_sum
                send_telegram(f"💰 Сдача: {change}₽")
            elif given == pending_sum:
                send_telegram("💰 Без сдачи.")
            else:
                short = pending_sum - given
                send_telegram(f"💰 Не додал: {short}₽")
            fuel[pending_fuel]["stock"] -= pending_liters
            pending_action = None
            send_main_menu()
        except:
            send_telegram("❌ Введите число.")
        return "", 200

    # ===== ПРИНЯТЬ БЕНЗИН =====
    if text == "Принять бензин":
        if current_user and users.get(current_user, {}).get("role") == "admin":
            pending_action = "scan_barcode"
            send_telegram("Введите штрих-код.")
        else:
            send_back_menu()
        return "", 200

    if pending_action == "scan_barcode":
        if text in barcodes:
            fuel_key = barcodes[text]
            fuel[fuel_key]["stock"] += 200
            fuel[fuel_key]["received"] += 200
            kb = [[{"text": "Добавить ещё"}, {"text": "Нет"}]]
            send_telegram(f"✅ Добавлен {fuel[fuel_key]['name']}, 200 л.\nОстаток: {fuel[fuel_key]['stock']} л.\n\nДобавить ещё?", kb)
            pending_action = "accept_more"
        else:
            send_telegram("❌ Штрих-код не распознан.")
        return "", 200

    if pending_action == "accept_more":
        if text == "Добавить ещё":
            pending_action = "scan_barcode"
            send_telegram("Введите штрих-код.")
        else:
            pending_action = None
            send_main_menu()
        return "", 200

    # ===== ЦЕНЫ И RGB =====
    if text == "Цены и RGB":
        if current_user and users.get(current_user, {}).get("role") == "admin":
            kb = [[{"text": "Изменить цены"}, {"text": "RGB"}], [{"text": "Назад"}]]
            send_telegram("Управление:", kb)
        else:
            send_back_menu()
        return "", 200

    if text == "Изменить цены":
        if current_user and users.get(current_user, {}).get("role") == "admin":
            kb = [[{"text": "100"}, {"text": "95"}], [{"text": "92"}, {"text": "Gas"}], [{"text": "Назад"}]]
            send_telegram("Какой бензин?", kb)
            pending_action = "change_price"
        else:
            send_back_menu()
        return "", 200

    if pending_action == "change_price" and text in ["100", "95", "92", "Gas"]:
        pending_fuel = {"100": "100", "95": "95", "92": "92", "Gas": "gas"}[text]
        pending_action = f"set_price_{pending_fuel}"
        send_telegram("Введите новую цену:")
        return "", 200

    if pending_action and pending_action.startswith("set_price_"):
        try:
            new_price = int(text)
            fuel[pending_fuel]["price"] = new_price
            send_telegram(f"✅ Цена {fuel[pending_fuel]['name']} = {new_price}₽")
            pending_action = None
            send_main_menu()
        except:
            send_telegram("❌ Введите число.")
        return "", 200

    if text == "RGB":
        if current_user and users.get(current_user, {}).get("role") == "admin":
            kb = [[{"text": "Красный"}, {"text": "Зелёный"}], [{"text": "Смешать"}, {"text": "Выключить"}], [{"text": "Назад"}]]
            send_telegram("RGB:", kb)
        else:
            send_back_menu()
        return "", 200

    if text == "Красный":
        rgb["r"] = 255; rgb["g"] = 0
        send_telegram("🔴 Красный включён")
        return "", 200

    if text == "Зелёный":
        rgb["r"] = 0; rgb["g"] = 255
        send_telegram("🟢 Зелёный включён")
        return "", 200

    if text == "Смешать":
        rgb["r"] = 255; rgb["g"] = 255
        send_telegram("🟡 Смешано (красный + зелёный)")
        return "", 200

    if text == "Выключить":
        rgb["r"] = 0; rgb["g"] = 0
        send_telegram("⚫ Выключено")
        return "", 200

    return "", 200

@app.route('/health')
def health():
    return "OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
