from flask import Flask, request, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage, BubbleContainer, CarouselContainer, QuickReply, QuickReplyButton, MessageAction, URIAction
from bs4 import BeautifulSoup
import requests
import json
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
from neo4j import GraphDatabase
from datetime import datetime

# ตั้งค่าการเชื่อมต่อกับ Neo4j
URI = "neo4j://localhost:7687"
AUTH = ("neo4j", "ponkai517")

# ฟังก์ชันสำหรับรันคำสั่ง Neo4j
def run_query(query, parameters=None):
    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        driver.verify_connectivity()
        with driver.session() as session:
            result = session.run(query, parameters)
            return [record for record in result]
    driver.close()

# ฟังก์ชันบันทึกประวัติการสนทนาและ last_keyword ใน Neo4j พร้อมบันทึกผล scrape
def store_chat_history_and_keyword(user_id, user_message, bot_response, last_keyword, scraped_text=None):
    timestamp = datetime.now().isoformat()  # สร้าง timestamp
    query = '''
    MERGE (u:User {user_id: $user_id})
    SET u.last_keyword = $last_keyword
    CREATE (m:Chat {user_message: $user_message, timestamp: $timestamp})
    CREATE (c:bot_response {bot_response: $bot_response, scraped_text: $scraped_text, timestamp: $timestamp})
    MERGE (u)-[:question]->(m)-[:answer]->(c)
    '''
    parameters = {
        'user_id': user_id,
        'user_message': user_message,
        'bot_response': bot_response,
        'scraped_text': scraped_text,
        'last_keyword': last_keyword,
        'timestamp': timestamp
    }
    run_query(query, parameters)

# ฟังก์ชันดึงค่า last_keyword จาก Neo4j
def get_last_keyword(user_id):
    query = '''
    MATCH (u:User {user_id: $user_id})
    RETURN u.last_keyword AS last_keyword
    '''
    parameters = {'user_id': user_id}
    result = run_query(query, parameters)
    
    if result and result[0]['last_keyword']:
        return result[0]['last_keyword']
    return None

# สร้างโมเดล SentenceTransformer สำหรับค้นหาความใกล้เคียง
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
    "เรียงตามคะแนน",
    "เรียงตามราคา",
    "หนังสือมาใหม่ช่วงนี้",
    "หนังสือขายดีช่วงนี้",
    "แนะนำหนังสือหน่อยครับ"
]
index, vectors = create_faiss_index(intent_phrases)

# ฟังก์ชันสำหรับค้นหาข้อความที่ใกล้เคียงที่สุดด้วย FAISS
def faiss_search(sentence):
    search_vector = encoder.encode(sentence)
    _vector = np.array([search_vector])
    faiss.normalize_L2(_vector)
    distances, ann = index.search(_vector, k=1)

    distance_threshold = 0.5
    if distances[0][0] > distance_threshold:
        return 'unknown'
    else:
        return intent_phrases[ann[0][0]]

# สร้าง Quick Reply
def create_quick_reply():
    return QuickReply(
        items=[
            QuickReplyButton(
                action=MessageAction(label="เรียงตามราคา", text="เรียงตามราคา")
            ),
            QuickReplyButton(
                action=MessageAction(label="เรียงตามคะแนน", text="เรียงตามคะแนน")
            )
        ]
    )

# Quick Reply ของแนะนำ
def create_quick_reply_rec():
    return QuickReply(
        items=[
            QuickReplyButton(
                action=MessageAction(label="นิยาย", text="นิยาย")
            ),
            QuickReplyButton(
                action=MessageAction(label="จิตวิทยา,การพัฒนาตัวเอง", text="จิตวิทยา,การพัฒนาตัวเอง")
            ),
            QuickReplyButton(
                action=MessageAction(label="วรรณกรรม", text="วรรณกรรม")
            ),
            QuickReplyButton(
                action=MessageAction(label="คอมพิวเตอร์", text="คอมพิวเตอร์")
            ),
        ]
    )
def quick_reply_n1():
    return QuickReply(
        items=[
            QuickReplyButton(
                action=MessageAction(label="แฟนตาซี", text="แฟนตาซี")
            ),
            QuickReplyButton(
                action=MessageAction(label="สืบสวน", text="สืบสวน")
            ),
            QuickReplyButton(
                action=MessageAction(label="ไลท์โนเวล", text="ไลท์โนเวล")
            ),
        ]
    )
