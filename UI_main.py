import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import json
import os
from datetime import datetime
import asyncio
import traceback
import re
import datefinder
import pytz

# 從 UCanScrapeX 目錄導入爬蟲類
from UCanScrapeX import XCrawler

class AsyncioThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.loop = None
        self.running = threading.Event()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.running.set()
        self.loop.run_forever()

    def stop(self):
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.join() # 等待線程結束

    def run_coroutine(self, coro):
        if not self.loop or not self.running.is_set():
            raise RuntimeError("Asyncio thread is not running.")
        
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()


# 日期和時間解析函數（從 crawler_API.py 移植）
def parse_date_with_year(text, today=None):
    """
    嘗試從文字中解析日期，若無年份自動補今年或最近一次未來日期。
    支援多種分隔符：/、／(全形)、-、－(全形)
    """
    if today is None:
        taipei_tz = pytz.timezone('Asia/Taipei')
        today = datetime.now(taipei_tz)
    
    # 支援 9/13、09/13、9-13、09-13、9／13（全形斜線）、9－13（全形減號）
    m = re.search(r'(\d{1,2})[/／\-－](\d{1,2})', text)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = today.year
        
        # 驗證月份和日期的有效性
        if month < 1 or month > 12 or day < 1 or day > 31:
            print(f"日期解析錯誤: 月份或日期超出有效範圍 (月:{month}, 日:{day}), 原始文字: {text}")
            return None
        
        try:
            try_date = datetime(year, month, day)
        except ValueError as e:
            print(f"日期解析錯誤: {e}, 月:{month}, 日:{day}, 原始文字前50字: {text[:50]}...")
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
    支援全形和半形字符
    """
    # 1. 19:00~22:00、19:00-22:00、19:00～22:00、19:00－22:00、19：00～22：00（全形冒號）
    m = re.search(r'(\d{1,2})[:\：](\d{2})\s*[~\-～－]\s*(\d{1,2})[:\：](\d{2})', text)
    if m:
        start_time = f"{int(m.group(1)):02d}:{m.group(2)}"
        end_time = f"{int(m.group(3)):02d}:{m.group(4)}"
        return start_time, end_time
    
    # 2. 19點-22點、19點～22點
    m = re.search(r'(\d{1,2})[點点时時]\s*[~\-～－]\s*(\d{1,2})[點点时時]', text)
    if m:
        return f"{int(m.group(1)):02d}:00", f"{int(m.group(2)):02d}:00"
    
    # 3. 7pm-10pm
    m = re.search(r'(\d{1,2})\s*(am|pm|AM|PM)?\s*[~\-～－]\s*(\d{1,2})\s*(am|pm|AM|PM)', text)
    if m:
        def to24h(h, ap):
            h = int(h)
            if ap and ap.lower() == 'pm' and h != 12:
                h += 12
            if ap and ap.lower() == 'am' and h == 12:
                h = 0
            return f"{h:02d}:00"
        return to24h(m.group(1), m.group(2)), to24h(m.group(3), m.group(4))
    
    # 4. 晚上七點-十點
    m = re.search(r'(早上|上午|下午|晚上)?(\d{1,2})[點点时時][~\-～－](\d{1,2})[點点时時]', text)
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

def process_tweet_to_event(tweet_data, venue_name, today=None):
    """
    將推文資料處理成事件資料格式
    """
    if today is None:
        taipei_tz = pytz.timezone('Asia/Taipei')
        today = datetime.now(taipei_tz)
    
    text = tweet_data.get('text', '').strip()
    
    # 1. RT開頭直接跳過
    if text.startswith('RT'):
        return None

    # 2. 解析日期
    date_obj = None
    date_matches = list(datefinder.find_dates(text, source=True))
    if date_matches:
        date_obj, _ = date_matches[0]
        taipei_tz = pytz.timezone('Asia/Taipei')
        if date_obj.tzinfo is None:
            date_obj = taipei_tz.localize(date_obj)
        else:
            date_obj = date_obj.astimezone(taipei_tz)
    else:
        # 嘗試補年份
        date_obj = parse_date_with_year(text, today)
        if date_obj:
            taipei_tz = pytz.timezone('Asia/Taipei')
            date_obj = taipei_tz.localize(date_obj)
    
    if not date_obj:
        return None  # 沒有日期就跳過
    
    # 避免錯誤日期格式
    if date_obj.year < 2000 or date_obj.year > 2100:
        return None
    
    date_found = date_obj.strftime('%Y-%m-%d')

    # 3. 解析時間範圍
    start_time, end_time = parse_time_range(text)

    event_data = {
        'date': date_found,
        'text': text,
        'check': False,
        'venue': venue_name,
        'title': '',
        'brief_description': '',
    }
    
    if start_time:
        event_data['start_time'] = start_time
    if end_time:
        event_data['end_time'] = end_time
    
    # 提取連結
    links = extract_links(text)
    if links:
        event_data['link'] = links[0]
    else:
        # 如果文本中沒有連結，使用推文連結
        event_data['link'] = tweet_data.get('tweet_url', '')
    
    return event_data


class EventCrawlerUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("X 爬蟲事件管理")
        self.geometry("900x700") # 調整視窗大小以容納更多內容

        self.crawler_interval_hours = tk.DoubleVar(value=6.0) # 預設每6小時執行一次
        self.running_crawler_thread = None
        self.stop_crawler_event = threading.Event()
        # self.client = crawler_API.Client('zh-TW') # 初始化 Twikit Client
        self.is_logged_in = True # 預設為已登入
        
        self.num_tweets_to_scrape = tk.IntVar(value=10) # 預設抓取50篇

        self.venues = [] # 在 __init__ 中初始化為空列表
        self.venue_frames = {}
        self.venue_treeviews = {}
        self.venue_events_data = {}

        # 啟動 asyncio 專用線程（暫時保留但不使用）
        self.asyncio_thread = AsyncioThread()
        self.asyncio_thread.start()
        # 等待事件循環啟動
        self.asyncio_thread.running.wait()
        
        # 初始化 XCrawler 實例
        self.crawler = XCrawler(user_data_dir="profile1", locale_code='zh-TW')

        self._create_widgets()
        self._load_events_and_display()
        
        # 綁定窗口關閉事件
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _create_widgets(self):
        # 登入區塊
        login_frame = ttk.LabelFrame(self, text="登入設定", padding="10")
        login_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        self.manual_login_button = ttk.Button(login_frame, text="手動登入 X", command=self._start_manual_x_login)
        self.manual_login_button.pack(padx=5, pady=5)
        
        # 設定區塊
        self.settings_frame = ttk.LabelFrame(self, text="爬蟲設定", padding="10")
        self.settings_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        ttk.Label(self.settings_frame, text="爬蟲間隔 (小時):").pack(side=tk.LEFT, padx=5, pady=5)
        self.interval_spinbox = ttk.Spinbox(self.settings_frame, from_=1.0, to=24.0, increment=0.5, textvariable=self.crawler_interval_hours, width=5)
        self.interval_spinbox.pack(side=tk.LEFT, padx=5, pady=5)
        
        ttk.Label(self.settings_frame, text="抓取數量:").pack(side=tk.LEFT, padx=5, pady=5)
        self.num_tweets_spinbox = ttk.Spinbox(self.settings_frame, from_=10, to=500, increment=10, textvariable=self.num_tweets_to_scrape, width=5)
        self.num_tweets_spinbox.pack(side=tk.LEFT, padx=5, pady=5)

        self.start_button = ttk.Button(self.settings_frame, text="啟動爬蟲", command=self.start_crawler)
        self.start_button.pack(side=tk.LEFT, padx=10, pady=5)
        self.stop_button = ttk.Button(self.settings_frame, text="停止爬蟲", command=self.stop_crawler)
        self.stop_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.run_once_button = ttk.Button(self.settings_frame, text="手動執行一次", command=self.run_crawler_once)
        self.run_once_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.sync_website_button = ttk.Button(self.settings_frame, text="同步網站", command=self.sync_website)
        self.sync_website_button.pack(side=tk.LEFT, padx=5, pady=5)

        # 事件列表區塊 - 改為 Notebook
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 配置 Treeview 樣式，用於已校正的日期
        self.style = ttk.Style()
        self.style.configure('Treeview', rowheight=25) # 調整行高
        self.style.map('Treeview', background=[('selected', 'blue')]) # 選中項目的背景色
        self.style.configure('corrected_date.Treeview', foreground='gray') # 已校正日期的文字顏色為灰色

        # 初始啟用爬蟲和編輯功能
        self._set_crawler_and_edit_state(True)

    def _set_crawler_and_edit_state(self, enabled):
        # This function now only controls the state of the crawler settings
        for child in self.settings_frame.winfo_children():
            if child == self.sync_website_button: # 排除同步網站按鈕
                continue
            if isinstance(child, (ttk.Button, ttk.Spinbox)):
                child.state(["!disabled"] if enabled else ["disabled"])
        # The manual login button state is managed independently

    def _start_manual_x_login(self):
        # Run login in a thread to avoid blocking the UI
        threading.Thread(target=self._manual_login_worker, daemon=True).start()

    def _manual_login_worker(self):
        try:
            # Disable button while logging in
            self.after(0, lambda: self.manual_login_button.config(state=tk.DISABLED, text="登入中..."))
            
            # 使用 XCrawler 的登入方法
            if self.crawler.login_to_x():
                self.is_logged_in = True
                
                # Update UI on the main thread after login
                self.after(0, lambda: messagebox.showinfo("登入成功", "手動登入成功！現在可以開始爬蟲了。"))
                self.after(0, lambda: self._set_crawler_and_edit_state(True))
                self.after(0, lambda: self.manual_login_button.config(text="已登入"))
            else:
                raise Exception("登入失敗")

        except Exception as e:
            self.is_logged_in = False
            self.after(0, lambda: messagebox.showerror("登入失敗", f"手動登入時發生錯誤: {e}"))
            self.after(0, lambda: self.manual_login_button.config(state=tk.NORMAL, text="手動登入 X"))
            print(f"登入錯誤: {e}")
            traceback.print_exc()

    def start_crawler(self):
        if not self.is_logged_in:
            messagebox.showwarning("爬蟲", "請先登入 X！")
            return
        if self.running_crawler_thread and self.running_crawler_thread.is_alive():
            messagebox.showinfo("爬蟲", "爬蟲正在運行中。")
            return
        
        self.stop_crawler_event.clear()
        self.running_crawler_thread = threading.Thread(target=self._run_crawler_periodically, daemon=True)
        self.running_crawler_thread.start()
        messagebox.showinfo("爬蟲", f"爬蟲已啟動，每 {self.crawler_interval_hours.get()} 小時執行一次。")

    def run_crawler_once(self):
        if not self.is_logged_in:
            messagebox.showwarning("爬蟲", "請先登入 X！")
            return
        if self.running_crawler_thread and self.running_crawler_thread.is_alive():
            messagebox.showwarning("爬蟲", "爬蟲正在運行中，請先停止自動爬蟲或等待其完成。")
            return
        messagebox.showinfo("爬蟲", "手動執行請求已收到，即將在背景開始執行。")
        threading.Thread(target=self._fetch_and_process_events, daemon=True).start()

    def stop_crawler(self):
        if self.running_crawler_thread and self.running_crawler_thread.is_alive():
            self.stop_crawler_event.set()
            messagebox.showinfo("爬蟲", "爬蟲已發出停止訊號，將在當前週期結束後停止。")
        else:
            messagebox.showinfo("爬蟲", "爬蟲未運行。")

    def _run_crawler_periodically(self):
        while not self.stop_crawler_event.is_set():
            self._fetch_and_process_events()
            # 等待下一次執行
            sleep_seconds = self.crawler_interval_hours.get() * 3600
            self.stop_crawler_event.wait(sleep_seconds)

    def _fetch_and_process_events(self):
        self.after(0, lambda: messagebox.showinfo("爬蟲", "開始執行爬蟲..."))
        user_configs = [
            {'user_id': 'jukuya456', 'name': '拘久屋'},
            {'user_id': 'studiobondage', 'name': '玩具間'},
            {'user_id': 'gengyiroom', 'name': '更衣間'},
            {'user_id': 's9808191779632', 'name': '思'},
            {'user_id': '16fnzoo', 'name': '動物方程式'},
        ]
        num_tweets_to_get = self.num_tweets_to_scrape.get()
        taipei_tz = pytz.timezone('Asia/Taipei')
        today = datetime.now(taipei_tz)
        
        try:
            for config in user_configs:
                print(f"正在抓取 {config['name']} (@{config['user_id']}) 的推文...")
                
                # 1. 使用 XCrawler 抓取推文
                tweets_data = self.crawler.scrape_x_tweets(
                    username=config['user_id'],
                    num_tweets=num_tweets_to_get,
                    debug=False,
                    ignore_retweets=True,
                    ignore_pinned=True
                )
                
                if not tweets_data:
                    print(f"在 {config['name']} 的頁面沒有抓取到新的推文。")
                    continue
                
                # 2. 將推文資料轉換為事件資料
                new_events = []
                for tweet in tweets_data:
                    event = process_tweet_to_event(tweet, config['name'], today)
                    if event:
                        new_events.append(event)
                
                if not new_events:
                    print(f"在 {config['name']} 的推文中沒有找到包含日期的事件。")
                    continue
                
                print(f"從 {len(tweets_data)} 條推文中提取了 {len(new_events)} 個事件")
                
                output_dir = "outputs"
                os.makedirs(output_dir, exist_ok=True)
                json_filename = os.path.join(output_dir, f"{config['name']}_events.json")
                
                # 3. Load existing events
                existing_events = []
                existing_event_texts = set()
                try:
                    if os.path.exists(json_filename):
                        with open(json_filename, 'r', encoding='utf-8') as f:
                            existing_events = json.load(f)
                        for event in existing_events:
                            existing_event_texts.add(event['text'])
                except (FileNotFoundError, json.JSONDecodeError) as e:
                    print(f"載入現有事件時發生錯誤: {e}")
                    traceback.print_exc()
                    pass # File doesn't exist or is empty, will be created

                # 4. Merge new events, avoiding duplicates
                unique_new_events = []
                for event in new_events:
                    if event['text'] not in existing_event_texts:
                        unique_new_events.append(event)
                
                print(f"新增 {len(unique_new_events)} 個新事件到 {config['name']}")
                final_events = existing_events + unique_new_events
                
                # 5. Overwrite the file with the merged list
                with open(json_filename, 'w', encoding='utf-8') as f:
                    json.dump(final_events, f, ensure_ascii=False, indent=4)

            self.after(0, lambda: messagebox.showinfo("爬蟲", "爬蟲執行完成，更新活動列表。"))
            self.after(0, self._load_events_and_display) # Refresh UI
        except Exception as e:
            self.after(0, lambda: messagebox.showerror("爬蟲錯誤", f"執行爬蟲時發生錯誤: {e}"))
            print(f"爬蟲執行錯誤: {e}")
            traceback.print_exc()
            
    def _load_events_and_display(self):
        outputs_dir = './outputs'
        if not os.path.exists(outputs_dir):
            os.makedirs(outputs_dir)

        # Rebuild the list of venues
        new_venues = []
        for filename in os.listdir(outputs_dir):
            if filename.endswith('_events.json'):
                venue_name = filename.replace('_events.json', '')
                new_venues.append(venue_name)
        new_venues.sort()
        self.venues = new_venues

        # Handle adding/removing venue tabs
        current_tabs = self.notebook.tabs()
        current_tab_names = [self.notebook.tab(tab, "text") for tab in current_tabs]

        for tab_name in current_tab_names:
            if tab_name not in self.venues:
                tab_id = self.notebook.index(tab_name)
                self.notebook.forget(tab_id)
                del self.venue_frames[tab_name]
                del self.venue_treeviews[tab_name]
                del self.venue_events_data[tab_name]
        
        for venue_name in self.venues:
            if venue_name not in current_tab_names:
                frame = ttk.Frame(self.notebook)
                self.notebook.add(frame, text=venue_name)
                self.venue_frames[venue_name] = frame
                
                tree = ttk.Treeview(frame, columns=("日期", "標題"), show="headings")
                tree.heading("日期", text="日期")
                tree.heading("標題", text="標題")
                tree.column("日期", width=100, anchor="center")
                tree.column("標題", width=300, anchor="w")
                tree.pack(fill=tk.BOTH, expand=True)
                tree.bind("<Double-1>", lambda event, v=venue_name: self._on_venue_date_select(event, v))
                self.venue_treeviews[venue_name] = tree

        for venue_name in self.venues:
            tree = self.venue_treeviews[venue_name]
            for item in tree.get_children():
                tree.delete(item)
            self.venue_events_data[venue_name] = {}

        all_events_by_venue_and_date = {venue: {} for venue in self.venues}

        for filename in os.listdir(outputs_dir):
            if filename.endswith('_events.json'):
                filepath = os.path.join(outputs_dir, filename)
                current_file_venue_name = filename.replace('_events.json', '')

                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        events = json.load(f)
                        for event in events:
                            if event.get('delete', False):
                                continue

                            # Data is now pre-structured, so direct assignment is used
                            event['venue'] = current_file_venue_name
                            event['source_file'] = filepath

                            # Fix for TypeError: handle both missing key and "date": null from old files
                            date_str = event.get('date') or 'N/A'

                            if date_str not in all_events_by_venue_and_date[current_file_venue_name]:
                                all_events_by_venue_and_date[current_file_venue_name][date_str] = []
                            all_events_by_venue_and_date[current_file_venue_name][date_str].append(event)
                except Exception as e:
                    print(f"載入檔案 {filepath} 時發生錯誤: {e}")
                    traceback.print_exc()
        
        # Display dates for each venue
        for venue_name, dates_data in all_events_by_venue_and_date.items():
            tree = self.venue_treeviews[venue_name]
            sorted_dates = sorted(dates_data.keys())
            for date_str in sorted_dates:
                all_events_on_date = dates_data[date_str]
                unchecked_events = [e for e in all_events_on_date if not e.get('check', False)]
                num_unchecked = len(unchecked_events)

                # 獲取該日期所有活動，並嘗試找到第一個有標題的活動
                display_text = date_str
                first_event_title = ""
                if all_events_on_date:
                    for event in all_events_on_date:
                        if event.get('title') and event.get('title').strip() != '':  # 檢查title非空且不為'.'
                            first_event_title = event.get('title')
                            break # 找到第一個有標題的活動就停止

                    if first_event_title:
                        display_text += f" - {first_event_title}"

                # 判斷是否所有事件都已校正
                all_checked = all(event.get('check', False) for event in all_events_on_date)
                tags = ('corrected_date',) if all_checked and all_events_on_date else ()

                tree.insert("", "end", values=(date_str, first_event_title if first_event_title else ""), iid=date_str, tags=tags)
                self.venue_events_data[venue_name][date_str] = dates_data[date_str]

    def _on_venue_date_select(self, event, venue_name):
        print(f"觸發 _on_venue_date_select 函數, 場地: {venue_name}") # 加入print
        selected_items = self.venue_treeviews[venue_name].selection()
        if not selected_items:
            return
        
        selected_date_str = selected_items[0] # item ID 就是日期字串
        events_on_selected_date = self.venue_events_data[venue_name].get(selected_date_str)

        if events_on_selected_date:
            self._show_event_details_popup(venue_name, selected_date_str, events_on_selected_date)

    def _show_event_details_popup(self, venue_name, date_str, events):
        popup = tk.Toplevel(self)
        popup.title(f"{venue_name} - {date_str} 活動詳情")
        popup.geometry("850x600") # 彈出視窗大小

        main_frame = ttk.Frame(popup, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(main_frame)
        v_scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        h_scrollbar = ttk.Scrollbar(main_frame, orient="horizontal", command=canvas.xview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(
                scrollregion=canvas.bbox("all")
            )
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        v_scrollbar.pack(side="right", fill="y")
        h_scrollbar.pack(side="bottom", fill="x")

        for i, event_data in enumerate(events):
            event_frame = ttk.LabelFrame(scrollable_frame, text=f"活動 {i+1}", padding="10")
            event_frame.pack(fill=tk.X, padx=5, pady=5)

            is_deleted = event_data.get('delete', False)

            if is_deleted:
                ttk.Label(event_frame, text="此活動已標記為刪除，將不會顯示在主頁面。", foreground="red").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)

            ttk.Label(event_frame, text="活動日期:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
            date_entry = ttk.Entry(event_frame, width=50, state=tk.NORMAL)
            date_entry.insert(0, event_data.get('date', ''))
            if is_deleted:
                date_entry.config(foreground="gray")
                date_entry.bind("<Key>", lambda e: "break")
            date_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=2)

            ttk.Label(event_frame, text="原始推文:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
            original_text = tk.Text(event_frame, height=10, wrap=tk.WORD)
            original_text.insert(tk.END, event_data.get('text', ''))
            original_text.config(state=tk.NORMAL) # 將狀態改為 NORMAL 以允許選取和複製
            original_text.tag_configure("readonly", foreground="gray") # 新增一個 readonly tag
            original_text.tag_add("readonly", "1.0", tk.END) # 將整個文字區域應用 readonly tag
            original_text.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=2)

            ttk.Label(event_frame, text="活動名稱:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
            title_entry = ttk.Entry(event_frame, width=50, state=tk.NORMAL) # 始終保持 NORMAL 狀態
            title_entry.insert(0, event_data.get('title', ''))
            if is_deleted: # 如果是刪除狀態，則設置為只讀模式
                title_entry.config(foreground="gray")
                title_entry.bind("<Key>", lambda e: "break") # 阻止鍵盤輸入
            title_entry.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=2)

            ttk.Label(event_frame, text="簡短描述:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
            brief_description_entry = ttk.Entry(event_frame, width=50, state=tk.NORMAL) # 始終保持 NORMAL 狀態
            brief_description_entry.insert(0, event_data.get('brief_description', ''))
            if is_deleted: # 如果是刪除狀態，則設置為只讀模式
                brief_description_entry.config(foreground="gray")
                brief_description_entry.bind("<Key>", lambda e: "break")
            brief_description_entry.grid(row=3, column=1, sticky=tk.EW, padx=5, pady=2)

            ttk.Label(event_frame, text="開始時間:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)
            start_time_entry = ttk.Entry(event_frame, width=50, state=tk.NORMAL) # 始終保持 NORMAL 狀態
            start_time_entry.insert(0, event_data.get('start_time', ''))
            if is_deleted: # 如果是刪除狀態，則設置為只讀模式
                start_time_entry.config(foreground="gray")
                start_time_entry.bind("<Key>", lambda e: "break")
            start_time_entry.grid(row=4, column=1, sticky=tk.EW, padx=5, pady=2)

            ttk.Label(event_frame, text="結束時間:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=2)
            end_time_entry = ttk.Entry(event_frame, width=50, state=tk.NORMAL) # 始終保持 NORMAL 狀態
            end_time_entry.insert(0, event_data.get('end_time', ''))
            if is_deleted: # 如果是刪除狀態，則設置為只讀模式
                end_time_entry.config(foreground="gray")
                end_time_entry.bind("<Key>", lambda e: "break")
            end_time_entry.grid(row=5, column=1, sticky=tk.EW, padx=5, pady=2)

            ttk.Label(event_frame, text="連結:").grid(row=6, column=0, sticky=tk.W, padx=5, pady=2)
            link_entry = ttk.Entry(event_frame, width=50, state=tk.NORMAL) # 始終保持 NORMAL 狀態
            link_entry.insert(0, event_data.get('link', ''))
            if is_deleted: # 如果是刪除狀態，則設置為只讀模式
                link_entry.config(foreground="gray")
                link_entry.bind("<Key>", lambda e: "break")
            link_entry.grid(row=6, column=1, sticky=tk.EW, padx=5, pady=2)

            # 新增直接貼上功能
            def _paste_from_clipboard(event, target_entry):
                if target_entry.cget('foreground') == "gray": # 如果是只讀模式，則不貼上
                    return "break" # 阻止默認貼上行為
                try:
                    clipboard_content = self.clipboard_get()
                    if not clipboard_content:  # 如果剪貼簿是空的，就不執行貼上
                        return "break"
                    
                    # 如果有選取內容，先刪除它
                    try:
                        if target_entry.selection_present():
                            target_entry.delete(tk.SEL_FIRST, tk.SEL_LAST)
                    except tk.TclError:
                        # 沒有選取內容，不需要刪除
                        pass
                    
                    # 獲取當前游標位置並插入文字
                    current_pos = target_entry.index(tk.INSERT)
                    target_entry.insert(current_pos, clipboard_content)
                except tk.TclError as e:
                    # 剪貼簿可能為空或無法存取
                    print(f"貼上時發生錯誤: {e}")
                    traceback.print_exc()
                except Exception as e:
                    print(f"貼上時發生未預期錯誤: {e}")
                    traceback.print_exc()
                return "break" # 阻止默認貼上行為

            def _copy_to_clipboard(event, target_widget):
                try:
                    selected_text = ""
                    if isinstance(target_widget, tk.Entry):
                        selected_text = target_widget.selection_get()
                    elif isinstance(target_widget, tk.Text):
                        selected_text = target_widget.selection_get()
                    
                    if selected_text:
                        self.clipboard_clear()
                        self.clipboard_append(selected_text)
                except tk.TclError:
                    pass
                return "break" # 阻止默認複製行為

            # 綁定複製和貼上事件到右鍵選單
            def _show_context_menu(event, widget, is_editable):
                context_menu = tk.Menu(widget, tearoff=0)
                if is_editable:
                    context_menu.add_command(label="剪下", command=lambda: widget.event_generate("<<Cut>>"))
                    context_menu.add_command(label="複製", command=lambda: widget.event_generate("<<Copy>>"))
                    context_menu.add_command(label="貼上", command=lambda: widget.event_generate("<<Paste>>"))
                else:
                    context_menu.add_command(label="複製", command=lambda: widget.event_generate("<<Copy>>"))
                context_menu.post(event.x_root, event.y_root)

            # 綁定右鍵選單
            original_text.bind("<Button-3>", lambda e: _show_context_menu(e, original_text, False)) # 右鍵 (macOS/Windows/Linux)
            
            for entry_widget in [title_entry, brief_description_entry, start_time_entry, end_time_entry, link_entry]:
                entry_widget.bind("<Control-v>", lambda e, entry=entry_widget: _paste_from_clipboard(e, entry))
                entry_widget.bind("<Command-v>", lambda e, entry=entry_widget: _paste_from_clipboard(e, entry))
                entry_widget.bind("<Button-3>", lambda e, entry=entry_widget: _show_context_menu(e, entry, entry.cget('foreground') != "gray")) # 右鍵 (macOS/Windows/Linux)
                entry_widget.bind("<<Copy>>", lambda e, entry=entry_widget: _copy_to_clipboard(e, entry)) # 綁定 <<Copy>> 事件
                entry_widget.bind("<<Paste>>", lambda e, entry=entry_widget: _paste_from_clipboard(e, entry)) # 綁定 <<Paste>> 事件

            # 刪除/取消刪除按鈕
            delete_button_text = "取消刪除" if is_deleted else "刪除活動"
            delete_button_command = lambda ed=event_data, current_is_deleted=is_deleted: self._toggle_delete_event(popup, venue_name, date_str, ed, current_is_deleted)
            delete_button = ttk.Button(event_frame, text=delete_button_text, command=delete_button_command)
            delete_button.grid(row=7, column=0, sticky=tk.W, padx=5, pady=5) # 放在左側

            save_button = ttk.Button(event_frame, text="保存校正", 
                                     command=lambda ed=event_data, de=date_entry, te=title_entry, bde=brief_description_entry, ste=start_time_entry, ete=end_time_entry, le=link_entry: self._save_correction_from_popup(popup, ed, de, te, bde, ste, ete, le),
                                     state=tk.DISABLED if is_deleted else tk.NORMAL) # 禁用保存按鈕
            save_button.grid(row=7, column=1, sticky=tk.E, padx=5, pady=5)

            event_frame.grid_columnconfigure(1, weight=1)

        # 綁定滾輪事件
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind("<MouseWheel>", _on_mousewheel)
        scrollable_frame.bind("<MouseWheel>", _on_mousewheel) # 確保在 frame 上滾動也有效

    def _save_correction_from_popup(self, popup, event_data, date_entry, title_entry, brief_description_entry, start_time_entry, end_time_entry, link_entry):
        # Validate date format before saving
        new_date = date_entry.get().strip()
        try:
            # Allow 'N/A' as a valid value
            if new_date.upper() != 'N/A':
                datetime.strptime(new_date, '%Y-%m-%d')
        except ValueError:
            messagebox.showerror("格式錯誤", "日期格式不正確。請使用 YYYY-MM-DD 格式，或填寫 'N/A'。")
            return

        # 更新活動資料
        event_data['date'] = new_date
        event_data['title'] = title_entry.get()
        event_data['brief_description'] = brief_description_entry.get()
        event_data['start_time'] = start_time_entry.get()
        event_data['end_time'] = end_time_entry.get()
        event_data['link'] = link_entry.get()
        event_data['check'] = True # 標記為已校正

        # 寫回 JSON 檔案
        filepath = event_data['source_file']
        try:
            with open(filepath, 'r+', encoding='utf-8') as f:
                all_events_in_file = json.load(f)
                # 找到並更新對應的事件
                for i, event in enumerate(all_events_in_file):
                    # 使用 text 作為唯一識別，確保找到正確的事件
                    if event.get('text') == event_data.get('text'): 
                        all_events_in_file[i] = event_data
                        break
                
                f.seek(0)
                json.dump(all_events_in_file, f, ensure_ascii=False, indent=4)
                f.truncate()
            messagebox.showinfo("保存成功", "活動校正已保存。")
            popup.destroy() # 關閉彈出視窗
            self.after(0, self._load_events_and_display) # 重新載入並顯示列表
        except Exception as e:
            messagebox.showerror("保存錯誤", f"保存活動時發生錯誤: {e}")
            traceback.print_exc()

    def _delete_event(self, popup, venue_name, date_str, event_data):
        if messagebox.askyesno("確認標記為刪除", f"您確定要將 {event_data.get('title', 'N/A')} 的活動標記為刪除嗎？這將不會從檔案中永久移除。"):
            # 在 event_data 中新增或更新 'delete' 標記為 True
            event_data['delete'] = True

            # 從 JSON 檔案中更新
            filepath = event_data['source_file']
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    all_events_in_file = json.load(f)

                # 找到要更新的活動並更新其 'delete' 狀態
                found = False
                for i, existing_event in enumerate(all_events_in_file):
                    # 假設 'text' 屬性可以唯一識別一個活動
                    if existing_event.get('text') == event_data.get('text'):
                        all_events_in_file[i]['delete'] = True
                        found = True
                        break

                if not found:
                    messagebox.showwarning("警告", "未能在檔案中找到要標記為刪除的活動。")
                    return
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(all_events_in_file, f, ensure_ascii=False, indent=4)
                messagebox.showinfo("標記成功", "活動已標記為刪除。")
                popup.destroy()
                self.after(0, self._load_events_and_display)
            except Exception as e:
                messagebox.showerror("標記錯誤", f"標記活動為刪除時發生錯誤: {e}")
                traceback.print_exc()

    def _toggle_delete_event(self, popup, venue_name, date_str, event_data, current_is_deleted):
        new_delete_status = not current_is_deleted
        action_text = "取消刪除" if new_delete_status else "刪除"
        confirm_message = f"您確定要將 {event_data.get('title', 'N/A')} 的活動{action_text}嗎？"
        success_message = f"活動已成功{action_text}。"
        error_message = f"在{action_text}活動時發生錯誤: "

        if messagebox.askyesno(f"確認{action_text}", confirm_message):
            event_data['delete'] = new_delete_status

            filepath = event_data['source_file']
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    all_events_in_file = json.load(f)

                found = False
                for i, existing_event in enumerate(all_events_in_file):
                    if existing_event.get('text') == event_data.get('text'):
                        all_events_in_file[i]['delete'] = new_delete_status
                        found = True
                        break

                if not found:
                    messagebox.showwarning("警告", "未能在檔案中找到要更新的活動。")
                    return
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(all_events_in_file, f, ensure_ascii=False, indent=4)
                messagebox.showinfo("操作成功", success_message)
                popup.destroy()
                self.after(0, self._load_events_and_display)
            except Exception as e:
                messagebox.showerror(f"{action_text}錯誤", f"{error_message}{e}")
                traceback.print_exc()

    def sync_website(self):       
        # 1. 讀取所有 JSON 檔案
        outputs_dir = './outputs'
        all_checked_events = []

        for filename in os.listdir(outputs_dir):
            if filename.endswith('_events.json'):
                filepath = os.path.join(outputs_dir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        events = json.load(f)
                        for event in events:
                            # 2. 篩選活動：check=True 且 title 非空
                            if event.get('check', False) and event.get('title') and event.get('title').strip() != '.':
                                all_checked_events.append(event)
                except Exception as e:
                    print(f"讀取檔案 {filepath} 時發生錯誤: {e}")
                    traceback.print_exc()

        if not all_checked_events:
            messagebox.showinfo("同步網站", "沒有找到已校正且有標題的活動。")
            return

        # 3. 按年份和月份分組
        events_by_month = {}
        for event in all_checked_events:
            try:
                date_obj = datetime.strptime(event['date'], '%Y-%m-%d')
                year_month = date_obj.strftime('%Y-%m') # 例如: '2025-08'
                if year_month not in events_by_month:
                    events_by_month[year_month] = []
                events_by_month[year_month].append(event)
            except ValueError as e:
                print(f"處理日期時發生錯誤: {event.get('date')} - {e}")
                traceback.print_exc()
                continue

        # 4. 將活動轉換為 index.html 中 event data 的 JavaScript 陣列格式
        venue_to_class_map = {
            '拘久屋': 'jukuya',
            '玩具間': 'toyroom',
            '更衣間': 'gengyiroom',
            '思': 'think',
            '動物方程式': 'zoo',
            '其他': 'other'
        }
        js_event_data = {}        
        for year_month, events_list in events_by_month.items():
            js_events = []
            for event in events_list:
                venue = event.get('venue', '')
                venue_class = venue_to_class_map.get(venue, 'other')
                # 轉換為 HTML 格式所需的鍵名
                js_events.append({
                    'date': datetime.strptime(event['date'], '%Y-%m-%d').day,
                    'venue': venue,
                    'title': event.get('title', ''),
                    'time': f"{event.get('start_time', '')}~{event.get('end_time', '')}",
                    'class': venue_class,
                    'link': event.get('link', None)
                })
            # 將月份名稱轉換為 JavaScript 變數名（例如 '2025-08' -> 'augustEvents'）
            month_name_abbr = datetime.strptime(year_month, '%Y-%m').strftime('%B').lower() # 'august'
            js_event_data[f"{month_name_abbr}Events"] = json.dumps(js_events, ensure_ascii=False, indent=4)

        # 5. 更新 index.html
        html_filepath = './index.html'
        try:
            with open(html_filepath, 'r', encoding='utf-8') as f:
                html_content = f.read()

            all_month_vars = [
                'januaryEvents', 'februaryEvents', 'marchEvents', 'aprilEvents',
                'mayEvents', 'juneEvents', 'julyEvents', 'augustEvents',
                'septemberEvents', 'octoberEvents', 'novemberEvents', 'decemberEvents'
            ]

            updated_html_content = html_content
            for month_var in all_month_vars:
                # Get the JSON string for the current month, default to '[]' if no events
                js_array_str = js_event_data.get(month_var, '[]')
                
                # Use regex to find and replace the event array for the current month
                pattern = rf"const\s+{month_var}\s*=\s*\[[\s\S]*?\];"
                replacement = f"const {month_var} = {js_array_str};"
                
                # Perform the replacement
                updated_html_content = re.sub(pattern, replacement, updated_html_content, count=1)
            
            with open(html_filepath, 'w', encoding='utf-8') as f:
                f.write(updated_html_content)

            messagebox.showinfo("同步網站", "網站活動資料已成功更新！")

        except Exception as e:
            messagebox.showerror("同步網站錯誤", f"更新 index.html 時發生錯誤: {e}")
            print(f"更新 index.html 錯誤: {e}")
            traceback.print_exc()

    def on_closing(self):
        self.stop_crawler()
        self.asyncio_thread.stop()
        # 關閉 XCrawler 實例
        if hasattr(self, 'crawler') and self.crawler:
            self.crawler.close()
        self.destroy()

if __name__ == "__main__":
    app = EventCrawlerUI()
    app.mainloop()
