# RedditApiStockParser

This script pulls the latest posts and comments from a subreddit and counts how often each stock ticker is mentioned. I built it to track which stocks are getting the most attention on Reddit, especially in places like r/wallstreetbets.

## How it works
- Connects to Reddit's API (you'll need your own API keys, see below)
- Collects all post titles, bodies, and comments (up to a reasonable API-safe limit)
- Counts every mention of each ticker in `curated_stock_tickers.txt`
- Outputs a JSON file with the results (number of posts, comments, and a sorted list of tickers by mention count)

## Setup
1. **Clone the repo**
2. Make sure you have Python 3.10+ and pip
3. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```
4. Set up your Reddit API credentials as environment variables:
   - `REDDIT_API_CLIENT_ID`
   - `REDDIT_API_CLIENT_SECRET`
   - `REDDIT_API_USER_AGENT` (should look like `script:YourAppName:v1.0.0 (by /u/YourUsername)`)
5. (Optional, for S3 upload) Set `S3_KEY` and `S3_SECRET` if you want to upload results to AWS S3.

## Usage
Run the script from the command line, passing the subreddit name as an argument:

```sh
python parse_tickers_from_reddit.py wallstreetbets
```

- The script will create a file like `wallstreetbets_most_mentioned_stocks.json` in the current directory.
- If you want to analyze a different subreddit, just change the argument.

## Notes
- The script is careful not to hit Reddit's API too hard, but if you run it a lot, you might still get rate-limited.
- The ticker list comes from `curated_stock_tickers.txt`. You can update this file if you want to track different stocks.
- If you have any issues or suggestions, feel free to open an issue or fork it.

---

I wrote this for my own curiosity Hope it's useful for someone else too.
