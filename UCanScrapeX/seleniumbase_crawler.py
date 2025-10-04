import os
import signal
import sys
import traceback
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from seleniumbase import Driver
import time
import json
import csv
import re
from datetime import datetime
import pytz
from typing import List, Dict, Optional


class XCrawler:
    """
    X (Twitter) Crawler class for object-oriented tweet scraping.
    """
    
    def __init__(self, user_data_dir: str = "profile1", locale_code: str = 'en-US'):
        """
        Initializes the X Crawler.
        
        Args:
            user_data_dir: Browser user data directory.
            locale_code: Language code.
        """
        self.headless = False # Headless mode is often blocked by X, so it's forced to False.
        self.user_data_dir = os.path.abspath(user_data_dir)
        self.locale_code = locale_code
        self.driver = None
        self.taipei_tz = pytz.timezone('Asia/Taipei')
        
        # Initialize the browser driver
        self._initialize_driver()
        
    def _get_chrome_options(self) -> Options:
        """Gets Chrome browser option configurations."""
        options = Options()
        options.add_argument('--start_maximized')
        options.add_argument("--disable-extensions")
        options.add_argument('--disable-application-cache')
        options.add_argument('--disable-gpu')
        options.add_argument("--dns-prefetch-disable")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-notifications")
        user_agent = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/60.0.3112.50 Safari/537.36'
        options.add_argument(f'user-agent={user_agent}')
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--user-data-dir={}".format(self.user_data_dir))
        return options
    
    def _initialize_driver(self):
        """Initializes the SeleniumBase driver."""
        try:
            self.driver = Driver(
                user_data_dir=self.user_data_dir,
                uc=True,
                headless=self.headless,
                locale_code=self.locale_code
            )
            print("⭐ Crawler initialized successfully.")
        except Exception as e:
            print(f"❌ Crawler initialization failed: {e}")
            raise

    def wait_for_elements(self, by, value, waittime: int = 10) -> bool:
        """
        Waits for page elements to load.
        
        Args:
            by: Locator strategy.
            value: Locator value.
            waittime: Wait time in seconds.
            
        Returns:
            bool: Whether the element was successfully waited for.
        """
        try:
            elements_present = EC.presence_of_all_elements_located((by, value))
            WebDriverWait(self.driver, waittime).until(elements_present)
            return True
        except TimeoutException:
            print(f"⏰ Timed out waiting for element: {by}, {value}")
            return False
    
    def save_to_json(self, data: List[Dict] | Dict, json_filename: str) -> bool:
        """
        Saves data to a JSON file.
        
        Args:
            data: Data to save.
            json_filename: JSON filename.
            
        Returns:
            bool: Whether the save was successful.
        """
        try:
            if os.path.exists(json_filename) and os.path.getsize(json_filename) > 0:
                try:
                    with open(json_filename, 'r', encoding='utf-8') as json_file:
                        existing_data = json.load(json_file)
                except json.JSONDecodeError:
                    existing_data = []
            else:
                existing_data = []
            
            if not isinstance(data, list):
                data = [data]
            
            existing_data.extend(data)
            
            with open(json_filename, 'w', encoding='utf-8') as json_file:
                json.dump(existing_data, json_file, ensure_ascii=False, indent=4)
            print(f"✅ Data saved to JSON file: {json_filename}")
            return True
        except Exception as e:
            print(f"❌ Failed to save JSON file: {e}")
            return False

    def scroll_in_element(self, element: WebElement, scroll_amount: int) -> bool:
        """
        Scrolls within a specified element.
        
        Args:
            element: The element to scroll within.
            scroll_amount: The distance to scroll.
            
        Returns:
            bool: Whether the scroll was successful.
        """
        try:
            scroll_script = "arguments[0].scrollTop += arguments[1];"
            self.driver.execute_script(scroll_script, element, scroll_amount)
            return True
        except Exception as e:
            print(f"❌ Scroll operation failed: {e}")
            return False
    
    def clear_file(self, file_path: str) -> bool:
        """
        Clears the content of a file.
        
        Args:
            file_path: The path to the file.
            
        Returns:
            bool: Whether the clear operation was successful.
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write('')
            print(f"✅ File cleared: {file_path}")
            return True
        except Exception as e:
            print(f"❌ Failed to clear file: {file_path}, Error: {e}")
            return False

    def login_to_x(self) -> bool:
        """
        Logs in to X (Twitter).
        
        Returns:
            bool: Whether the login was successful.
        """
        print("🔐 First-time login to X (Twitter). Please log in manually in the browser.")
        try:
            self.driver.get("https://X.com/login")
            print("Please complete the login in the opened browser window. Press Enter to continue scraping after logging in.")
            input("Press Enter when ready...")  # Wait for the user to complete manual login
            print("✅ User has confirmed login is complete.")
            return True
        except Exception as e:
            print(f"❌ Failed to open X (Twitter) login page: {e}")
            print(traceback.format_exc())
            return False

    def scrape_x_tweets(self, username: str, num_tweets: int = 10, debug: bool = False, ignore_retweets: bool = True, ignore_pinned: bool = True) -> List[Dict]:
        """
        Scrapes tweets from a specified user.
        
        Args:
            username: X (Twitter) username.
            num_tweets: Number of tweets to scrape.
            debug: Whether to enable debug mode to show original and cleaned text.
            ignore_retweets: Whether to ignore retweets.
            ignore_pinned: Whether to ignore pinned tweets.
            
        Returns:
            List[Dict]: A list of tweet data.
        """
        print(f"🐦 Scraping tweets from user @{username}, targeting {num_tweets} tweets.")
        tweets_data = []
        processed_links = set()
        bottom_check_count = 0  # 用於追蹤連續檢測到底部的次數

        try:
            self.driver.get(f"https://x.com/{username}")
            time.sleep(5)
            
            last_height = self.driver.execute_script("return document.body.scrollHeight")

            while len(tweets_data) < num_tweets:
                tweet_elements = self.driver.find_elements(By.XPATH, "//article[@data-testid='tweet']")
                
                for tweet in tweet_elements:
                    try:
                        # Get the tweet link
                        link_element = tweet.find_element(By.XPATH, ".//a[time]")
                        tweet_url = link_element.get_attribute('href')

                        if tweet_url in processed_links:
                            continue
                        
                        # Get the full text to check for retweets or pinned status
                        full_text = tweet.text
                        lines = full_text.split('\n')
                        
                        # Check if it's a pinned tweet
                        if ignore_pinned and lines and (lines[0].strip() == "Pinned" or lines[0].strip() == "已釘選"):
                            if debug:
                                print(f"🚫 Ignoring pinned tweet: {tweet_url}\n")
                            continue

                        # Check if it's a retweet
                        is_retweet = False
                        for line in lines[:2]: # Usually in the first two lines
                            if 'reposted' in line or '已轉發' in line:
                                is_retweet = True
                                break
                        if ignore_retweets and is_retweet:
                            if debug:
                                print(f"🚫 Ignoring retweet: {tweet_url}\n")
                            continue

                        processed_links.add(tweet_url)

                        # Get the post time
                        time_element = link_element.find_element(By.TAG_NAME, "time")
                        post_time = time_element.get_attribute('datetime')
                        
                        # Get and clean the tweet text
                        cleaned_text = self._clean_tweet_text(full_text)
                        
                        if debug:
                            print("------------- DEBUG START -------------")
                            print(f"Original Text for tweet {tweet_url}:")
                            print(full_text)
                            print("---------------------------------------")
                            print("Cleaned Text:")
                            print(cleaned_text)
                            print("-------------- DEBUG END --------------\n")
                        
                        tweet_data = {
                            "post_time": post_time,
                            "text": cleaned_text,
                            "tweet_url": tweet_url
                        }
                        tweets_data.append(tweet_data)

                    except Exception:
                        # Skip tweet elements that can't be parsed (e.g., ads or layout changes)
                        continue

                print(f"📊 Scraped {len(tweets_data)} tweets.")
                if len(tweets_data) >= num_tweets:
                    break
                
                # Scroll the page to load more tweets
                self.driver.execute_script("window.scrollBy(0, 800);")
                time.sleep(2) # Wait for content to load
                
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                
                # If the page height has not increased after scrolling, check multiple times to confirm bottom
                if new_height == last_height:
                    bottom_check_count += 1
                    print(f"🔍 檢測到可能的底部 ({bottom_check_count}/5)")
                    
                    if bottom_check_count >= 5:
                        print("📄 已連續5次確認到達底部，結束爬取。")
                        break
                    
                    # 等待0.2秒後重新檢查
                    time.sleep(0.2)
                else:
                    # 高度有變化，重置計數器
                    bottom_check_count = 0
                    last_height = new_height

            if len(tweets_data) < num_tweets:
                print(f"⚠️ Did not scrape enough tweets, only got {len(tweets_data)}.")
            
            return tweets_data

        except TimeoutException:
            print("⏰ Timed out while scraping X (Twitter) tweets.")
            print(traceback.format_exc())
        except Exception as e:
            print(f"❌ Failed to scrape X (Twitter) tweets: {e}")
            print(traceback.format_exc())
        return tweets_data

    def _clean_tweet_text(self, full_text: str) -> str:
        """
        Cleans the tweet text by removing author info and interaction buttons.
        
        Args:
            full_text: The original tweet text.
            
        Returns:
            str: The cleaned tweet text.
        """
        lines = full_text.split('\n')
        
        # Find the start of the content (usually after username and timestamp)
        content_start_index = 0
        for i, line in enumerate(lines):
            # The content usually starts on the second line after the '·' symbol (the first being the date)
            if line.strip() == '·' and i > 0 and i + 2 < len(lines):
                content_start_index = i + 2
                break
        
        if content_start_index == 0 and len(lines) > 4: # Fallback strategy
             content_start_index = 4

        # Find the end of the content (usually before interaction buttons)
        content_end_index = len(lines)
        
        # Common junk phrases in the UI
        junk_phrases = [
            # English
            "Show this thread", "Show more", "Translate post", "View",
            "The author labeled this post as containing sensitive content.",
            "Content warning: Sensitive content", "Adult content",
            "The following media includes potentially sensitive content.",
            "X labeled this post as containing Adult Content.",
            "This Post is from a suspended account. Learn more",
            "Change settings", "Show", "More",
            # Chinese
            "顯示", "顯示更多", "內容警告：成人內容",
            "以下的媒體可能包含敏感內容。變更設定", "查看",
            "X 已將此貼文標示為包含成人內容。",
            "此貼文來自遭停權的帳戶。了解更多",
            # Common
            "…"
        ]

        # Regex to match view counts, likes, etc. e.g., "1,234", "1.5K", "2M", "1.8萬"
        stat_pattern = re.compile(r'^[,\d.]+[KMB萬千]?$')
        
        # Check from the bottom up to find the end of the content
        # The last few lines are usually stats or junk messages
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()
            
            # Check if it's a statistic number or a junk phrase
            if stat_pattern.fullmatch(line) or line in junk_phrases:
                content_end_index = i
            # Check for empty lines, which can also be mixed in at the bottom
            elif not line:
                content_end_index = i
            else:
                # Stop when the first non-junk line is found
                break
        
        if content_start_index >= content_end_index:
            # If positioning is confusing, return the original text
            return full_text 

        cleaned_text = '\n'.join(lines[content_start_index:content_end_index])
        return cleaned_text.strip()

    def save_tweets_data(self, tweets_data: List[Dict], filename: str) -> bool:
        """
        Saves tweet data to a JSON file.
        
        Args:
            tweets_data: A list of tweet data.
            filename: The filename.
            
        Returns:
            bool: Whether the save was successful.
        """
        return self.save_to_json(tweets_data, filename)

    def close(self):
        """
        Closes the browser driver.
        """
        if self.driver:
            try:
                self.driver.quit()
                self.driver = None  # 設為 None 避免重複關閉
                print("✅ Browser closed successfully.")
            except Exception as e:
                print(f"❌ Error while closing the browser: {e}")
                traceback.print_exc()

    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit, cleans up resources automatically."""
        self.close()

    def __del__(self):
        """Destructor to ensure resources are released."""
        # 只在 driver 還存在時才關閉
        if hasattr(self, 'driver') and self.driver is not None:
            try:
                self.close()
            except Exception:
                # 在析構函數中忽略錯誤，避免在程序退出時產生問題
                pass
