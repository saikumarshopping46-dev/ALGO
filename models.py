from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator


ActionType = Literal["buy", "sell", "close_long", "close_short", "close_all"]


class TradingViewAlert(BaseModel):
    """
    Shape of the JSON body your TradingView alert should send.

    Example "Message" field on a TradingView alert:

    {
      "passphrase": "{{strategy.order.comment}}",   <-- or hardcode your secret
      "action": "buy",
      "symbol": "BTC/USDT:USDT",
      "order_type": "market",
      "quantity_pct": 10,
      "leverage": 5,
      "stop_loss_pct": 2,
      "take_profit_pct": 4
    }
    """

    passphrase: str
    action: ActionType
    symbol: str = Field(..., description="ccxt unified symbol, e.g. BTC/USDT:USDT for swap, BTC/USDT for spot")
    order_type: Literal["market", "limit"] = "market"
    limit_price: Optional[float] = None

    # position sizing: % of available quote-currency balance to commit
    quantity_pct: float = Field(10.0, gt=0, le=100)

    leverage: Optional[int] = None
    stop_loss_pct: Optional[float] = Field(None, gt=0, description="e.g. 2 = 2% away from entry")
    take_profit_pct: Optional[float] = Field(None, gt=0)

    @field_validator("limit_price")
    @classmethod
    def limit_price_required_for_limit_orders(cls, v, info):
        if info.data.get("order_type") == "limit" and v is None:
            raise ValueError("limit_price is required when order_type is 'limit'")
        return v
