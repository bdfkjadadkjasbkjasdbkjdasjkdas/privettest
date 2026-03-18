import requests
from bs4 import BeautifulSoup
import telebot
import time
import json
import os
import hashlib
from datetime import datetime
import threading
import schedule

# --- Конфигурация ---
BOT_TOKEN = "7885455433:AAEOk7_T8jBlWhzI3nJcFmi96z1N9vsgCgE"
CHECK_INTERVAL = 5  # минут

bot = telebot.TeleBot(BOT_TOKEN)

# Файлы для хранения
SUBS_FILE = "subscriptions.json"
SENT_FILE = "sent_items.json"

def load_json(filename, default={}):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

user_subs = load_json(SUBS_FILE, {})
sent_items = load_json(SENT_FILE, {})

def generate_item_id(item):
    text = f"{item['link']}_{item['title']}_{item['price']}"
    return hashlib.md5(text.encode()).hexdigest()

# --- Функция парсинга ---
def parse_site(brand, size=None, price=None):
    """
    Парсит разные площадки
    """
    items = []
    
    # Список сайтов для парсинга
    sites = [
        {
            "name": "Goofish",
            "url": f"https://www.goofish.com/search?keyword={brand} {size if size else ''}".replace(' ', '%20'),
            "selector": "div.item-card, div.feed-card, div[class*='item']"
        },
        {
            "name": "Taobao",
            "url": f"https://s.taobao.com/search?q={brand} {size if size else ''}".replace(' ', '+'),
            "selector": "div.item, div.J_MouserOnverReq"
        },
        {
            "name": "AliExpress",
            "url": f"https://aliexpress.ru/wholesale?SearchText={brand} {size if size else ''}".replace(' ', '%20'),
            "selector": "div.product-item"
        }
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    for site in sites:
        try:
            print(f"🔍 Парсим {site['name']}: {site['url']}")
            
            response = requests.get(site['url'], headers=headers, timeout=30)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                cards = soup.select(site['selector'])
                
                print(f"✅ {site['name']}: найдено {len(cards)} карточек")
                
                for card in cards[:5]:
                    try:
                        # Парсим ссылку
                        link = ""
                        link_elem = card.select_one('a')
                        if link_elem:
                            link = link_elem.get('href', '')
                            if link and not link.startswith('http'):
                                link = 'https:' + link if link.startswith('//') else site['url'] + link
                        
                        # Парсим фото
                        img = ""
                        img_elem = card.select_one('img')
                        if img_elem:
                            img = img_elem.get('src') or img_elem.get('data-src') or ''
                            if img and img.startswith('//'):
                                img = 'https:' + img
                        
                        # Парсим цену
                        price_text = "Цена не указана"
                        price_elem = card.select_one('.price, [class*="price"], strong')
                        if price_elem:
                            price_text = price_elem.text.strip()
                        
                        # Парсим название
                        title = brand
                        title_elem = card.select_one('.title, .desc, h3, [class*="title"]')
                        if title_elem:
                            title = title_elem.text.strip()
                        
                        items.append({
                            "title": title[:100],
                            "link": link,
                            "price": price_text,
                            "photo": img,
                            "site": site['name']
                        })
                        
                    except Exception as e:
                        continue
                
                # Если нашли товары, прекращаем
                if items:
                    break
                    
        except Exception as e:
            print(f"❌ Ошибка с {site['name']}: {e}")
            continue
    
    return items

# --- Функция проверки подписок ---
def check_subscriptions():
    print(f"\n🔄 Проверка в {datetime.now()}")
    
    for chat_id, subs in user_subs.items():
        user_sent = sent_items.get(chat_id, {})
        
        for sub in subs:
            items = parse_site(sub['brand'], sub.get('size'), sub.get('price'))
            
            for item in items:
                item_id = generate_item_id(item)
                
                if item_id not in user_sent:
                    user_sent[item_id] = datetime.now().isoformat()
                    
                    # Отправляем
                    caption = (
                        f"🆕 <b>НОВОЕ НА {item['site']}!</b>\n"
                        f"📦 {item['title']}\n"
                        f"💰 {item['price']}\n"
                        f"🔗 <a href='{item['link']}'>Ссылка</a>"
                    )
                    
                    try:
                        if item['photo']:
                            bot.send_photo(chat_id, item['photo'], caption, parse_mode='HTML')
                        else:
                            bot.send_message(chat_id, caption, parse_mode='HTML')
                        time.sleep(1)
                    except:
                        pass
        
        if user_sent:
            sent_items[chat_id] = user_sent
            save_json(SENT_FILE, sent_items)
    
    save_json(SUBS_FILE, user_subs)

# --- Команды бота ---
@bot.message_handler(commands=['start'])
def start(message):
    text = (
        "👋 <b>Поисковый бот</b>\n\n"
        "Ищу товары на:\n"
        "• Goofish (闲鱼)\n"
        "• Taobao\n"
        "• AliExpress\n\n"
        "/sub бренд размер цена - подписаться\n"
        "/list - мои подписки\n"
        "/unsub ID - отписаться"
    )
    bot.reply_to(message, text, parse_mode='HTML')

@bot.message_handler(commands=['sub'])
def sub(message):
    args = message.text.split()[1:]
    if not args:
        bot.reply_to(message, "❌ Укажи бренд")
        return
    
    brand = args[0].lower()
    size = args[1] if len(args) > 1 else None
    price = args[2] if len(args) > 2 else None
    
    chat_id = str(message.chat.id)
    
    if chat_id not in user_subs:
        user_subs[chat_id] = []
    
    user_subs[chat_id].append({
        "brand": brand,
        "size": size,
        "price": price
    })
    
    save_json(SUBS_FILE, user_subs)
    bot.reply_to(message, f"✅ Подписка создана! ID: {len(user_subs[chat_id])-1}")

@bot.message_handler(commands=['list'])
def list_subs(message):
    chat_id = str(message.chat.id)
    if chat_id not in user_subs or not user_subs[chat_id]:
        bot.reply_to(message, "❌ Нет подписок")
        return
    
    text = "📋 Подписки:\n"
    for i, sub in enumerate(user_subs[chat_id]):
        text += f"{i}. {sub['brand']} {sub.get('size', '')} {sub.get('price', '')}\n"
    
    bot.reply_to(message, text)

@bot.message_handler(commands=['unsub'])
def unsub(message):
    args = message.text.split()[1:]
    if not args:
        bot.reply_to(message, "❌ Укажи ID")
        return
    
    try:
        sub_id = int(args[0])
        chat_id = str(message.chat.id)
        
        if chat_id in user_subs and sub_id < len(user_subs[chat_id]):
            user_subs[chat_id].pop(sub_id)
            save_json(SUBS_FILE, user_subs)
            bot.reply_to(message, "✅ Отписал")
        else:
            bot.reply_to(message, "❌ Не найдено")
    except:
        bot.reply_to(message, "❌ Ошибка")

# --- Запуск ---
def run_scheduler():
    schedule.every(CHECK_INTERVAL).minutes.do(check_subscriptions)
    while True:
        schedule.run_pending()
        time.sleep(30)

if __name__ == "__main__":
    print("🚀 Запуск бота...")
    threading.Thread(target=run_scheduler, daemon=True).start()
    bot.infinity_polling()
