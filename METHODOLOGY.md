# How strategies were tested

The method matters more than any individual result. Most strategies that look
profitable in a first backtest do not survive these checks — that is the point
of running them.

## The tests, in order of how much they matter

### 1. Split-sample
Split the period in half. A real edge shows up in both halves. Every intraday
strategy tested here **flipped sign** between halves:

| Strategy | First half | Second half |
|---|---|---|
| ORB | +Rs 10,697 | -Rs 8,291 |
| VWAP | -Rs 21,354 | +Rs 3,123 |
| SMA | -Rs 2,459 | +Rs 4,607 |

That is what no edge looks like. Cross-sectional momentum, by contrast, held
up in both halves.

### 2. Offset sensitivity
For anything that rebalances every N months, there are N possible schedules
(start in month 0, 1, ... N-1). Run all of them. If results swing widely, you
picked a lucky calendar rather than found an effect.

Quarterly momentum: 27.13% / 24.00% / 23.58% depending on start month. The
honest number is the mean (~25%), not the best (27.13%).

### 3. Compare against the right benchmark
Comparing a 15-stock equal-weight portfolio to the cap-weighted NIFTY 50
conflates three things: the signal, equal weighting, and universe choice.

The correct control is **random selection from the same universe**:

| Benchmark | CAGR |
|---|---|
| NIFTY 50 (cap-weighted) | 11.16% |
| Equal-weight all ~103 stocks | 21.99% |
| Random 15 stocks (200 trials) | 21.60% |
| Momentum 12-1 top-15 | 28.60% |

Half the apparent "momentum edge" was never momentum. The real edge is
momentum minus random-from-same-universe: about +7%.

### 4. Survivorship bias
A universe built from *today's* index members excludes everything that failed
out of it. NIFTY Midcap 100 turns over ~20% a year, so over a decade the
survivor list bears little resemblance to the real one.

NSE publishes membership changes at
`https://archives.nseindia.com/content/indices/IndexInclExcl.xls` (data through
July 2020). Excluded names from that file include DHFL, Jaiprakash Associates,
Lanco Infratech, Punj Lloyd, Educomp, Unitech, Reliance Communications and
Bhushan Steel — none of which appear in the current constituent list.

Adding 33 of them back cut mid-cap momentum CAGR from 32.45% to 30.91%, and
the 2024+ figure from 36.27% to 29.07%. **14 more had no price data at all**
(delisted or wound up), so even the corrected number remains optimistic.

### 5. Costs and tax
Backtests that ignore these are fiction.

- Intraday round trip on Rs 2L: **Rs 118** (0.059%)
- Delivery round trip: **0.476%** including DP charges
- STCG 20% + 4% cess; LTCG 12.5% above Rs 1.25 lakh/year

Tax alone cut monthly momentum from 25.49% to **21.20%** CAGR over 12.5 years
(Rs 5.16 lakh paid; Rs 12.3 lakh lost to lost compounding).

### 6. Parameter sensitivity
Sweep lookback, holding count, rebalance frequency. A real effect shows a broad
plateau; an artifact shows a single peak. Momentum held 24-29% across a 4x
parameter range.

## Recurring findings

**Trading less won every time.** Monthly < quarterly < half-yearly for momentum.
Intraday: the strategy that traded most (VWAP, 3.7/day) lost the most to costs;
the one that barely traded lost least.

**Costs dominate at short horizons.** 0.059% per round trip is 6% of a 1% target
but 0.7% of an 8% monthly move. This single fact rules intraday out and
multi-week horizons in.

**A small profit target is not conservative.** A 1% target with a
volatility-appropriate stop gives R:R around 0.44, needing a **69% win rate** to
break even. Measured win rates were 35-50%.

**Beware finding a variant by searching.** Testing six configurations and
reporting the best is how false results are manufactured. If a result only
appears at one setting, it is not real.

## Reproducing any of it

```bash
.venv/bin/python backtest.py --strategy vwap --days 60      # intraday
.venv/bin/python -m momentum.backtest                       # momentum, pre-tax
.venv/bin/python -m momentum.backtest_tax                   # with capital gains
.venv/bin/python screener.py                                # intraday feasibility
.venv/bin/python levels.py                                  # sizing and stops
```
