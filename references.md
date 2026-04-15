# QD Trading System — Bibliography & References

---

## Primary Research Paper (The Paper This Project Is Based On)

**[1] Diverse Approaches to Optimal Execution Schedule Generation**
Authors: (2026)
arXiv:2601.22113v1 — Published January 30, 2026
URL: https://arxiv.org/abs/2601.22113

> The first application of MAP-Elites to trade execution. Rather than searching for a
> single optimal policy, MAP-Elites generates a diverse portfolio of regime-specialist
> strategies indexed by liquidity and volatility conditions. Individual specialists
> achieve 8–10% performance improvements within their behavioural niches.

**How this project differs from [1]:**
- [1] applies MAP-Elites to *trade execution scheduling* (when/how to execute a large order)
- This project applies MAP-Elites to *autonomous alpha generation* — discovering entirely
  new trading strategies (MA periods, RSI thresholds, stop-losses, signal weights) that
  run on real SPY equity data across 16 years
- [1] uses a calibrated Gymnasium simulation environment
- This project backtests directly on real OHLCV market data with transaction costs
- [1] indexes strategies by liquidity and volatility of execution conditions
- This project uses intrinsic strategy properties (momentum bias, risk tolerance) as
  behavioral descriptors, making the archive independent of market data
- [1] focuses on execution of a known trade; this project discovers whether to trade at all

---

## Foundational Algorithm

**[2] Illuminating Search Spaces by Mapping Elites**
Authors: Jean-Baptiste Mouret, Jeff Clune
arXiv:1504.04909 — Published April 20, 2015
URL: https://arxiv.org/abs/1504.04909

> The original MAP-Elites paper. Introduces the Multi-dimensional Archive of Phenotypic
> Elites (MAP-Elites) algorithm. Rather than returning the single highest-performing
> solution, MAP-Elites produces a map of high-performing solutions across a space defined
> by user-chosen dimensions of variation (behavioral descriptors). 809 citations.

---

## Related Work — Quality Diversity in Finance

**[3] QuantEvolve: Automating Quantitative Strategy Discovery through Multi-Agent Evolutionary Framework**
arXiv:2510.18569 — Published October 2025
URL: https://arxiv.org/abs/2510.18569

> Applies evolutionary methods to quantitative strategy discovery. Cites MAP-Elites
> (Mouret & Clune 2015) as foundational, and AlphaEvolve as related work. Validates
> the general approach of using evolutionary algorithms for autonomous trading strategy
> search.

**[4] Generating Alpha: A Hybrid AI-Driven Trading System Integrating Technical Analysis, Machine Learning and Financial Sentiment for Regime-Adaptive Equity Strategies**
Authors: Varun Narayan Kannan Pillai et al.
arXiv:2601.19504 — Published January 27, 2026
Accepted: International Conference on Computing Systems and Intelligent Applications
(ComSIA 2026), Springer LNNS
URL: https://arxiv.org/abs/2601.19504

> Proposes a hybrid system using EMA, MACD, RSI, Bollinger Bands, FinBERT sentiment,
> XGBoost, and volatility-based regime filtering. Achieved 135.49% return over 24 months.
> Validates the use of multi-indicator signal combination with regime filtering — the same
> technical foundation used in this project's signal_generator.py.

---

## Performance Metrics

**[5] Mutual Fund Performance**
Author: William F. Sharpe
The Journal of Business, Vol. 39, No. 1, pp. 119–138 — January 1966
URL: http://www.jstor.org/stable/2351741

> Original paper introducing the reward-to-variability ratio, now universally known as
> the Sharpe Ratio: annualised excess return divided by standard deviation of returns.
> The primary fitness metric used in this project's Sharpe archive runs.

**[6] The Sharpe Ratio**
Author: William F. Sharpe
Journal of Portfolio Management, Fall 1994, pp. 49–58
URL: https://web.stanford.edu/~wfsharpe/art/sr/sr.htm

