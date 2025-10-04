# UCanScrapeX - X.com Tweet Scraper

[Read in Traditional Chinese (繁體中文)](zh_TW_README.md)

A robust, Selenium-based web scraper designed to efficiently extract tweet data from X.com (formerly Twitter). This tool is built to be resilient against anti-scraping measures by leveraging a browser profile, allowing for persistent login sessions. It focuses on gathering essential tweet information: the content, post time, and direct URL.

## Key Features

- **Persistent Login**: Only requires a one-time manual login. The session is saved to a user profile, enabling automatic logins for subsequent runs.
- **Targeted Scraping**: Scrape tweets from any specified user profile.
- **Content-Focused Data**: Extracts the core data you need:
  - Tweet Text (cleaned of UI clutter)
  - Exact Post Timestamp (in UTC)
  - Permanent URL to the tweet
- **Advanced Filtering**:
  - **Ignore Retweets**: Option to automatically skips retweets to gather original content.
  - **Ignore Pinned Tweets**: Option to exclude pinned tweets from the scrape.
- **Smart Text Cleaning**: Intelligently removes UI elements (like author info, interaction buttons, and view counts) from the tweet text, supporting both English and Chinese interfaces.
- **Organized Output**: Saves scraped data into a structured JSON file, automatically named with a timestamp and the target username (e.g., `20251001_153000_username.json`), and stores it in a dedicated `outputs/` directory.
- **Debug Mode**: An optional debug mode prints the original and cleaned text for each tweet, helping to verify and refine the text-cleaning logic.

## Setup Instructions

- **Python 3.11**: Ensure you have Python installed. It's recommended to use a virtual environment.
- **Install Dependencies**: Navigate to the `UCanScrapeX` directory in your terminal and run the following command to install the required packages:
  ```bash
  pip install -r requirements.txt
  ```

## How to Use

### 1. Configure the Scraper

Open the `example.py` file and configure the scraping parameters:

- `username_to_scrape`: Set the X.com username of the account you want to scrape (e.g., `"ugcxvjk"`).
- `num_tweets`: Set the desired number of tweets to collect.

### 2. First-Time Login

The first time you run the scraper, you will need to log in to X.com manually. This step saves your session cookies to the `profile1/` directory, allowing the scraper to log in automatically in the future.

Run the script:
```bash
python example.py
```

- A Chrome browser window will open and navigate to the X.com login page.
- Log in with your credentials.
- Once you are successfully logged in and see the X.com homepage, return to your terminal and press **Enter**.

### 3. Subsequent Runs

For all subsequent runs, the browser will use the saved session data in `profile1/`. You will already be logged in. When the script prompts you with "Press Enter when ready...", you can simply press **Enter** immediately to proceed with scraping.

The scraped data will be saved as a JSON file in the `outputs/` directory.
