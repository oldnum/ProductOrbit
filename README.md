## About 📌
🔍 Async service for parsing products and reviews from Hotline, Comfy and Brain.

## Requirements ⚙️
- Docker
- Docker Compose

## Technologies 🛠️
- **Backend:** FastAPI (async)
- **Database:** MongoDB (Motor driver)
- **Parsing:** BeautifulSoup / lxml / Playwright
- **Validation:** Pydantic v2
- **Containerization:** Docker + Docker Compose

## Installation ☁️
1. Clone the repository.
2. Create a `.env` file (optional, by default values from `docker-compose.yml` are used).
3. Run the services via Docker Compose:

```bash
docker-compose up --build
```

The service will be available at `http://localhost:8000`.

## API Endpoints 🔗

### Get offers from Hotline
```bash
GET /product/offers?url=<URL>&timeout_limit=5&count_limit=10&sort=asc
```
- `timeout_limit` (int): Timeout limit in seconds. Maximum is 60, minimum is 10. Default is 60.
- `count_limit` (int): Limit number of offers. Maximum is 1000, minimum is 10. Default is 10.
- `sort` (str | None): Sort order: 'asc' or 'desc'. Default is None (no sort).

### Get reviews from Comfy/Brain
```bash
GET /product/comments?url=<URL>&date_to=2024-02-08
```
- `date_to` (str | None): Filter reviews up to date (YYYY-MM-DD). Default is None (no filter).

## Basic structure 🛠️
- `app/api/`: API routes.
- `app/core/`: Configuration and database connection.
- `app/models/`: Pydantic models (internal and external).
- `app/services/`: Parsing logic.
- `app/main.py`: Entry point of the application.

## Disclaimer 🔰
> The information presented here is intended solely for educational and research purposes. It helps to better understand how systems work and how to apply secure practices in software development. 🔒
>
> The author does not endorse or encourage the use of this information for illegal purposes 🚨
>
> Use this knowledge responsibly and follow best practices in software development. 👀

## Donation 💰
* 📒 BTC: `bc1qqxzd80fgzqyy4wjfqsweplfmw3av7hxp07eevx`
* 📘 ETH: `0x20be839c0b9d888e5DD153Cc55A4b93bb8496c48`
* 📗 USDT (TRC20): `TY6SjeCBE4TRedVCbqk3XLqk5F4UMSGYqw`