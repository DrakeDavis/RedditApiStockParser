# This script connects to reddit's API, retrieves a count of stock $ticker mentions,
# and calculates an average VADER sentiment score per ticker from the comments that mention it.
import praw
import json
import time
import datetime
from datetime import timezone
from collections import defaultdict
import re
import boto3
import os
import pytz
import sys
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer


def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# Connection credentials to reddit's API
reddit = praw.Reddit(
    client_id=os.environ['REDDIT_API_CLIENT_ID'],
    client_secret=os.environ['REDDIT_API_CLIENT_SECRET'],
    user_agent=os.environ['REDDIT_API_USER_AGENT'],
    ratelimit_seconds=300
)

analyzer = SentimentIntensityAnalyzer()

# Retrieve subreddit name from terminal argument
if len(sys.argv) < 2:
    print("Usage: python parse_tickers_and_sentiment.py <subreddit_name>")
    sys.exit(1)
subreddit_name = str(sys.argv[1])

# Load the curated ticker list and build two sets for fast O(1) lookup:
#   dollar_required_tickers: lines like "$A" in the file — ONLY match when written as $A in text
#   plain_tickers:            lines like "AAPL" in the file — match both AAPL and $AAPL in text
dollar_required_tickers = set()
plain_tickers = set()
for line in open("curated_stock_tickers.txt"):
    ticker = line.strip()
    if not ticker:
        continue
    if ticker.startswith('$'):
        dollar_required_tickers.add(ticker[1:].upper())
    else:
        plain_tickers.add(ticker.upper())

# Instantiating objects
posts_in_last_day = []

log(f"Fetching posts from r/{subreddit_name}...")
post_fetch_count = 0
# Get all posts from subreddit in the last 24 hours (or the last 50 posts, I dont want to hammer reddits API)
for post in reddit.subreddit(subreddit_name).new(limit=50):
    post_creation_epoch_time = post.created_utc
    current_epoch_time = int(time.time())
    age_of_post_in_hours = (current_epoch_time - post_creation_epoch_time) / 60 / 60

    post_fetch_count += 1
    if post_fetch_count % 100 == 0:
        log(f"  Scanned {post_fetch_count} posts so far...")
    if age_of_post_in_hours < 24:
        posts_in_last_day.append(post)

post_count_in_last_day = len(posts_in_last_day)
log(f"Found {post_count_in_last_day} posts in the last 24 hours. Fetching comments...")
comments_in_last_day = 0

# ticker_mentions[ticker] = count of text segments (title/selftext/comment) that mention it
# ticker_sentiment_scores[ticker] = list of VADER compound scores from those segments
ticker_mentions = defaultdict(int)
ticker_sentiment_scores = defaultdict(list)


def process_text_segment(text):
    """Score a single text segment with VADER and attribute it to any tickers it mentions."""
    if not text or not text.strip():
        return
    # Find $-prefixed tokens (e.g. $A, $AAPL) — match against both sets
    dollar_tokens = set(t.upper() for t in re.findall(r'\$([A-Za-z]{1,5})\b', text))
    # Find bare all-caps tokens (e.g. NVDA, GME) — only match against plain_tickers
    # (tickers that require $ like "$A" must NOT match bare "A")
    caps_tokens = set(re.findall(r'\b([A-Z]{1,5})\b', text))

    matched_tickers = (
        (dollar_tokens & dollar_required_tickers) |  # $A matches $A-type tickers
        (dollar_tokens & plain_tickers) |            # $AAPL also matches plain tickers
        (caps_tokens & plain_tickers)                # bare AAPL matches plain tickers only
    )
    if matched_tickers:
        score = analyzer.polarity_scores(text)['compound']
        for ticker in matched_tickers:
            ticker_mentions[ticker] += 1
            ticker_sentiment_scores[ticker].append(score)


# Process all posts and their comments
post_metadata = []
for i, post in enumerate(posts_in_last_day):
    log(f"  Post {i + 1}/{post_count_in_last_day}: '{post.title[:60]}'")  # noqa

    # Score the post title and body as individual segments
    process_text_segment(post.title)
    process_text_segment(post.selftext)

    post_comment_count = 0
    post.comments.replace_more(limit=100)
    for comment in post.comments.list():
        if comment.body:
            comments_in_last_day += 1
            post_comment_count += 1
            process_text_segment(comment.body)

    post_metadata.append({
        "title": post.title,
        "url": "https://www.reddit.com" + post.permalink,
        "comments_scanned": post_comment_count
    })

log(f"Fetched {comments_in_last_day} comments. Post breakdown:")
for post in posts_in_last_day:
    log(f"  {post.num_comments:>6} comments — {post.title[:80]}")

log(f"Computing average sentiment for {len(ticker_mentions)} tickers...")

# Build the output — each entry has mention count and average sentiment score
# Sentiment compound score: +1.0 = most positive, -1.0 = most negative, 0 = neutral
output_data = []
for ticker, count in ticker_mentions.items():
    scores = ticker_sentiment_scores[ticker]
    avg_sentiment = round(sum(scores) / len(scores), 4) if scores else 0.0
    output_data.append({
        "ticker": ticker,
        "mentions": count,
        "avg_sentiment": avg_sentiment,
    })

# Sort by mention count descending (same as original script)
output_data.sort(key=lambda x: x["mentions"], reverse=True)

# Get the current time and format it accordingly
current_time = datetime.datetime.now(timezone.utc)
est = pytz.timezone('US/Eastern')
date_format = "%d %B %I:%M %p"

# Write out the data in .json format for consumption by the frontend
post_metadata.sort(key=lambda x: x["comments_scanned"], reverse=True)
api_calls_used = reddit.auth.limits.get('used', 'unknown')
json_data = {
    "posts": post_count_in_last_day,
    "comments": comments_in_last_day,
    "time": current_time.astimezone(est).strftime(date_format),
    "data": output_data,
    "metadata": {
        "posts": post_metadata,
        "total_tickers_found": len(output_data),
        "api_calls_used": api_calls_used
    }
}
output_filename = subreddit_name + '_most_mentioned_stocks_sentiment.json'
with open(output_filename, 'w+') as fp:
    fp.write(json.dumps(json_data, indent=2))

log(f"JSON written with {len(output_data)} tickers -> {output_filename}")
log(f"Total Reddit API calls made this run: {api_calls_used}")

# Open connection to AWS S3 bucket
s3 = boto3.resource('s3',
                    aws_access_key_id=os.environ['S3_KEY'],
                    aws_secret_access_key=os.environ['S3_SECRET'])
s3_client = boto3.client('s3',
                         aws_access_key_id=os.environ['S3_KEY'],
                         aws_secret_access_key=os.environ['S3_SECRET'])
log("Done.")
# Upload the .json file to S3. Making it public so anyone can use it.
#s3_client.upload_file(output_filename, 'wsb-pop-index',
#                       subreddit_name + 'SentimentIndex.json', ExtraArgs={'ContentType': "application/json",
#                       'ACL': 'public-read'})
