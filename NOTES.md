What this tells you about the path forward
The two archives together reveal what the routing system should actually do:
When market is calm and trending upward → use sharpe archive
When market is volatile or uncertain    → use calmar archive
This is the natural next step. Instead of one archive, maintain two. Detect the current market regime — is volatility high or low, is there a clear trend or not — and route between archives accordingly. The infrastructure for this already exists in the code. It's a config and routing change, not a rebuild.
The other thing worth noting — calmar reached Sharpe 1.969 in only 3000 generations compared to sharpe needing 10000 to reach 1.341. Calmar converges faster and to higher peaks because it has a cleaner objective. Worth running calmar for another 3000 generations to see how high it goes:

You're right — let me be straight with you about what's happening.

What the numbers are telling you
The training performance looks impressive — Best Sharpe climbed to 2.085, Mean Sharpe 0.433, QD-Score 25.97. But the OOS dropped from 61% to 56.7% while training kept improving. That's the classic overfit signature. The more generations you run, the better it gets at the past and the worse it gets at the future.
Compare across all your runs:
                    Run 1      Run 2      Run 3 (calmar)  Run 4 (calmar+3k)
Generations:        2000       5000           3000              6000
Mean train:        +0.125     +0.208          +0.345           +0.433
Mean test:         +0.199     +0.228          -0.046           -0.082
OOS positive:       66.7%      75.0%           61.0%            56.7%
The Sharpe archive was actually your best result. At 5000 generations it had mean test Sharpe +0.228 — actually better than training — and 75% OOS positive. That's genuinely good. Then the calmar experiment improved training numbers but hurt generalisation. And more calmar generations made it worse again.

What is actually going on
The system hit its ceiling given the current setup. Three specific things are causing the wall:
1. The genome is too small for complex market conditions. 22 parameters controlling 4 indicator types is enough to find simple patterns but not enough to adapt to fundamentally different regimes like 2015 (choppy, zero trend) versus 2017 (smooth, continuous trend). The strategies that work in one simply cannot be mutated into strategies that work in the other — they're structurally different enough that no amount of evolution bridges the gap.
2. The behavioral descriptors aren't capturing what actually matters. Right now BD1 is the genome's momentum bias and BD2 is its stop-loss width. These describe what type of strategy it is. What the archive really needs is strategies organised by what market conditions they handle — volatility level, trend strength, correlation regime. A strategy in the V4/T0 niche might be good at calm trending markets, but the system doesn't know that — it just knows it has a certain momentum bias.
3. Walk-forward failures are structural, not fixable by more generations. 2015 and 2017 require fundamentally opposite strategy characteristics. 2015 needs patience and restraint. 2017 needs continuous exposure. No single strategy type handles both. The solution isn't more evolution — it's a smarter routing mechanism that detects the current regime and switches between the two archives you've already built.

The honest assessment of where you are
Your best result — the sharpe archive at 5000 generations — is a real, working proof of concept:

75% of strategies profitable on 3.3 years of unseen data
Mean test Sharpe slightly better than training (no overfit)
Best strategy: +20.9% return, -9.7% drawdown on unseen data
Sharpe 0.482 on data the system never touched

That result is legitimate. The calmar experiments showed you something important about the tradeoffs but didn't improve on it.

What would actually make this better
There are three directions, each genuinely different:
Direction 1 — Fix the routing (biggest impact, no more training needed)
The routing strategy loses money in every test. If you could replace that -1.333 routing Sharpe with even +0.3, the overall system becomes dramatically more useful. This means implementing real regime detection — measure current 20-day rolling volatility versus its historical percentile, measure ADX trend strength, and route to the calmar archive when volatility is high and the sharpe archive when the market is trending smoothly. The code for this already exists in indicators.py.
Direction 2 — More diverse instruments
Download QQQ data and run a fresh evolution. QQQ behaves differently enough from SPY that the strategies it finds will cover market conditions SPY strategies miss. Having two archives from different instruments that you can cross-reference is more valuable than running SPY for 20,000 generations.
Direction 3 — Accept what you have and use it
The sharpe archive at 5000 generations is a working system. Load it, run inspect_archive.py, look at the routing table, pick the top 3-5 strategies by OOS performance, and paper trade them for 6 months. Real forward testing on live data is more informative than any amount of backtesting at this point. After 6 months of paper trading you'll have genuine evidence about whether the signal is real — which is more than any test suite can give you.


The outcome of everything you built
In plain terms — you built a system that starting from zero knowledge of finance, trained on 13 years of SPY data, discovered 60 different trading strategies completely autonomously. The best of those strategies achieved +1520% return over the training period with only -11.6% maximum drawdown, and 75% of them remained profitable on 3+ years of future data the system never saw during training.
The system correctly identified that tight stop-losses and asymmetric risk management work better than momentum-chasing on large-cap US equities. It found this pattern independently — no human programmed it in.
What it can't do yet — route to the right strategy in real time, handle sudden market crashes reliably, and achieve statistical significance with the current amount of test data.

Concrete next steps in order
Step 1 — Paper trade the top 3 strategies starting now
Don't touch the code. Just observe. Look at the top 3 from your routing table:
V5/T0  Sharpe 1.341  — use this as your primary
V6/T0  Sharpe 1.312  — use this as backup
V4/T0  Sharpe 1.253  — third option
Each morning run inspect_archive.py and check what signal it gives. Record what you would have done. In 3 months you'll have real forward-test data.
Step 2 — Fix the routing fallback
The current fallback finds the nearest cell geometrically. Change it to always fall back to the best filled cell in the T0 column when confidence is low — since the entire T0 column is your strongest region. This is a 5-line change in router/live_router.py.
Step 3 — Run on QQQ
powershellpython run_evolution.py --csv data/QQQ.csv --generations 3000
QQQ data is downloaded the same way as SPY from Yahoo Finance. Compare the routing tables. Where they agree on strategy type, that's a genuinely robust signal.
Step 4 — Let time work for you
Your biggest unsolved problem is statistical significance — you need 6-8 years of out-of-sample data to prove the result rigorously. Every month that passes adds to that dataset automatically. Run test_suite.py again in 6 months with the new data and the Monte Carlo test will start showing significance.
The system is built. The foundation is solid. The next phase is observation and incremental improvement rather than fundamental rebuilding.

