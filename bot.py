from flask import Flask, request, jsonify
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage, BubbleContainer, CarouselContainer
from bs4 import BeautifulSoup
import requests
import json

last_keyword = ""

def scrape_books(keyword,sort_by_rate=False,sort_by_price=False):
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
        
        # พิมพ์โครงสร้างของแต่ละ book_item เพื่อดูว่ามีอะไรผิดปกติ
        print(book_item.prettify())  # พิมพ์โครงสร้าง HTML ของหนังสือแต่ละเล่ม
        
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

        # ตรวจสอบว่า img_url มีรูปแบบ http:// หรือ https:// หรือไม่
        if not (img_url.startswith('http://') or img_url.startswith('https://')):
            img_url = "https://drive.google.com/uc?export=view&id=13ihm2R69rRvt2tEHWsYbefED9CGP39vq"

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



# ฟังก์ชันสำหรับคำนวณการตอบสนอง
def compute_response(sentence):
    # เช็คว่าผู้ใช้พิมพ์ "ค้นหาหนังสือ" ไหม
    if sentence.startswith("ค้นหาหนังสือ"):
        keyword = sentence.replace("ค้นหาหนังสือ", "").strip()
        try:
            books = scrape_books(keyword)  # ดึงข้อมูลหนังสือ
            if books:
                # ถ้าพบหนังสือ สร้าง Flex Message
                flex_message = create_flex_message(books)
                # ส่ง Flex Message กลับ
                return flex_message
            else:
                return TextSendMessage(text="ไม่พบข้อมูลหนังสือที่ค้นหา")
        except Exception as e:
            print(f"Error while fetching or processing books: {e}")
            return TextSendMessage(text="เกิดข้อผิดพลาดในการดึงข้อมูล โปรดลองใหม่อีกครั้ง")
    
    # เช็คว่าผู้ใช้พิมพ์ "เรียงตามคะแนน" ไหม
    elif sentence.startswith("เรียงตามคะแนน"):
        try:
            books = scrape_books(last_keyword, sort_by_rate=True)  # ดึงข้อมูลหนังสือโดยเรียงตามคะแนน
            if books:
                # ถ้าพบหนังสือ สร้าง Flex Message
                flex_message = create_flex_message(books)
                # ส่ง Flex Message กลับ
                return flex_message
            else:
                return TextSendMessage(text="ไม่พบข้อมูลหนังสือที่ค้นหา")
        except Exception as e:
            print(f"Error while fetching or processing books: {e}")
            return TextSendMessage(text="เกิดข้อผิดพลาดในการดึงข้อมูล โปรดลองใหม่อีกครั้ง")
    elif sentence.startswith("เรียงตามราคา"):
        try:
            books = scrape_books(last_keyword, sort_by_price=True)  # ดึงข้อมูลหนังสือโดยเรียงตามราคา
            if books:
                flex_message = create_flex_message(books)
                return flex_message
            else:
                return TextSendMessage(text="ไม่พบข้อมูลหนังสือที่ค้นหา")
        except Exception as e:
            print(f"Error while fetching or processing books: {e}")
            return TextSendMessage(text="เกิดข้อผิดพลาดในการดึงข้อมูล โปรดลองใหม่อีกครั้ง")

    else:
        return TextSendMessage(text="ฟังก์ชันนี้ยังไม่รองรับการค้นหาอื่น ๆ")
    




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