def quick_reply_n2():
    return QuickReply(
        items=[
            QuickReplyButton(
                action=MessageAction(label="การพัฒนาตัวเอง", text="การพัฒนาตัวเอง")
            ),
            QuickReplyButton(
                action=MessageAction(label="จิตวิทยา", text="จิตวิทยา")
            ),
        ]
    )
def quick_reply_n3():
    return QuickReply(
        items=[
            QuickReplyButton(
                action=MessageAction(label="เรื่องสั้น", text="เรื่องสั้น")
            ),
            QuickReplyButton(
                action=MessageAction(label="วรรณคดีไทย", text="วรรณคดีไทย")
            ),
        ]
    )
def quick_reply_n4():
    return QuickReply(
        items=[
            QuickReplyButton(
                action=MessageAction(label="ไม่มี", text="ไม่มี")
            ),
        ]
    )

def scrape_synopsis(book_title):
    # สมมติว่ามีฟังก์ชันหรือระบบที่ให้ URL ของหนังสือจากชื่อ
    book_url = get_book_url_by_title(book_title)  # ต้องทำให้แน่ใจว่ามีฟังก์ชันนี้ หรือสร้างฟังก์ชันนี้ขึ้นมา
    
    if not book_url:
        return "ไม่พบ URL ของหนังสือจากชื่อที่ให้มา"
    
    # ส่ง request เพื่อดึงข้อมูลจาก URL
    response = requests.get(book_url)
    
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ดึงข้อมูลเรื่องย่อจากแท็ก <p> แรกใน class "book-description"
        synopsis_tag = soup.select_one('.book-decription p')
        
        if synopsis_tag:
            return synopsis_tag.get_text(strip=True)
        else:
            return "ไม่พบเรื่องย่อ"
    else:
        return f"Error: ไม่สามารถเข้าถึง URL ได้ - รหัสสถานะ: {response.status_code}"



# ฟังก์ชันสำหรับการ scrape ข้อมูลหนังสือและสร้างข้อความ text
def scrape_books(keyword, sort_by_rate=False, sort_by_price=False):
    url = f"https://www.naiin.com/search-result?title={keyword}"
    if sort_by_rate:
        url += "&sortBy=rate"
    elif sort_by_price:
        url += "&sortBy=price"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    books = []
    scraped_text = ""
    for book_item in soup.select('.item-details')[:5]:  
        title_tag = book_item.select_one('.txt-normal a')
        title = title_tag.get_text(strip=True) if title_tag else "ไม่มีชื่อหนังสือ"
        product_url = title_tag['href'] if title_tag else "ไม่มี URL สินค้า"
        author_tag = book_item.select_one('.txt-light a')
        author = author_tag.get_text(strip=True) if author_tag else "ไม่มีผู้แต่ง"
        product_item_div = book_item.parent  
        price = product_item_div.get('data-price', 'ไม่ระบุ')
        img_tag = book_item.parent.select_one('.item-img-block img')
        img_url = img_tag.get('data-src') or img_tag.get('src') if img_tag else "https://drive.google.com/uc?export=view&id=13ihm2R69rRvt2tEHWsYbefED9CGP39vq"
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

        # เก็บข้อมูล text สำหรับบันทึกใน Neo4j
        scraped_text += f"ชื่อหนังสือ: {title}\nผู้แต่ง: {author}\nราคา: {price}\nคะแนน: {rating}\n\n"
    
    return books, scraped_text

def scrape_fantasy_books(url):
    # ส่ง request เพื่อดึงข้อมูลจาก URL
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    books = []
    
    # ดึงข้อมูลหนังสือที่ต้องการ
    for book_item in soup.select('.item-details')[:5]:  
        title_tag = book_item.select_one('.txt-normal a')
        title = title_tag.get_text(strip=True) if title_tag else "ไม่มีชื่อหนังสือ"
        product_url = title_tag['href'] if title_tag else "ไม่มี URL สินค้า"
        author_tag = book_item.select_one('.txt-light a')
        author = author_tag.get_text(strip=True) if author_tag else "ไม่มีผู้แต่ง"
        product_item_div = book_item.parent  
        price = product_item_div.get('data-price', 'ไม่ระบุ')
        
        # ดึง img_url ด้วย
        img_tag = book_item.parent.select_one('.item-img-block img')
        img_url = img_tag.get('data-src') or img_tag.get('src') if img_tag else "https://via.placeholder.com/200"

        rating_tag = book_item.find('span', class_='vote-scores')
        rating = rating_tag.text.strip() if rating_tag and rating_tag.text else 'ไม่มีคะแนน'

        # เก็บข้อมูลแต่ละหนังสือในรูปแบบ dict
        books.append({
            "title": title,
            "author": author,
            "price": price,
            "rating": rating,
            "product_url": product_url,
            "img_url": img_url  # เพิ่มการเก็บ img_url
        })
    
    # ส่งข้อมูลทั้งหมดกลับไป
    return books


