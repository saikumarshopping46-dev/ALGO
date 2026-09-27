import logging
import ccxt

from config import settings

log = logging.getLogger("gateio_client")


class GateioClient:
    """
    Thin wrapper around ccxt's gateio exchange class.
    Handles both spot ('spot') and USDT-margined perpetual swap ('swap') markets,
    controlled by config.MARKET_TYPE.
    """

    def __init__(self):
        self.exchange = ccxt.gateio({
            "apiKey": settings.GATEIO_API_KEY,
            "secret": settings.GATEIO_API_SECRET,
            "enableRateLimit": True,
            "options": {
                "defaultType": settings.MARKET_TYPE,  # "spot" or "swap"
            },
        })
        self.exchange.load_markets()

    # ---------- account info ----------

    def get_quote_balance(self, symbol: str) -> float:
        """Available balance in the symbol's quote currency (e.g. USDT)."""
        market = self.exchange.market(symbol)
        quote = market["quote"]
        balance = self.exchange.fetch_balance()
        free = balance.get(quote, {}).get("free")
        return float(free or 0.0)

    def get_position(self, symbol: str):
        """Returns the open position dict for symbol, or None. Swap markets only."""
        if settings.MARKET_TYPE != "swap":
            return None
        positions = self.exchange.fetch_positions([symbol])
        for p in positions:
            contracts = p.get("contracts") or 0
            if contracts and float(contracts) != 0:
                return p
        return None

    def last_price(self, symbol: str) -> float:
        ticker = self.exchange.fetch_ticker(symbol)
        return float(ticker["last"])

    # ---------- order sizing ----------

    def calc_order_amount(self, symbol: str, quantity_pct: float) -> float:
        """
        Convert 'use quantity_pct% of available balance' into a base-asset amount,
        respecting the exchange's minimum order size and precision rules.
        """
        quantity_pct = min(quantity_pct, settings.MAX_POSITION_PCT)
        quote_balance = self.get_quote_balance(symbol)
        price = self.last_price(symbol)
        spend = quote_balance * (quantity_pct / 100.0)
        amount = spend / price
        amount = float(self.exchange.amount_to_precision(symbol, amount))

        market = self.exchange.market(symbol)
        min_amount = (market.get("limits", {}).get("amount", {}) or {}).get("min")
        if min_amount and amount < min_amount:
            raise ValueError(
                f"Calculated order size {amount} {market['base']} is below the "
                f"exchange minimum of {min_amount}. Increase quantity_pct or "
                f"account balance."
            )
        return amount

    # ---------- leverage ----------

    def set_leverage(self, symbol: str, leverage: int):
        if settings.MARKET_TYPE != "swap":
            return
        try:
            self.exchange.set_leverage(leverage, symbol)
        except Exception as e:
            log.warning("Could not set leverage for %s: %s", symbol, e)

    # ---------- orders ----------

    def place_entry_order(self, symbol: str, side: str, amount: float,
                           order_type: str = "market", price: float = None):
        """side: 'buy' or 'sell'."""
        if settings.DRY_RUN:
            log.info("[DRY_RUN] would place %s %s order: %s %s @ %s",
                      order_type, side, amount, symbol, price or "market")
            return {"dry_run": True, "side": side, "amount": amount, "symbol": symbol}

        if order_type == "market":
            return self.exchange.create_order(symbol, "market", side, amount)
        return self.exchange.create_order(symbol, "limit", side, amount, price)

    def place_reduce_only_order(self, symbol: str, side: str, amount: float,
                                 order_type: str = "market", price: float = None,
                                 stop_price: float = None, kind: str = None):
        """
        Used for stop-loss / take-profit / manual close orders that should only
        reduce an existing position, never open a new one in the opposite direction.
        """
        params = {}
        if settings.MARKET_TYPE == "swap":
            params["reduceOnly"] = True
        if stop_price is not None:
            params["stopPrice"] = stop_price

        if settings.DRY_RUN:
            log.info("[DRY_RUN] would place reduce-only %s (%s) order: %s %s @ %s stop=%s",
                      order_type, kind, amount, symbol, price, stop_price)
            return {"dry_run": True, "kind": kind, "side": side, "amount": amount}

        return self.exchange.create_order(
            symbol, order_type, side, amount, price, params
        )

    def close_position(self, symbol: str):
        position = self.get_position(symbol)
        if not position:
            log.info("No open position on %s to close.", symbol)
            return None
        contracts = float(position["contracts"])
        side = "sell" if position["side"] == "long" else "buy"
        return self.place_reduce_only_order(symbol, side, abs(contracts), kind="manual_close")

    def place_stop_loss_take_profit(self, symbol: str, entry_side: str, amount: float,
                                     entry_price: float, sl_pct: float = None, tp_pct: float = None):
        """
        entry_side: the side of the entry order that was just filled ('buy' or 'sell').
        Places the opposite-side reduce-only stop/limit orders.
        """
        opposite = "sell" if entry_side == "buy" else "buy"
        results = {}

        if sl_pct:
            if entry_side == "buy":
                sl_price = entry_price * (1 - sl_pct / 100.0)
            else:
                sl_price = entry_price * (1 + sl_pct / 100.0)
            sl_price = float(self.exchange.price_to_precision(symbol, sl_price))
            results["stop_loss"] = self.place_reduce_only_order(
                symbol, opposite, amount, order_type="market",
                stop_price=sl_price, kind="stop_loss"
            )

        if tp_pct:
            if entry_side == "buy":
                tp_price = entry_price * (1 + tp_pct / 100.0)
            else:
                tp_price = entry_price * (1 - tp_pct / 100.0)
            tp_price = float(self.exchange.price_to_precision(symbol, tp_price))
            results["take_profit"] = self.place_reduce_only_order(
                symbol, opposite, amount, order_type="limit",
                price=tp_price, kind="take_profit"
            )

        return results
