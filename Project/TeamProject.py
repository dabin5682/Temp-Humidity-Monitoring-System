from flask import Flask, render_template, jsonify, request, make_response
import board
import adafruit_dht
import time
import threading
import RPi.GPIO as GPIO
import requests
import json
import os
import sys

# ----------------------------
# 사용자 설정 (카카오 REST API 키)
# ----------------------------
# 카카오 개발자 센터 > 내 애플리케이션 > 앱 키 > REST API 키 복사
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REST_API_KEY = "4e60aa05456a9b9f92c926e117f37379"

# 토큰 저장 파일 경로
TOKEN_FILE = os.path.join(BASE_DIR,"kakao_token.json")

# ----------------------------
# GPIO 및 전역 변수 설정
# ----------------------------
BUZZER_PIN = 16
LED_PIN = 20

last_sent_time = 0
ALERT_INTERVAL = 1800  # 30분

t = None
h = None
check_box = False

tem_min = 0
tem_max = 30
humi_min = 40
humi_max = 70

# GPIO 초기화
try:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUZZER_PIN, GPIO.OUT)
    GPIO.output(BUZZER_PIN, GPIO.LOW)
    GPIO.setup(LED_PIN, GPIO.OUT)
    GPIO.output(LED_PIN, GPIO.LOW)
except Exception as e:
    print(f"GPIO setup error: {e}")

def led_on():
    try: GPIO.output(LED_PIN, GPIO.HIGH)
    except: pass

def led_off():
    try: GPIO.output(LED_PIN, GPIO.LOW)
    except: pass

app = Flask(__name__)

# DHT11 초기화
try:
    dhtDevice = adafruit_dht.DHT11(board.D4, use_pulseio=False)
    time.sleep(2)
except Exception:
    dhtDevice = None

# ----------------------------
# LCD 라이브러리
# ----------------------------
sys.path.append('/usr/lib/python3/dist-packages')
sys.path.append('/home/chosun/myenv/lib64/python3.11/site-packages/cc863375a6e19dce359d')
import RPi_I2C_driver
mylcd = RPi_I2C_driver.lcd()

def lcd_display(line1, line2):
    mylcd.lcd_clear()
    mylcd.lcd_display_string(line1[:16], 1)
    mylcd.lcd_display_string(line2[:16], 2)

# ----------------------------
# 토큰 관리 함수 (JSON 파일 입출력)
# ----------------------------
def load_tokens():
    if not os.path.exists(TOKEN_FILE):
        print(f"오류: {TOKEN_FILE} 파일이 없습니다.")
        return None
    with open(TOKEN_FILE, "r") as fp:
        return json.load(fp)

def save_tokens(tokens):
    with open(TOKEN_FILE, "w") as fp:
        json.dump(tokens, fp)
    print(">> 토큰 파일 업데이트 완료")

# ----------------------------
# 토큰 갱신 함수
# ----------------------------
def refresh_kakao_token():
    tokens = load_tokens()
    if not tokens:
        return None

    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": REST_API_KEY,
        "refresh_token": tokens.get("refresh_token")
    }

    response = requests.post(url, data=data)
    
    if response.status_code == 200:
        new_tokens = response.json()
        
        # Access Token 갱신
        if "access_token" in new_tokens:
            tokens["access_token"] = new_tokens["access_token"]
            
        # Refresh Token 갱신 (만료 임박 시 새 값 반환됨, 아닐 경우 기존 유지)
        if "refresh_token" in new_tokens:
            tokens["refresh_token"] = new_tokens["refresh_token"]
            
        save_tokens(tokens)
        print(">> 카카오톡 Access Token 갱신 성공!")
        return tokens["access_token"]
    else:
        print(f">> 토큰 갱신 실패: {response.status_code}, {response.text}")
        return None

