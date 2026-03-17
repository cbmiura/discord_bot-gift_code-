import requests
import re
import json
import time
import pytesseract
from PIL import Image
from io import BytesIO
import cv2
import numpy as np
from discord_webhook import DiscordWebhook
import os

# ================= CONFIG =================
URL = "https://www.youtube.com/@AFKArenaOfficial/posts"
WEBHOOK_URL = "https://discord.com/api/webhooks/1483401513505394769/NH4dR-gx1j8Z2aj9ffZWKzkwo0JdexTKrDzhKkFDDJwj7ru7Xv1uWQRarzU6I7jdiVY1"

HISTORY_FILE = "posts.json"
CHECK_INTERVAL = 600  # 10 minutos

pytesseract.pytesseract.tesseract_cmd = r"/usr/bin/tesseract"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}
# ==========================================


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r") as f:
        return json.load(f)


def save_history(data):
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f)


# ================= PEGAR POSTS =================
def get_posts():
    html = requests.get(URL, headers=HEADERS).text

    data = re.search(r"var ytInitialData = ({.*?});</script>", html)

    if not data:
        return []

    json_data = json.loads(data.group(1))

    posts = []

    def find_posts(obj):
        if isinstance(obj, dict):

            if "backstagePostRenderer" in obj:
                post = obj["backstagePostRenderer"]

                post_id = post.get("postId")

                # TEXTO
                text_runs = post.get("contentText", {}).get("runs", [])
                text = " ".join([r.get("text", "") for r in text_runs]).lower()

                # 🎯 FILTRO INTELIGENTE
                keywords = ["gift code", "new code", "redeem code", "code:"]
                if not any(k in text for k in keywords):
                    return

                # 🚫 ANTI QR/SPAM
                if "qr" in text and "gift" not in text:
                    return

                images = []
                attachment = post.get("backstageAttachment", {})

                if "postMultiImageRenderer" in attachment:
                    for img in attachment["postMultiImageRenderer"]["images"]:
                        images.append(
                            img["backstageImageRenderer"]["image"]["thumbnails"][-1]["url"]
                        )

                elif "backstageImageRenderer" in attachment:
                    images.append(
                        attachment["backstageImageRenderer"]["image"]["thumbnails"][-1]["url"]
                    )

                posts.append({
                    "id": post_id,
                    "images": images,
                    "text": text
                })

            for v in obj.values():
                find_posts(v)

        elif isinstance(obj, list):
            for item in obj:
                find_posts(item)

    find_posts(json_data)

    return posts


# ================= OCR =================
def preprocess(img):
    img = np.array(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    gray = cv2.convertScaleAbs(gray, alpha=2)
    _, thresh = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)

    return Image.fromarray(thresh)


def extract_codes(image_url):
    try:
        img = Image.open(BytesIO(requests.get(image_url).content))
        img = preprocess(img)

        text = pytesseract.image_to_string(
            img,
            config="--psm 6 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyz0123456789"
        ).lower()

        # 🎯 padrão mais preciso
        codes = re.findall(r'\b[a-z0-9]{10}\b', text)

        return list(set(codes))

    except:
        return []


# ================= DISCORD =================
def send(image_url, codes):
    content = "🍺🔥 **Taverna do GaLo encontrou um código!** 🔥🍺\n\n"

    if codes:
        content += "\n".join([f"🔑 {c}" for c in codes])

    webhook = DiscordWebhook(url=WEBHOOK_URL, content=content)

    try:
        webhook.add_file(requests.get(image_url).content, filename="gift.jpg")
    except:
        pass

    webhook.execute()


# ================= MAIN =================
def main():
    history = load_history()

    print("🔥 Monitorando POSTS do YouTube...")

    while True:
        try:
            posts = get_posts()

            if not posts:
                print("Nenhum post relevante...")

            for post in posts:
                if post["id"] in history:
                    continue

                print("🆕 Post com código detectado!")

                for img in post["images"]:
                    print("🔍 Lendo imagem...")

                    codes = extract_codes(img)

                    send(img, codes)

                history.append(post["id"])
                save_history(history)

            print("OK, esperando...")

        except Exception as e:
            print("Erro:", e)

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()