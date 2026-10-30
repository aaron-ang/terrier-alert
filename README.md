# Terrier Alert

A Python service that collects class information at Boston University and sends a notification via [Telegram](https://telegram.org/) bot when a class is open.

Deployed on [Render](https://render.com/).

> [!WARNING]
> **Alerts paused.** Since around October 12, 2026, BU's public class search (`public.mybustudent.bu.edu`) has answered every request with HTTP 503 "No backend server available". The bot detects HTTP errors and timeouts from the search. It then pauses checks and posts to the feedback channel, once when the search goes down and once when it recovers. The flag is held in memory, so each restart can post the outage message again. Subscriptions stay in place while the search returns errors.

## Demo

![demo](doc/terrier-alert-demo.gif)

### Register Feature (Deprecated)

![register](doc/terrier-alert-register.gif)

## System Design Overview

![system schema](doc/terrier-alert-design-latest.png)

## Technical Details

One process ([src/server.py](src/server.py)) serves the health check at `GET /`, receives Telegram updates by webhook at `POST /telegram`, and runs the bot and its finder job.
The webhook URL is `WEBHOOK_URL`, or `RENDER_EXTERNAL_URL`, which Render sets for web services.
Requests must carry a secret token derived from the bot token.
In prod the server refuses to start without a webhook URL. In dev, without one, the bot polls instead.

Seat data comes from BU's public class search through `BUClassSearch` in [src/search.py](src/search.py).
`Finder` in [src/finder.py](src/finder.py) depends only on the `CourseSearch` protocol, so a different seat data source can replace BU's public search without changes to the finder.

Database is a MongoDB Atlas Cluster.  
There are two collections: _courses_ and _users_.

Each document in the _courses_ collection has the following schema:

- \_id: `ObjectId`
- name: `String`
- users: `String[]`

Each document in the _users_ collection has the following schema:

- \_id: `ObjectId`
- user: `String`
- last_subscribed: `Date`
- is_subscribed: `Boolean`
- last_subscription: `String`

## Development

```sh
uv sync
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run pytest -m "not live"   # unit tests, no network
uv run pytest -m live         # queries BU's live class search; skips while BU is down
```

Create a `.env` file with `TELEGRAM_TOKEN`, `TEST_TELEGRAM_TOKEN`, `FEEDBACK_CHANNEL_ID`, `MONGO_URL` and `REPO_URL`. Then run the dev bot, which polls unless `WEBHOOK_URL` is set:

```sh
./src/main.sh --dev
```

Run the admin scripts from the repository root as modules, for example `uv run python -m admin.commands`.