# ----------------------------
# 카카오톡 메시지 전송 (자동 갱신 포함)
# ----------------------------
def send_kakao_message(temp_status, humi_status, cur_t, cur_h, retry=True):
    global last_sent_time
    now = time.time()
    
    if now - last_sent_time < ALERT_INTERVAL:
        return # 쿨타임 중

    tokens = load_tokens()
    if not tokens:
        print(">> 토큰 정보가 없어 메시지를 보낼 수 없습니다.")
        return

    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {"Authorization": "Bearer " + tokens["access_token"]}

    # 메시지 구성
    msg_body = f"[경고] 설정값 이탈\n현재: {cur_t:.1f}°C / {cur_h:.1f}%\n"
    if temp_status: msg_body += f"온도: {temp_status}\n"
    if humi_status: msg_body += f"습도: {humi_status}"

    template = {
        "object_type": "text",
        "text": msg_body,
        "link": {
            "web_url": "http://localhost:5000",
            "mobile_web_url": "http://localhost:5000"
        }
    }

    try:
        response = requests.post(url, headers=headers, data={"template_object": json.dumps(template)})
        
        # 401 Unauthorized 에러 발생 시 (토큰 만료)
        if response.status_code == 401 and retry:
            print(">> 토큰 만료 감지. 갱신 시도 중...")
            new_access_token = refresh_kakao_token()
            if new_access_token:
                # 갱신 후 재귀 호출 (retry=False로 무한 루프 방지)
                send_kakao_message(temp_status, humi_status, cur_t, cur_h, retry=False)
            return

        if response.status_code == 200:
            last_sent_time = now
            print(">> 카카오톡 전송 성공")
        else:
            print(f">> 전송 실패 (Code {response.status_code}): {response.text}")

    except Exception as e:
        print(">> 전송 에러:", e)

# ----------------------------
# 부저 알람
# ----------------------------
def buzzer_alert():
    try:
        for _ in range(3):
            GPIO.output(BUZZER_PIN, GPIO.HIGH)
            time.sleep(0.1)
            GPIO.output(BUZZER_PIN, GPIO.LOW)
            time.sleep(0.1)
    except: pass

def buzzer_off():
    try: GPIO.output(BUZZER_PIN, GPIO.LOW)
    except: pass

# ----------------------------
# DHT11 읽기
# ----------------------------
def read_dht():
    for i in range(5):
        try:
            t = dhtDevice.temperature
            h = dhtDevice.humidity
            print("센서 측정 시도 %d 번쨰", i+1)
            if t is not None and h is not None:
                return t, h
        except:
            time.sleep(0.5)
    return None, None

# ----------------------------
# 센서 루프
# ----------------------------
def sensor_loop():
    global t, h
    while True:
        temp, humi = read_dht()
        
        if temp is None:
            led_on()
            lcd_display("Sensor Error", "Check Device")
            print("센서 오류")
        else:
            t, h = temp, humi
            led_off()
            print(f"T: {t:.1f}, H: {h:.1f}, Alarm: {check_box}")
            lcd_display(f"Temp: {t:.1f}C", f"Hum : {h:.1f}%")

            t_warn = f"{t}°C (범위:{tem_min}~{tem_max})" if not (tem_min <= t <= tem_max) else None
            h_warn = f"{h}% (범위:{humi_min}~{humi_max})" if not (humi_min <= h <= humi_max) else None

            if check_box and (t_warn or h_warn):
                print("!! 임계값 초과 !!")
                buzzer_alert()
                send_kakao_message(t_warn, h_warn, t, h)
            else:
                buzzer_off()

        time.sleep(5)

# ----------------------------
# Flask
# ----------------------------
@app.route('/')
def index():
    return render_template('index.html', temperature=t, humidity=h, tem_min=tem_min, tem_max=tem_max, humi_min=humi_min, humi_max=humi_max, check_box=check_box)

@app.route('/data')
def get_data():
    return make_response(jsonify({"temperature": t, "humidity": h}))

@app.route('/set_checkbox', methods=['POST'])
def set_checkbox():
    global check_box
    check_box = bool(request.get_json().get('check_box'))
    return jsonify(success=True)

@app.route('/set_limits', methods=['POST'])
def set_limits():
    global tem_min, tem_max, humi_min, humi_max
    d = request.get_json()
    tem_min, tem_max = int(d.get("tem_min", tem_min)), int(d.get("tem_max", tem_max))
    humi_min, humi_max = int(d.get("humi_min", humi_min)), int(d.get("humi_max", humi_max))
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    threading.Thread(target=sensor_loop, daemon=True).start()
    try:
        app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
    finally:
        GPIO.cleanup()