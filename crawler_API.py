import asyncio
import re
import json
from datetime import datetime, timedelta
import datefinder
import pytz
import traceback
from twikit import Client

# 初始化客户端
# client = Client('zh-TW')

def parse_date_with_year(text, today=None):
    """
    嘗試從文字中解析日期，若無年份自動補今年或最近一次未來日期。
    """
    if today is None:
        today = datetime.now()
    # 支援 9/13、09/13、9-13、09-13
    m = re.search(r'(\d{1,2})[/-](\d{1,2})', text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = today.year
        try:
            try_date = datetime(year, month, day)
        except ValueError as e:
            print(f"日期解析錯誤: {e}, 原始文字: {text}")
            traceback.print_exc()
            return None
        # 若日期已過，則補下一年
        if try_date < today:
            try_date = datetime(year+1, month, day)
        return try_date
    return None

def parse_time_range(text):
    """
    支援多種時間範圍格式：19:00~22:00、19點-22點、7pm-10pm、晚上七點-十點
    """
    # 1. 19:00~22:00、19:00-22:00、19:00～22:00、19:00－22:00
    m = re.search(r'(\d{1,2}:\d{2})\s*[~\-～－]\s*(\d{1,2}:\d{2})', text)
    if m:
        return m.group(1), m.group(2)
    # 2. 19點-22點、19點～22點
    m = re.search(r'(\d{1,2})[點时時]\s*[~\-～－]\s*(\d{1,2})[點时時]', text)
    if m:
        return f"{int(m.group(1)):02d}:00", f"{int(m.group(2)):02d}:00"
    # 3. 7pm-10pm
    m = re.search(r'(\d{1,2})\s*(am|pm|AM|PM)?\s*[~\-～－]\s*(\d{1,2})\s*(am|pm|AM|PM)', text)
    if m:
        def to24h(h, ap):
            h = int(h)
            if ap.lower() == 'pm' and h != 12:
                h += 12
            if ap.lower() == 'am' and h == 12:
                h = 0
            return f"{h:02d}:00"
        return to24h(m.group(1), m.group(2)), to24h(m.group(3), m.group(4))
    # 4. 晚上七點-十點
    m = re.search(r'(早上|上午|下午|晚上)?(\d{1,2})[點时時][~\-～－](\d{1,2})[點时時]', text)
    if m:
        def zh_to24h(prefix, h):
            h = int(h)
            if prefix in ['下午', '晚上'] and h < 12:
                h += 12
            return f"{h:02d}:00"
        return zh_to24h(m.group(1), m.group(2)), zh_to24h(m.group(1), m.group(3))
    return None, None

def extract_links(text):
    """
    從文字中提取所有連結。
    """
    # 匹配 http(s):// 或 www. 開頭的連結
    urls = re.findall(r'https?://[^\s<>\"\'{}|^`]+', text)
    if not urls:
        urls = re.findall(r'www\.[^\s<>\"\'{}|^`]+', text)
    return urls

async def get_user_tweets(client, user_id, name):
    tweets = await client.get_user_tweets(
        user_id=user_id,
        tweet_type='Tweets',
        count=60,  # 多抓一點，以便處理更多歷史貼文和避免頻繁抓取限制
    )
    event_posts = []
    taipei_tz = pytz.timezone('Asia/Taipei')
    today = datetime.now(taipei_tz)

    output_path = f'./outputs/{name}_events.json'
    existing_events = []
    existing_event_texts = set()

    try:
        with open(output_path, 'r', encoding='utf-8') as f:
            existing_events = json.load(f)
            for event in existing_events:
                existing_event_texts.add(event['text'])
                if 'check' not in event: # 新增這行來檢查和添加 'check' 屬性
                    event['check'] = False
                if 'brief_description' not in event: # 新增這行來檢查和添加 'check' 屬性
                    event['brief_description'] = ""
                if 'title' not in event: # 新增這行來檢查和添加 'check' 屬性
                    event['title'] = ""
                if 'link' not in event: # 新增這行來檢查和添加 'check' 屬性
                    event['link'] = ""
        print(f"已載入 {len(existing_events)} 條現有事件從 {output_path}")
    except FileNotFoundError:
        print(f"檔案 {output_path} 不存在，將建立新檔案。")
    except json.JSONDecodeError:
        print(f"檔案 {output_path} 內容無效，將建立新檔案。")
    except Exception as e:
        print(f"載入 {output_path} 時發生錯誤: {e}")
        traceback.print_exc()

    new_event_posts = []

    for tweet in tweets:
        text = tweet.text.strip()
        
        # 如果文章內容已存在，則跳過
        if text in existing_event_texts:
            continue
        
        # 1. RT開頭直接跳過
        if text.startswith('RT'):
            continue

        # 2. 解析日期
        date_obj = None
        date_matches = list(datefinder.find_dates(text, source=True))
        if date_matches:
            date_obj, _ = date_matches[0]
            date_obj = date_obj.astimezone(taipei_tz)
        else:
            # 嘗試補年份
            date_obj = parse_date_with_year(text, today)
            if date_obj:
                date_obj = taipei_tz.localize(date_obj)
        if not date_obj:
            continue  # 沒有日期就跳過
        # 避免錯誤日期格式
        if date_obj.year < 2000 or date_obj.year > 2100:
            continue
        date_found = date_obj.strftime('%Y-%m-%d')

        # 3. 解析時間範圍
        start_time, end_time = parse_time_range(text)
        # 若沒時間範圍，嘗試用date_obj的時間（但若是00:00:00就省略）
        if not start_time and date_obj.hour != 0:
            start_time = date_obj.strftime('%H:%M:%S')

        event_data = {
            'date': date_found,
            'text': text,
            'check': False, # 新增 'check' 屬性，預設為 False
            'venue': name # 新增場地名
        }
        if start_time:
            event_data['start_time'] = start_time
        if end_time:
            event_data['end_time'] = end_time
        
        # 提取連結
        links = extract_links(text)
        if links:
            event_data['link'] = links[0] # 暫時只保存第一個連結

        event_posts.append(event_data)
        new_event_posts.append(event_data) # 將新的事件添加到 new_event_posts 列表

    # 將現有事件和新事件合併
    final_events = existing_events + new_event_posts

    # 寫入 JSON 文件
    try:
        with open(output_path, 'w', encoding='utf-8') as f: # 注意這裡改為 'w' 模式，覆寫整個檔案
            json.dump(final_events, f, ensure_ascii=False, indent=4)
        print(f"已保存 {len(final_events)} 條事件到 {output_path}")
    except Exception as e:
        print(f"保存事件到 {output_path} 時發生錯誤: {e}")
        traceback.print_exc()
    
    return 0
