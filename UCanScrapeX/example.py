import os
from datetime import datetime
from seleniumbase_crawler import XCrawler

# Example Usage
# Using a context manager is recommended as it handles browser closing automatically.
with XCrawler() as crawler:
    # --- Login Step ---
    # You only need to run this login process once.
    # After the first successful login, SeleniumBase saves your session data (cookies, etc.)
    # in the user_data_dir (e.g., 'profile1'). On subsequent runs, the crawler
    # will use this saved session, and you will be already logged in.
    # If you are already logged in, you can comment out this 'if' block.
    if crawler.login_to_x():
        
        # --- Scraping Step ---
        # Scrape tweets, ignoring retweets and pinned tweets by default.
        username_to_scrape = "ugcxvjk"
        tweets = crawler.scrape_x_tweets(
            username_to_scrape, 
            num_tweets=20, 
            debug=False,
            ignore_retweets=True,
            ignore_pinned=True
        )
        
        # --- Data Saving Step ---
        if tweets:
            # Create the outputs directory if it doesn't exist
            output_dir = "outputs"
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate filename based on current time and username
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{username_to_scrape}.json"
            filepath = os.path.join(output_dir, filename)
            
            crawler.save_tweets_data(tweets, filepath)
            print(f"✅ Successfully scraped and saved {len(tweets)} tweets to {filepath}")
        else:
            print("❌ No tweets were scraped.")
