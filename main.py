import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from config import settings
from models import TradingViewAlert
from gateio_client import GateioClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("webhook")

app = FastAPI(title="TradingView -> Gate.io Bot")
client = GateioClient()


@app.get("/health")
def health():
    return {"status": "ok", "market_type": settings.MARKET_TYPE, "dry_run": settings.DRY_RUN}


@app.post("/webhook")
async def webhook(request: Request):
    raw = await request.json()
    log.info("Alert received: %s", {k: v for k, v in raw.items() if k != "passphrase"})

    try:
        alert = TradingViewAlert(**raw)
    except Exception as e:
        log.warning("Rejected malformed alert: %s", e)
        raise HTTPException(status_code=422, detail=str(e))

    if alert.passphrase != settings.WEBHOOK_PASSPHRASE:
        log.warning("Rejected alert with bad passphrase.")
        # Deliberately vague error so a bad actor probing the endpoint learns nothing.
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        result = handle_alert(alert)
        return JSONResponse({"status": "ok", "result": result})
    except ValueError as e:
        # Expected/validation-style failures (e.g. below min order size)
        log.warning("Order rejected: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.exception("Unexpected error handling alert")
        raise HTTPException(status_code=500, detail="Internal error, check server logs")


def handle_alert(alert: TradingViewAlert):
    symbol = alert.symbol

    if alert.action == "close_all":
        return {"closed": client.close_position(symbol)}

    if alert.action == "close_long":
        pos = client.get_position(symbol)
        if not pos or pos["side"] != "long":
            return {"note": "No open long position to close."}
        return {"closed": client.close_position(symbol)}

    if alert.action == "close_short":
        pos = client.get_position(symbol)
        if not pos or pos["side"] != "short":
            return {"note": "No open short position to close."}
        return {"closed": client.close_position(symbol)}

    # Otherwise this is an entry: "buy" (go/add long) or "sell" (go/add short)
    side = alert.action  # "buy" or "sell"

    if alert.leverage:
        client.set_leverage(symbol, alert.leverage)
    elif settings.MARKET_TYPE == "swap":
        client.set_leverage(symbol, settings.DEFAULT_LEVERAGE)

    amount = client.calc_order_amount(symbol, alert.quantity_pct)

    order = client.place_entry_order(
        symbol, side, amount,
        order_type=alert.order_type,
        price=alert.limit_price,
    )

    entry_price = alert.limit_price or client.last_price(symbol)
    bracket = {}
    if alert.stop_loss_pct or alert.take_profit_pct:
        bracket = client.place_stop_loss_take_profit(
            symbol, side, amount, entry_price,
            sl_pct=alert.stop_loss_pct, tp_pct=alert.take_profit_pct,
        )

    return {"entry_order": order, "bracket_orders": bracket, "amount": amount}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=False)
