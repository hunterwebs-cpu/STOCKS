import re
from collections import defaultdict
from typing import Dict

import praw

import config

_TICKER_RE = re.compile(r'\$([A-Z]{1,5})\b')


def _extract_tickers(text: str) -> list:
    if not text:
        return []
    return [
        m for m in _TICKER_RE.findall(text)
        if m not in config.TICKER_BLACKLIST
    ]


def scrape_reddit() -> Dict[str, int]:
    """
    Scrape configured subreddits for $TICKER mentions in post titles,
    bodies, and the top 50 comments per post.
    Returns a dict of {ticker: mention_count}.
    """
    reddit = praw.Reddit(
        client_id=config.REDDIT_CLIENT_ID,
        client_secret=config.REDDIT_CLIENT_SECRET,
        user_agent=config.REDDIT_USER_AGENT,
    )

    counts: Dict[str, int] = defaultdict(int)

    for sub_name in config.REDDIT_SUBREDDITS:
        subreddit = reddit.subreddit(sub_name)
        try:
            posts = list(subreddit.new(limit=100)) + list(subreddit.hot(limit=100))
        except Exception as e:
            print(f"[reddit] Failed to fetch r/{sub_name}: {e}")
            continue

        seen_post_ids = set()
        for post in posts:
            if post.id in seen_post_ids:
                continue
            seen_post_ids.add(post.id)

            for ticker in _extract_tickers(post.title):
                counts[ticker] += 1
            for ticker in _extract_tickers(post.selftext):
                counts[ticker] += 1

            try:
                post.comments.replace_more(limit=0)
                top_comments = post.comments.list()[:50]
                for comment in top_comments:
                    for ticker in _extract_tickers(comment.body):
                        counts[ticker] += 1
            except Exception:
                pass

    return dict(counts)
