"""Reddit ticker-mention scraper.

Scans hot + top-of-day posts in the configured subreddits and counts
$TICKER cashtags in post titles, bodies, and the top N comments per post.
"""

import logging
import re
from collections import Counter

import praw

import config

log = logging.getLogger(__name__)

CASHTAG_RE = re.compile(r"\$([A-Z]{1,5})\b")


def extract_tickers(text: str) -> list[str]:
    """All non-blacklisted $TICKER cashtags in a block of text."""
    if not text:
        return []
    return [t for t in CASHTAG_RE.findall(text) if t not in config.TICKER_BLACKLIST]


def _client() -> praw.Reddit:
    return praw.Reddit(
        client_id=config.REDDIT_CLIENT_ID,
        client_secret=config.REDDIT_CLIENT_SECRET,
        user_agent=config.REDDIT_USER_AGENT,
    )


def scrape() -> Counter:
    """Mention counts per ticker across all configured subreddits."""
    reddit = _client()
    counts: Counter = Counter()
    seen_posts: set[str] = set()

    for name in config.SUBREDDITS:
        subreddit = reddit.subreddit(name)
        posts = []
        for listing in (
            subreddit.hot(limit=config.REDDIT_POST_LIMIT),
            subreddit.top(time_filter="day", limit=config.REDDIT_POST_LIMIT),
        ):
            try:
                posts.extend(listing)
            except Exception:
                log.exception("Failed to fetch a listing for r/%s", name)

        for post in posts:
            if post.id in seen_posts:
                continue
            seen_posts.add(post.id)

            counts.update(extract_tickers(post.title))
            counts.update(extract_tickers(getattr(post, "selftext", "")))

            try:
                post.comments.replace_more(limit=0)
                for comment in post.comments[: config.REDDIT_COMMENTS_PER_POST]:
                    counts.update(extract_tickers(comment.body))
            except Exception:
                log.exception("Failed to read comments on post %s", post.id)

        log.info("r/%s scanned (%d unique posts so far)", name, len(seen_posts))

    return counts
