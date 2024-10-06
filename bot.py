from flask import Flask, request, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage, BubbleContainer, CarouselContainer, QuickReply, QuickReplyButton, MessageAction
from bs4 import BeautifulSoup
import requests
import json
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

# สร้างโมเดล SentenceTransformer
encoder = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

# การเตรียม faiss index เพื่อค้นหาความใกล้เคียง
def create_faiss_index(phrases):
    vectors = encoder.encode(phrases)
    vector_dimension = vectors.shape[1]
    index = faiss.IndexFlatL2(vector_dimension)
    faiss.normalize_L2(vectors)
    index.add(vectors)
    return index, vectors

# สร้างประโยคตัวอย่างสำหรับการค้นหา intent
intent_phrases = [
    "ค้นหาหนังสือ",
    "เรียงตามคะแนน",
    "เรียงตามราคา"
]
index, vectors = create_faiss_index(intent_phrases)

# ค้นหาข้อความที่ใกล้เคียงที่สุดด้วย FAISS
def faiss_search(sentence):
    search_vector = encoder.encode(sentence)
    _vector = np.array([search_vector])
    faiss.normalize_L2(_vector)
    distances, ann = index.search(_vector, k=1)  # k=1 เพราะต้องการแค่ข้อความที่ใกล้เคียงที่สุด

    # ตั้งค่า threshold สำหรับ distance
    distance_threshold = 0.4
    if distances[0][0] > distance_threshold:
        return 'unknown'  # ถ้าไม่มีข้อความใกล้เคียง
    else:
        return intent_phrases[ann[0][0]]  # คืนค่าประโยคที่ใกล้เคียงที่สุด

# สร้าง Quick Reply
def create_quick_reply():
    return QuickReply(
        items=[
            QuickReplyButton(
                action=MessageAction(label="เรียงตามสินค้า", text="เรียงตามราคา")
            ),
            QuickReplyButton(
                action=MessageAction(label="เรียงตามคะแนน", text="เรียงตามคะแนน")
            )
        ]
    )

# ฟังก์ชันสำหรับการ scrape ข้อมูลหนังสือ
last_keyword = ""

def scrape_books(keyword, sort_by_rate=False, sort_by_price=False):
    global last_keyword
    global url
    url = f"https://www.naiin.com/search-result?title={keyword}"
    if sort_by_rate:
        url += "&sortBy=rate"
    elif sort_by_price:
        url += "&sortBy=price"
    last_keyword = keyword
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    books = []
    for book_item in soup.select('.item-details')[:5]:  # ดึงข้อมูลหนังสือ 5 เล่มแรก
        # ดึงชื่อหนังสือ
        title_tag = book_item.select_one('.txt-normal a')
        title = title_tag.get_text(strip=True) if title_tag else "ไม่มีชื่อหนังสือ"
        product_url = title_tag['href'] if title_tag else "ไม่มี URL สินค้า"

        # ดึงชื่อผู้แต่ง
        author_tag = book_item.select_one('.txt-light a')
        author = author_tag.get_text(strip=True) if author_tag else "ไม่มีผู้แต่ง"

        # ดึงราคา
        product_item_div = book_item.parent  # ค้นหา parent ของ item-details ซึ่งมีแอตทริบิวต์ data-price
        price = product_item_div.get('data-price', 'ไม่ระบุ')  # ดึงราคาจากแอตทริบิวต์ data-price

        # ดึงลิ้งรูปภาพ
        img_tag = book_item.parent.select_one('.item-img-block img')
        img_url = img_tag.get('data-src') or img_tag.get('src') if img_tag else "https://drive.google.com/uc?export=view&id=13ihm2R69rRvt2tEHWsYbefED9CGP39vq"

        # ดึงคะแนนรีวิว (rating)
        rating_tag = book_item.find('span', class_='vote-scores')
        rating = rating_tag.text.strip() if rating_tag and rating_tag.text else 'ไม่มีคะแนน'

        books.append({
            "title": title,
            "price": price,
            "author": author,
            "rating": rating,
            "img_url": img_url,
            "product_url": product_url
        })
    
    return books