> Sharpe's own extended treatment of the ratio, generalising it beyond the original
> mutual fund context to any benchmark-relative performance measurement.

**[7] Calmar Ratio: A Smoother Tool**
Author: Terry W. Young
Futures Magazine, 1991

> Introduces the Calmar Ratio: annualised compound return divided by maximum drawdown
> over a rolling 36-month period. Named after Young's firm California Managed Accounts
> and its newsletter CMA Reports. The primary fitness metric in this project's Calmar
> archive runs. Produces more defensive strategies with lower drawdown than Sharpe-
> optimised equivalents.

---

## Technical Indicators

**[8] Technical Analysis of the Financial Markets**
Author: John J. Murphy
Publisher: New York Institute of Finance, 1999
ISBN: 0735200661

> The definitive reference for all classical technical indicators used in this project:
> Simple and Exponential Moving Averages, RSI, MACD, Bollinger Bands, ATR, and ADX.
> All implementations in strategies/indicators.py are based on the formulas defined here.

**[9] New Concepts in Technical Trading Systems**
Author: J. Welles Wilder Jr.
Publisher: Trend Research, 1978
ISBN: 0894590278

> Original introduction of RSI (Relative Strength Index), ATR (Average True Range),
> and ADX (Average Directional Index) — three of the four core indicator families
> used in this project's signal generation.

**[10] MACD — Moving Average Convergence/Divergence Trading Method**
Author: Gerald Appel
Publisher: Signalert Corporation, 1979

> Original introduction of the MACD indicator. The specific implementation in this
> project uses fast EMA, slow EMA, and a signal line smoothing period — all evolved
> as parameters in the genome.

---

## Evolutionary Computation

**[11] An Introduction to Genetic Algorithms**
Author: Melanie Mitchell
Publisher: MIT Press, 1996
ISBN: 0262631857

> Foundational reference for the mutation, crossover, and selection operators used
> in evolution/genome.py. The Gaussian mutation and uniform crossover implemented
> follow Mitchell's formulations for real-valued genetic algorithms.

---

## Walk-Forward Validation

**[12] Evidence-Based Technical Analysis**
Author: David Aronson
Publisher: Wiley, 2006
ISBN: 0470008741

> Establishes the statistical framework for walk-forward validation and Monte Carlo
> permutation testing of trading strategies. The test designs in testing/walk_forward.py
> and testing/monte_carlo.py follow the methodology described in Chapters 6 and 10.

---

## Data Source

**[13] Yahoo Finance Historical Data**
Provider: Yahoo Finance / Altaba Inc.
URL: https://finance.yahoo.com/quote/SPY/history/

> Source of all real market data used in this project. SPY (SPDR S&P 500 ETF Trust)
> daily OHLCV data from 2010-01-14 to 2026-04-10. Auto-adjusted for splits and
> dividends. 4,084 trading days.

---

## Software Dependencies

**[14] pandas: powerful Python data analysis toolkit**
Authors: Wes McKinney and the pandas development team
URL: https://pandas.pydata.org
DOI: 10.25080/Majora-92bf1922-00a

**[15] NumPy: The fundamental package for scientific computing with Python**
Authors: Charles R. Harris et al.
Nature 585, 357–362 (2020)
DOI: 10.1038/s41586-020-2649-2

**[16] yfinance: Yahoo! Finance market data downloader**
Author: Ran Aroussi
URL: https://github.com/ranaroussi/yfinance

---

## How to Cite This Project

If presenting this work, suggested citation format:

> Singhal, A. (2026). *Autonomous Alpha Generation via Quality Diversity Evolution:
> Applying MAP-Elites to Trading Strategy Discovery on Real Equity Data.*
> Unpublished project. Based on: [1] arXiv:2601.22113 and [2] arXiv:1504.04909.
> Real SPY data, 2010–2026. 10,000+ generations. Best OOS Sharpe: 0.482.
> 75% out-of-sample positive rate on 2023–2026 unseen data.

---

*Bibliography compiled April 2026.*