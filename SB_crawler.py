import os
import json
import re
import time
import traceback
from datetime import datetime
import pytz
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from UCanScrapeX import XCrawler

class SBCrawler:
    """SB玩具間活動日曆爬蟲"""
    
    def __init__(self, driver=None, user_data_dir="profile1", locale_code='zh-TW'):
        """初始化爬蟲
        
        Args:
            driver: 外部傳入的 WebDriver（如果提供，則使用此 driver；否則創建新的）
            user_data_dir: 瀏覽器配置目錄（當 driver 為 None 時使用）
            locale_code: 語言代碼（當 driver 為 None 時使用）
        """
        self.external_driver = driver is not None  # 記錄是否使用外部 driver
        
        if driver:
            # 使用外部傳入的 driver
            self.driver = driver
            self.crawler = None
        else:
            # 創建新的 XCrawler
            self.crawler = XCrawler(user_data_dir=user_data_dir, locale_code=locale_code)
            self.driver = self.crawler.driver
            
        self.venue_name = "玩具間"
        self.output_dir = "outputs"
        
    def scrape_events(self, url="https://studiobondage.com/sb%e7%8e%a9%e5%85%b7%e9%96%93%e6%b4%bb%e5%8b%95%e6%97%a5%e6%9b%86/", debug=False):
        """爬取 SB玩具間 活動日曆
        
        Args:
            url: 活動日曆網址
            debug: 是否顯示詳細 debug 信息
        """
        # 記錄原始窗口大小
        original_size = self.driver.get_window_size()
        original_width = original_size['width']
        original_height = original_size['height']
        
        if debug:
            print(f"[DEBUG] 原始窗口大小: {original_width}x{original_height}")
        
        try:
            # 調整瀏覽器窗口大小為 360x750（手機模式）
            self.driver.set_window_size(360, 750)
            if debug:
                print(f"[DEBUG] 瀏覽器窗口已調整為 360x750")
            
            print(f"⏳ 正在訪問 {url}")
            self.driver.get(url)
            
            # 等待頁面載入 - 等待表格出現
            time.sleep(3)  # 等待頁面完全載入
            
            print("✅ 頁面載入成功，開始解析活動...")
            
            # 先獲取當前顯示的年月
            current_year, current_month = self._get_current_year_month(debug=debug)
            
            if debug:
                print(f"[DEBUG] 當前日曆: {current_year} 年 {current_month} 月")
            
            # 找到所有包含活動的表格單元格（只找有 has_events 類的）
            event_cells = self.driver.find_elements(By.CSS_SELECTOR, "td.has_events")
            
            if debug:
                print(f"[DEBUG] 找到 {len(event_cells)} 個包含活動的 td 元素")
            
            events = []
            taipei_tz = pytz.timezone('Asia/Taipei')
            
            for i, cell in enumerate(event_cells):
                try:
                    if debug:
                        print(f"\n[DEBUG] === 單元格 #{i+1} ===")
                    
                    event_data_list = self._parse_event_cell(cell, taipei_tz, current_year, current_month, debug=debug)
                    if event_data_list:
                        for event_data in event_data_list:
                            events.append(event_data)
                            if debug:
                                print(f"[DEBUG] ✅ 成功解析活動: {event_data['title']}")
                except Exception as e:
                    if debug:
                        print(f"⚠️ 解析單元格 #{i+1} 時出錯: {e}")
                        traceback.print_exc()
                    continue
            
            print(f"📊 統計: 成功解析 {len(events)} 個活動")
            return events
            
        except Exception as e:
            print(f"❌ 爬取活動時出錯: {e}")
            traceback.print_exc()
            return []
        finally:
            # 恢復原始窗口大小
            try:
                self.driver.set_window_size(original_width, original_height)
                if debug:
                    print(f"[DEBUG] 窗口已恢復為原始大小: {original_width}x{original_height}")
            except Exception as e:
                if debug:
                    print(f"[DEBUG] 恢復窗口大小時出錯: {e}")
    
    def _get_current_year_month(self, debug=False):
        """從頁面獲取當前顯示的年月"""
        try:
            # 從 h3.ics-calendar-label 獲取年月（格式: "10 月 2025"）
            h3_elements = self.driver.find_elements(By.CSS_SELECTOR, "h3.ics-calendar-label")
            if h3_elements:
                label_text = h3_elements[0].text.strip()
                # 匹配 "10 月 2025" 格式
                match = re.search(r'(\d+)\s*月\s*(\d{4})', label_text)
                if match:
                    month = int(match.group(1))
                    year = int(match.group(2))
                    if debug:
                        print(f"[DEBUG] 從 h3.ics-calendar-label 獲取: {year} 年 {month} 月 (原始文字: '{label_text}')")
                    return year, month
        except Exception as e:
            if debug:
                print(f"[DEBUG] 從 h3 獲取年月時出錯: {e}")
        
        # 備用方案：從 phone_only span 中獲取
        try:
            spans = self.driver.find_elements(By.CSS_SELECTOR, "span.phone_only span[data-date-format='n']")
            if spans:
                month_text = spans[0].text.strip()
                month = int(month_text)
                
                # 獲取年份 - 從當前或推算
                taipei_tz = pytz.timezone('Asia/Taipei')
                now = datetime.now(taipei_tz)
                year = now.year
                
                # 如果月份小於當前月份，可能是明年
                if month < now.month:
                    year += 1
                
                if debug:
                    print(f"[DEBUG] 從備用方案獲取月份: {year} 年 {month} 月")
                return year, month
        except Exception as e:
            if debug:
                print(f"[DEBUG] 備用方案獲取年月時出錯: {e}")
        
        # 最後預設使用當前時間
        taipei_tz = pytz.timezone('Asia/Taipei')
        now = datetime.now(taipei_tz)
        if debug:
            print(f"[DEBUG] 使用當前時間作為預設: {now.year} 年 {now.month} 月")
        return now.year, now.month
    
    def _parse_event_cell(self, cell, taipei_tz, current_year, current_month, debug=False):
        """解析單個活動單元格（可能包含多個活動）"""
        try:
            # 從 class 中提取日期數字 (如 d_01 表示 1 號)
            class_attr = cell.get_attribute("class")
            day_match = re.search(r'd_(\d+)', class_attr)
            if not day_match:
                if debug:
                    print(f"[DEBUG] ❌ 無法從 class 中提取日期: {class_attr}")
                return None
            
            day = int(day_match.group(1))
            date_str = f"{current_year}-{current_month:02d}-{day:02d}"
            
            if debug:
                print(f"[DEBUG] 解析日期: {date_str} (從 class: {class_attr})")
            
            # 找到所有活動項目（<li class="event">）
            event_items = cell.find_elements(By.CSS_SELECTOR, "li.event")
            
            if debug:
                print(f"[DEBUG] 找到 {len(event_items)} 個活動項目")
            
            events = []
            
            for event_item in event_items:
                try:
                    # 提取時間
                    start_time = None
                    end_time = None
                    try:
                        time_span = event_item.find_element(By.CSS_SELECTOR, "span.time")
                        time_text = time_span.text.strip()
                        time_match = re.search(r'(\d{1,2}):(\d{2})\s*[–\-~～]\s*(\d{1,2}):(\d{2})', time_text)
                        if time_match:
                            start_time = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"
                            end_time = f"{int(time_match.group(3)):02d}:{time_match.group(4)}"
                            if debug:
                                print(f"[DEBUG] 解析時間: {start_time} ~ {end_time}")
                    except:
                        pass
                    
                    # 提取標題
                    title = ""
                    try:
                        title_span = event_item.find_element(By.CSS_SELECTOR, "span.title")
                        title = title_span.text.strip()
                        if debug:
                            print(f"[DEBUG] 提取標題: '{title}'")
                    except:
                        if debug:
                            print(f"[DEBUG] ❌ 無法提取標題")
                        continue
                    
                    # 如果標題為空，跳過（沒有活動）
                    if not title:
                        if debug:
                            print(f"[DEBUG] ❌ 標題為空，跳過此活動")
                        continue
                    
                    # 提取連結
                    link = ""
                    try:
                        link_element = event_item.find_element(By.TAG_NAME, "a")
                        link = link_element.get_attribute("href")
                        if debug:
                            print(f"[DEBUG] 找到連結: {link}")
                    except:
                        pass
                    
                    # 建立活動數據
                    event_data = {
                        "date": date_str,
                        "text": f"{self.venue_name} - {title} {start_time}~{end_time}" if start_time else f"{self.venue_name} - {title}",
                        "check": True,  # 從網站抓下來的都設為 True
                        "venue": self.venue_name,
                        "start_time": start_time,
                        "end_time": end_time,
                        "link": link,
                        "title": title,
                        "brief_description": "",
                        "delete": False,
                        "category": self._categorize_event(title)
                    }
                    
                    events.append(event_data)
                    
                except Exception as e:
                    if debug:
                        print(f"[DEBUG] 解析單個活動項目時出錯: {e}")
                    continue
            
            return events if events else None
            
        except Exception as e:
            print(f"⚠️ 解析事件單元格失敗: {e}")
            traceback.print_exc()
            return None
    
    def _categorize_event(self, title):
        """根據標題自動分類活動"""
        title_lower = title.lower()
        
        # 根據關鍵字分類
        if 'bd' in title_lower or '綁縛' in title:
            return 'bd'
        elif 'sp' in title_lower or '拍打' in title:
            return 'sp'
        elif 'v.i.p' in title_lower or 'vip' in title_lower or '別館' in title:
            return 'ss'
        elif '放飛' in title or '聊天' in title or 'ds' in title_lower or 'sm' in title_lower:
            return 'so'
        elif '工作坊' in title or '體驗' in title:
            return 'wk'
        else:
            return 'so'  # 預設為社交類
    
    def save_events(self, events, filename=None, merge_existing=True):
        """儲存活動到 JSON 檔案
        
        Args:
            events: 要儲存的活動列表
            filename: 檔案名稱（預設為 玩具間_events.json）
            merge_existing: 是否與現有檔案合併（預設為 True）
        """
        try:
            os.makedirs(self.output_dir, exist_ok=True)
            
            if filename is None:
                filename = f"{self.venue_name}_events.json"
            
            filepath = os.path.join(self.output_dir, filename)
            
            final_events = events
            
            # 如果要合併，先讀取現有檔案
            if merge_existing and os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        existing_events = json.load(f)
                    
                    # 合併活動，避免重複
                    final_events = self._merge_events(existing_events, events)
                    print(f"📋 已與現有 {len(existing_events)} 個活動合併")
                except Exception as e:
                    print(f"⚠️ 讀取現有檔案時出錯，將使用新資料: {e}")
            
            # 按日期排序
            final_events.sort(key=lambda x: x.get('date', ''))
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(final_events, f, ensure_ascii=False, indent=4)
            
            print(f"✅ 活動已儲存至 {filepath} (共 {len(final_events)} 個活動)")
            return filepath
            
        except Exception as e:
            print(f"❌ 儲存活動時出錯: {e}")
            traceback.print_exc()
            return None
    
    def _merge_events(self, existing_events, new_events):
        """合併現有活動和新活動，避免重複
        
        Args:
            existing_events: 現有活動列表
            new_events: 新活動列表
            
        Returns:
            合併後的活動列表
        """
        # 建立現有活動的唯一標識集合（日期 + 標題）
        existing_keys = {
            (event.get('date'), event.get('title'))
            for event in existing_events
            if event.get('date') and event.get('title')
        }
        
        # 合併活動
        merged = list(existing_events)
        
        for new_event in new_events:
            key = (new_event.get('date'), new_event.get('title'))
            if key not in existing_keys:
                merged.append(new_event)
                existing_keys.add(key)
                print(f"  ➕ 新增活動: {new_event.get('date')} - {new_event.get('title')}")
            else:
                # 如果活動已存在，但從網站抓的資料更完整，則更新
                # 找到對應的現有活動並更新
                for i, existing_event in enumerate(merged):
                    if (existing_event.get('date'), existing_event.get('title')) == key:
                        # 如果新活動有連結而舊活動沒有，則更新
                        if new_event.get('link') and not existing_event.get('link'):
                            merged[i]['link'] = new_event['link']
                            print(f"  🔄 更新活動連結: {new_event.get('date')} - {new_event.get('title')}")
                        # 確保 check 設為 True（從網站抓的都是已確認的）
                        merged[i]['check'] = True
                        break
        
        return merged
    
    def close(self):
        """關閉瀏覽器（僅當使用自己的 driver 時）"""
        # 如果使用外部 driver，不要關閉它
        if not self.external_driver and self.crawler and self.crawler.driver:
            self.crawler.driver.quit()
            print("✅ 瀏覽器已關閉")


def main():
    """主函數 - 示例用法"""
    crawler = None
    try:
        print("🚀 啟動 SB玩具間 爬蟲...")
        crawler = SBCrawler(user_data_dir="profile1", locale_code='zh-TW')
        
        # 爬取活動
        events = crawler.scrape_events()
        
        if events:
            # 儲存活動
            crawler.save_events(events)
            print(f"\n📊 總共爬取了 {len(events)} 個活動")
            
            # 顯示前幾個活動
            print("\n🔍 活動預覽（前 3 個）:")
            for event in events[:3]:
                print(f"  - {event['date']} {event['title']}")
        else:
            print("⚠️ 沒有爬取到任何活動")
            
    except Exception as e:
        print(f"❌ 執行過程中出錯: {e}")
        traceback.print_exc()
    finally:
        if crawler:
            crawler.close()


if __name__ == "__main__":
    main()

