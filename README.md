# TradingView → Gate.io Auto-Trading Bot

A small webhook server: TradingView fires an alert → this server validates it →
places/closes an order on Gate.io (spot or USDT-margined perpetual swap) via `ccxt`,
with optional automatic stop-loss / take-profit.

**This is not financial advice, and I'm not a financial advisor.** Automated
trading can lose money quickly, especially with leverage. Test thoroughly in
`DRY_RUN` mode and with small size before trusting it with real funds.

## 1. Setup

```bash
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`:
- `GATEIO_API_KEY` / `GATEIO_API_SECRET` — create these under Gate.io → API Management.
  Only enable **spot trading** and/or **futures trading** permissions, never withdrawals.
- `WEBHOOK_PASSPHRASE` — a long random string. This is the only auth on your webhook,
  so treat it like a password.
- `MARKET_TYPE` — `swap` for USDT-margined perpetual futures, `spot` for spot market.
- `DRY_RUN=true` — leave this on until you've verified the whole flow end-to-end;
  it logs what *would* be sent to Gate.io without sending it.

Run it:

```bash
python main.py
# or: uvicorn main:app --host 0.0.0.0 --port 8000
```

Check it's alive: `GET http://localhost:8000/health`

## 2. Expose it to TradingView

TradingView needs to reach your server over the public internet. Options:
- Quick testing: `ngrok http 8000` and use the `https://xxxx.ngrok.app/webhook` URL it gives you.
- Production: deploy on a small VPS (or a container host) with a real domain and TLS,
  and put it behind a reverse proxy (nginx/Caddy).

**Webhook alerts require a paid TradingView plan** (Pro tier or higher).

## 3. Create the TradingView alert

On your chart/strategy, create an alert. In the alert's **Message** box, use JSON like:

```json
{
  "passphrase": "the_same_string_you_put_in_.env",
  "action": "buy",
  "symbol": "BTC/USDT:USDT",
  "order_type": "market",
  "quantity_pct": 10,
  "leverage": 5,
  "stop_loss_pct": 2,
  "take_profit_pct": 4
}
```

Set the alert's **Webhook URL** to `https://your-server/webhook`.

If you're driving this from a Pine Script strategy, you can inject dynamic values using
placeholders, e.g. `"action": "{{strategy.order.action}}"`, and TradingView will fill
them in when the alert fires.

### Field reference

| Field | Values | Notes |
|---|---|---|
| `action` | `buy`, `sell`, `close_long`, `close_short`, `close_all` | `buy`/`sell` open or add to a position; the others exit |
| `symbol` | ccxt unified symbol | `BTC/USDT:USDT` for the USDT-margined swap, `BTC/USDT` for spot |
| `order_type` | `market`, `limit` | `limit` requires `limit_price` |
| `quantity_pct` | 0–100 | % of available quote balance to commit (capped by `MAX_POSITION_PCT` in `.env`) |
| `leverage` | integer | swap only; falls back to `DEFAULT_LEVERAGE` if omitted |
| `stop_loss_pct` / `take_profit_pct` | percent | optional; places reduce-only bracket orders right after entry fills |

## 4. How it works

- `models.py` — validates every incoming alert against a strict schema before anything touches money.
- `gateio_client.py` — wraps `ccxt`'s Gate.io client: balance lookup, position-size
  calculation, leverage, entry orders, and reduce-only stop-loss/take-profit orders.
- `main.py` — the FastAPI app: checks the passphrase, routes the alert to an entry
  or an exit, and returns the resulting order info as JSON (also logged server-side).

## 5. Safety notes

- Keep `DRY_RUN=true` until you've watched several alerts flow through correctly in the logs.
- `MAX_POSITION_PCT` is a hard cap enforced server-side, independent of what an alert requests —
  keep it low while testing.
- API keys should never have withdrawal permission.
- Consider running this only on `swap` **or** `spot`, matching exactly what your strategy
  was backtested on — mixing the two changes fees, slippage, and liquidation risk.
- Gate.io's exact minimum order sizes and precision vary by pair; `calc_order_amount`
  rounds to what the exchange allows and raises an error rather than silently guessing
  if the resulting size is below the exchange minimum.