from linebot.models import FlexSendMessage

def create_fantasy_flex_message(books):
    bubbles = []
    for book in books:
        bubble = {
            "type": "bubble",
            "hero": {
                "type": "image",
                "url": book['img_url'],  # ใช้ img_url ที่ดึงมาได้
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
                                "text": f"คะแนน: {book['rating']}",
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
    
    carousel = {
        "type": "carousel",
        "contents": bubbles
    }
    flex_message = FlexSendMessage(alt_text="หนังสือแฟนตาซีที่ค้นพบ", contents=carousel)
    
    return flex_message



# ฟังก์ชันดึง URL จากชื่อหนังสือ
def get_book_url_by_title(book_title):
    return book_url_map.get(book_title, None)


book_url_map = {}

# ฟังก์ชันสำหรับสร้าง Flex Message พร้อมปุ่ม "ขอเรื่องย่อ"
def create_flex_message(books):
    bubbles = []
    for book in books:
        book_url_map[book['title']] = book['product_url']
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
                    },
                    {
                        "type": "button",
                        "style": "primary",
                        "action": {
                            "type": "message",
                            "label": "ขอเรื่องย่อ",
                            "text": f"ขอเรื่องย่อ {book['title']}"
                        }
                    }
                ]
            }
        }
        bubbles.append(bubble)
    
    carousel = {
        "type": "carousel",
        "contents": bubbles
    }
    flex_message = FlexSendMessage(alt_text="หนังสือที่ค้นพบ", contents=carousel)
    
    return flex_message

