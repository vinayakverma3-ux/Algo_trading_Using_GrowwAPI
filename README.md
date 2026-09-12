# Groww Algo Trading

Momentum investing and intraday strategy research on the Groww Trading API.

Two independent things live here:

| | Status | What it is |
|---|---|---|
| **Cross-sectional momentum** | live, real money | Monthly/quarterly rebalance into the top-ranked stocks by trailing return |
| **Intraday bots** | paper only | Three strategies (ORB, VWAP reversion, SMA cross) that failed backtesting and run as a control |

Read [METHODOLOGY.md](METHODOLOGY.md) before trusting any backtest number here.

> **Not investment advice.** This is a personal research project, published
> because the testing method may be useful to others — not because the results
> are worth acting on.
>
> Every backtest figure here is **optimistic**. The universes are built from
> *current* index constituents, so companies that failed out of the index are
> missing; a partial correction cut mid-cap momentum returns by several points
> and 14 delisted companies could not be recovered at all. Results also vary
> by several percentage points depending on which month you start rebalancing.
>
> Three of the four strategies here **failed** their own validation and are
> kept as controls. Indian markets carry 20% short-term capital gains tax,
> which alone reduced one strategy's backtested CAGR from 25.5% to 21.2%.
> SEBI found that **over 70% of individual intraday traders lose money**.
>
> If you use any of this, test it yourself and risk only what you can lose.

## Setup

```bash
python3.13 -m venv .venv                # 3.10+ required by the MCP SDK
.venv/bin/pip install -r requirements.txt
cp .env.example .env                    # add your Groww API key and secret
```

Groww credentials come from Profile -> Trading APIs. Order placement additionally
requires the originating IP to be whitelisted (SEBI rule); `groww_client.py`
forces IPv4 so the address Groww sees matches what you registered.

## Momentum (the live strategy)

```bash
./rebalance.sh                  # show the plan, place nothing
./rebalance.sh --execute        # place real orders, asks for confirmation
.venv/bin/python -m momentum.status     # current holdings and P&L
```

Rules: rank the universe by return over the trailing 12 months ending 1 month
ago, hold the top 15 equal-weighted, cap at 4 per sector and 2 per promoter
group, rebalance on schedule. No stop-loss and no profit target — a holding is
sold only when it drops out of the ranking at a rebalance.

## Intraday paper bots

```bash
./start_trading.sh              # all three, plus watchdog
.venv/bin/python compare.py     # side-by-side results
./stop_trading.sh
```

Each strategy runs as an isolated instance with its own cash, positions and
trade log. Telegram alerts on every fill (`setup_telegram.py` to configure).

## Research tools

```bash
.venv/bin/python backtest.py --strategy vwap --days 60
.venv/bin/python -m momentum.backtest_tax        # momentum after capital gains
.venv/bin/python screener.py                     # which stocks move enough intraday
.venv/bin/python levels.py                       # position sizing and stops
```

## Layout

```
bot/           engine, risk manager, brokers, market data, alerts
strategies/    intraday rules and the live adapter
momentum/      universes, backtests, tax model, live rebalancer
groww_mcp.py   MCP server exposing the account to Claude Code
```

## Operational notes

- Groww approval-flow sessions **expire periodically**; `start_trading.sh`
  checks auth and fails fast rather than starting broken bots.
- Candle history is cached per bar to stay under Groww's rate limit.
- Groww returns pre-open and post-close candles; `bot/data.py` filters them out
  because they silently corrupt backtests.
- A laptop is a poor host for unattended bots. `caffeinate` cannot defeat a
  closed lid on battery.

## Licence

[MIT](LICENSE) — with an additional notice on financial risk. The software is
provided without warranty, and you are responsible for any trades it places.