# ฟังก์ชันสำหรับสร้าง Flex Message
def create_flex_message(books):
    bubbles = []
    for book in books:
        bubble = {
            "type": "bubble",
            "hero": {
                "type": "image",
                "url": book['img_url'],
                "size": "full",
                "aspectRatio": "20:13",
                "aspectMode": "cover"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": book['title'],
                        "weight": "bold",
                        "size": "md",
                        "wrap": True
                    },
                    {
                        "type": "box",
                        "layout": "baseline",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"ผู้แต่ง: {book['author']}",
                                "size": "sm",
                                "color": "#999999",
                                "wrap": True
                            }
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "baseline",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"ราคา: {book['price']}",
                                "weight": "bold",
                                "size": "md",
                                "color": "#1DB446",
                                "wrap": True
                            }
                        ]
                    },
                    {
                        "type": "box",
                        "layout": "baseline",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"Rating: {book['rating']}",
                                "size": "sm",
                                "color": "#FFCC00",
                                "wrap": True
                            }
                        ]
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "action": {
                            "type": "uri",
                            "label": "ดูสินค้า",
                            "uri": book['product_url']
                        }
                    }
                ]
            }
        }
        bubbles.append(bubble)
    
    # สร้าง Carousel จาก Bubble ทั้งหมด
    carousel = {
        "type": "carousel",
        "contents": bubbles
    }
    flex_message = FlexSendMessage(alt_text="หนังสือที่ค้นพบ", contents=carousel)
    
    return flex_message

# ฟังก์ชันคำนวณการตอบสนอง
def compute_response(sentence):
    intent = faiss_search(sentence)

    if intent == "ค้นหาหนังสือ":
        keyword = sentence.replace("ค้นหาหนังสือ", "").strip()
        books = scrape_books(keyword)
        if books:
            flex_message = create_flex_message(books)
            flex_message.quick_reply = create_quick_reply()
            return flex_message
        else:
            return TextSendMessage(text="ไม่พบข้อมูลหนังสือที่ค้นหา")

    elif intent == "เรียงตามคะแนน":
        books = scrape_books(last_keyword, sort_by_rate=True)
        if books:
            flex_message = create_flex_message(books)
            flex_message.quick_reply = create_quick_reply()
            return flex_message
        else:
            return TextSendMessage(text="ไม่พบข้อมูลหนังสือที่ค้นหา")

    elif intent == "เรียงตามราคา":
        books = scrape_books(last_keyword, sort_by_price=True)
        if books:
            flex_message = create_flex_message(books)
            flex_message.quick_reply = create_quick_reply()
            return flex_message
        else:
            return TextSendMessage(text="ไม่พบข้อมูลหนังสือที่ค้นหา")
    
    else:
        return TextSendMessage(text="ขอโทษครับ ผมไม่เข้าใจคำถามนี้")

# เชื่อมต่อกับ Line API
app = Flask(__name__)

@app.route("/", methods=['POST'])
def linebot():
    body = request.get_data(as_text=True)
    try:
        json_data = json.loads(body)
        access_token = '2h5B+6TZellUgtBUJke0dQvrWsKiSxnwNPOCsOpjixABRzME0XhakcDdfeMwlyLxI/fIpCTOHLDduCINBUCGwzzi7fDSNg10MDWqn8twIhETIJBrdA8yAHHD4PWMeJvmAlOrVe+cKApTJga+C+OorQdB04t89/1O/w1cDnyilFU='  # ใส่ access token ของ Line Bot
        secret = 'dd1ed20330791ca4762c5910ab155d57'
        line_bot_api = LineBotApi(access_token)
        handler = WebhookHandler(secret)
        signature = request.headers['X-Line-Signature']
        handler.handle(body, signature)
        msg = json_data['events'][0]['message']['text']
        tk = json_data['events'][0]['replyToken']
        response_msg = compute_response(msg)
        line_bot_api.reply_message(tk, response_msg)
        print(msg, tk,last_keyword,url)
    except Exception as e:
        print(body)
        print(f"Error: {e}")
    return 'OK'

if __name__ == '__main__':
    app.run(port=5000)