# ฟังก์ชันคำนวณการตอบสนอง
def compute_response(sentence, user_id):
    intent = faiss_search(sentence)

    if sentence.startswith("ขอเรื่องย่อ"):
        # Scrape the synopsis for the given URL
        product_url = sentence.replace("ขอเรื่องย่อ", "").strip()
        synopsis = scrape_synopsis(product_url)
        return TextSendMessage(text=f"เรื่องย่อ: {synopsis}")

    if sentence.startswith("ค้นหาหนังสือ"):
        keyword = sentence.replace("ค้นหาหนังสือ", "").strip()
        books, scraped_text = scrape_books(keyword)
        if books:
            flex_message = create_flex_message(books)
            flex_message.quick_reply = create_quick_reply()
            bot_response = f"พบหนังสือที่เกี่ยวกับ {keyword} มีดังนี้ครับ"
            store_chat_history_and_keyword(user_id, sentence, bot_response, keyword, scraped_text)
            return [TextSendMessage(text=bot_response),flex_message]
        else:
            bot_response = "ไม่พบข้อมูลหนังสือที่ค้นหา"
            store_chat_history_and_keyword(user_id, sentence, bot_response, keyword, "")
            return TextSendMessage(text=bot_response)

    elif sentence.startswith("นิยาย"):
        quick_reply = quick_reply_n1()
        bot_response = "สนใจนิยายแบบไหนเป็นพิเศษครับ"
        return TextSendMessage(text=bot_response, quick_reply=quick_reply)
    elif sentence.startswith("นิยาย"):
        quick_reply = quick_reply_n2()
        bot_response = "สนใจนิยายแบบไหนเป็นพิเศษครับ"
        return TextSendMessage(text=bot_response, quick_reply=quick_reply)
    elif sentence.startswith("จิตวิทยา,การพัฒนาตัวเอง"):
        quick_reply = quick_reply_n3()
        bot_response = "สนใจนิยายแบบไหนเป็นพิเศษครับ"
        return TextSendMessage(text=bot_response, quick_reply=quick_reply)
    elif sentence.startswith("คอมพิวเตอร์"):
        quick_reply = quick_reply_n4()
        bot_response = "สนใจนิยายแบบไหนเป็นพิเศษครับ"
        return TextSendMessage(text=bot_response, quick_reply=quick_reply)
    
    elif sentence.startswith("แฟนตาซี"):
        url = "https://www.naiin.com/category?category_1_code=2&product_type_id=1&categoryLv2Code=86"
        scraped_books = scrape_fantasy_books(url)
    
        if scraped_books:
            flex_message = create_fantasy_flex_message(scraped_books)
            return flex_message
        else:
            return TextSendMessage(text="ไม่พบข้อมูลหนังสือแฟนตาซีที่ค้นหา")
        
    elif sentence.startswith("สืบสวน"):
        url = "https://www.naiin.com/category?category_1_code=2&product_type_id=1&categoryLv2Code=8"
        scraped_books = scrape_fantasy_books(url)
    
        if scraped_books:
            flex_message = create_fantasy_flex_message(scraped_books)
            return flex_message
        else:
            return TextSendMessage(text="ไม่พบข้อมูลหนังสือแฟนตาซีที่ค้นหา")
    elif sentence.startswith("ไลท์โนเวล"):
        url = "https://www.naiin.com/category?category_1_code=2&product_type_id=1&categoryLv2Code=134"
        scraped_books = scrape_fantasy_books(url)
    
        if scraped_books:
            flex_message = create_fantasy_flex_message(scraped_books)
            return flex_message
        else:
            return TextSendMessage(text="ไม่พบข้อมูลหนังสือแฟนตาซีที่ค้นหา")


    elif intent == "เรียงตามคะแนน":
        last_keyword = get_last_keyword(user_id)
        if not last_keyword:
            return TextSendMessage(text="คุณยังไม่ได้ค้นหาหนังสือก่อนหน้า")
        books, scraped_text = scrape_books(last_keyword, sort_by_rate=True)
        if books:
            flex_message = create_flex_message(books)
            flex_message.quick_reply = create_quick_reply()
            bot_response = "เรียงหนังสือตามคะแนน"
            store_chat_history_and_keyword(user_id, sentence, bot_response, last_keyword, scraped_text)
            return flex_message
        else:
            bot_response = "ไม่พบข้อมูลหนังสือที่ค้นหา"
            store_chat_history_and_keyword(user_id, sentence, bot_response, last_keyword, "")
            return TextSendMessage(text=bot_response)
        
    elif intent == "แนะนำหนังสือหน่อยครับ":
        quick_reply = create_quick_reply_rec()  # สร้าง Quick Reply
        bot_response = "เลือกหมวดหมู่ที่สนใจได้เลยครับ"
        return TextSendMessage(text=bot_response, quick_reply=quick_reply)

    
    elif intent == "หนังสือมาใหม่ช่วงนี้":
        url = "https://www.naiin.com/category?type_book=new_arrival&product_type_id=1"
        scraped_books = scrape_fantasy_books(url)
        return TextSendMessage(text=scraped_books)

    elif intent == "หนังสือขายดีช่วงนี้":
        url = "https://www.naiin.com/category?type_book=best_seller&product_type_id=1"
        scraped_books = scrape_fantasy_books(url)
        return TextSendMessage(text=scraped_books)

    elif intent == "เรียงตามราคา":
        last_keyword = get_last_keyword(user_id)
        if not last_keyword:
            return TextSendMessage(text="คุณยังไม่ได้ค้นหาหนังสือก่อนหน้า")
        books, scraped_text = scrape_books(last_keyword, sort_by_price=True)
        if books:
            flex_message = create_flex_message(books)
            flex_message.quick_reply = create_quick_reply()
            bot_response = "เรียงหนังสือตามราคา"
            store_chat_history_and_keyword(user_id, sentence, bot_response, last_keyword, scraped_text)
            return flex_message
        else:
            bot_response = "ไม่พบข้อมูลหนังสือที่ค้นหา"
            store_chat_history_and_keyword(user_id, sentence, bot_response, last_keyword, "")
            return TextSendMessage(text=bot_response)
    elif sentence.startswith("ขอเรื่องย่อ"):
        book_title = sentence.replace("ขอเรื่องย่อ", "").strip()  # ดึงชื่อหนังสือจากข้อความ
        # เรียกฟังก์ชัน scrape เรื่องย่อตามชื่อหนังสือ
        synopsis = scrape_synopsis(book_title)  
        
        if synopsis:
            return TextSendMessage(text=f"เรื่องย่อของหนังสือ '{book_title}':\n\n{synopsis}")
        else:
            return TextSendMessage(text=f"ไม่พบเรื่องย่อของหนังสือ '{book_title}'")

    
    else:
        bot_response = "ขอโทษครับ ผมไม่เข้าใจคำถามนี้"
        store_chat_history_and_keyword(user_id, sentence, bot_response, "")
        return TextSendMessage(text=bot_response)

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
        user_id = json_data['events'][0]['source']['userId']
        response_msg = compute_response(msg, user_id)
        line_bot_api.reply_message(tk, response_msg)
        print(msg, tk,book_url_map)
    except Exception as e:
        print(body)
        print(f"Error: {e}")
    return 'OK'

if __name__ == '__main__':
    app.run(port=5000)
