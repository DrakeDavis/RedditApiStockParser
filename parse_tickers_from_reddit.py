# This script connects to reddit's API and retrieves a count of stock $ticker mentions to gauge rising popularity.
import praw
import json
import time
import datetime
from datetime import timezone
import re
import boto3
import os
import pytz


# Function to find all occurrences of the stock ticker (or $ticker) with case ignored. Returns the number of occurrences
def find_occurrences_of_stock_ticker(arg_ticker, arg_text_to_search):
    # Regex that also checks for boundaries (start of sentence, end of sentence, etc.)
    reg_ex_count = sum(1 for match in re.finditer(r"\b{}\b".format(arg_ticker), arg_text_to_search, re.IGNORECASE))

    # Also check for ticker with a $ in front of it
    prefaced_ticker = "$" + arg_ticker
    reg_ex_count = reg_ex_count + sum(1 for match in re.finditer(r"\b{}\b".format(prefaced_ticker), arg_text_to_search,
                                                                 re.IGNORECASE))
    return reg_ex_count


# Connection credentials to reddit's API
reddit = praw.Reddit(
    client_id=os.environ['REDDIT_API_CLIENT_ID'],
    client_secret=os.environ['REDDIT_API_CLIENT_SECRET'],
    user_agent=os.environ['REDDIT_API_USER_AGENT']
)

# Instantiating objects
posts_in_last_day = []
text_blob = ''

# Get all posts from subreddit in the last 24 hours (limit is 900, but no 24 period has reached that number)
for post in reddit.subreddit("wallstreetbets").new(limit=900):
    post_title = post.title
    post_creation_epoch_time = post.created - 60 * 60 * 8  # subtracting 8 hours due to timezone
    current_epoch_time = int(time.time())
    age_of_post_in_hours = (current_epoch_time - post_creation_epoch_time) / 60 / 60

    if age_of_post_in_hours < 24:
        posts_in_last_day.append(post)

# Define metrics for posts and comments in the last 24 hours
post_count_in_last_day = posts_in_last_day.__len__()
comments_in_last_day = 0

# Retrieve all comments from the acquired posts
for post in posts_in_last_day:
    text_blob = text_blob + post.title
    post.comments.replace_more(limit=1)
    for comment in post.comments.list():
        if comment.body:
            comments_in_last_day = comments_in_last_day + 1
            text_blob = text_blob + comment.body

# The text_blob is an amalgamation of all posts and comments from the last 24 hours
# We're going to parse it and find occurrences of stock names
dictionary = {}
with open("curated_stock_tickers.txt") as f:
    for line in f:
        line = line.rstrip('\n')
        print("Currently counting: " + str(line))
        occurrences = find_occurrences_of_stock_ticker(line, text_blob)
        if occurrences > 0:
            dictionary[line] = occurrences

# Get the current time and format it accordingly
current_time = datetime.datetime.now(timezone.utc)
est = pytz.timezone('US/Eastern')
date_format = "%d %B %I:%M %p"

# Write out the data in .json format for consumption by the frontend
json_data = {"posts": post_count_in_last_day, "comments": comments_in_last_day,
             "time": current_time.astimezone(est).strftime(date_format),
             "data": (sorted(dictionary.items(), key=lambda x: x[1], reverse=True))}
fp = open('reddit_most_mentioned_stocks.json', 'w+')
fp.write(json.dumps(json_data))
fp.close()

# Open connection to AWS S3 bucket
s3 = boto3.resource('s3',
                    aws_access_key_id=os.environ['S3_KEY'],
                    aws_secret_access_key=os.environ['S3_SECRET'])
s3_client = boto3.client('s3',
                         aws_access_key_id=os.environ['S3_KEY'],
                         aws_secret_access_key=os.environ['S3_SECRET'])

# Upload the .json file to S3. Making it public so anyone can use it.
s3_client.upload_file('reddit_most_mentioned_stocks.json', 'wsb-pop-index', 'wsbPopIndex.json',
                      ExtraArgs={'ContentType': "application/json", 'ACL': 'public-read'})
