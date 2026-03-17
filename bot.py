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
import psycopg2

# ================= CONFIG =================
URL = "https://www.youtube.com/@AFKArenaOfficial/posts"
WEBHOOK_URL = os.getenv("https://discord.com/api/webhooks/1483401513505394769/NH4dR-gx1j8Z2aj9ffZWKzkwo0JdexTKrDzhKkFDDJwj7ru7Xv1uWQRarzU6I7jdiVY1")

CHECK_INTERVAL = 43200  # 12 horas

pytesseract.pytesseract.tesseract_cmd = r"/usr/bin/tesseract"

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

DATABASE_URL = os.getenv("postgresql://postgres:EMnBIzWtpgvgCqdhddBtDNLSMazcBcqb@postgres.railway.internal:5432/railway")
# ==========================================


# ================= BANCO =================
def get_connection():
    return psycopg2.connect(DATABASE_URL)


def create_table():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id TEXT PRIMARY KEY
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


def post_exists(post_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM posts WHERE id = %s", (post_id,))
    exists = cur.fetchone() is not None

    cur.close()
    conn.close()

    return exists


def save_post(post_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO posts (id) VALUES (%s) ON CONFLICT DO NOTHING",
        (post_id,)
    )

    conn.commit()
    cur.close()
    conn.close()


# ================= PEGAR POSTS =================
def get_posts():
    try:
        html = requests.get(URL, headers=HEADERS).text

        data = re.search(r"var ytInitialData = ({.*?});</script>", html)

        if not data:
            print("⚠️ ytInitialData não encontrado")
            return []

        json_data = json.loads(data.group(1))

        posts = []

        def find_posts(obj):
            if isinstance(obj, dict):

                if "backstagePostRenderer" in obj:
                    post = obj["backstagePostRenderer"]

                    post_id = post.get("postId")

                    text_runs = post.get("contentText", {}).get("runs", [])
                    text = " ".join([r.get("text", "") for r in text_runs]).lower()

                    keywords = ["gift code", "new code", "redeem code", "code:"]
                    if not any(k in text for k in keywords):
                        return

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

    except Exception as e:
        print("❌ Erro ao pegar posts:", e)
        return []


# ================= OCR =================
def preprocess(img):
    img = np.array(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    gray = cv2.convertScaleAbs(gray, alpha=2, beta=20)
    _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)

    return Image.fromarray(thresh)


def extract_codes(image_url):
    try:
        response = requests.get(image_url)
        img = Image.open(BytesIO(response.content))

        img = preprocess(img)

        text = pytesseract.image_to_string(
            img,
            config="--psm 6 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyz0123456789"
        ).lower()

        codes = re.findall(r'\b[a-z0-9]{10}\b', text)

        print("🔍 OCR TEXTO:", text)
        print("🎯 CÓDIGOS:", codes)

        return list(set(codes))

    except Exception as e:
        print("❌ Erro OCR:", e)
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
    print("\n🚀 Rodando verificação...")

    posts = get_posts()

    print(f"📊 POSTS FILTRADOS: {len(posts)}")

    for post in posts:
        if post_exists(post["id"]):
            continue

        print("\n🆕 NOVO POST DETECTADO!")
        print("Texto:", post["text"])

        for img in post["images"]:
            codes = extract_codes(img)
            send(img, codes)

        save_post(post["id"])

    print("✅ Verificação finalizada!")


# ================= LOOP =================
if __name__ == "__main__":
    print("🔥 Bot iniciado com PostgreSQL!")

    create_table()

    while True:
        try:
            main()
        except Exception as e:
            print("❌ Erro no loop:", e)

        print("⏳ Dormindo 12 horas...")
        time.sleep(CHECK_INTERVAL)