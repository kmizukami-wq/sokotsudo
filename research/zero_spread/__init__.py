"""FXTF zero-spread micro mean-reversion scalping strategy.

This package implements a session-open mean-reversion scalp on 1-minute bars,
designed to exploit FXTF's zero-spread campaign hours on USD/JPY, EUR/USD,
and EUR/JPY. The structural edge — the strategy is not viable with normal
spreads — is verified via the spread-sensitivity analysis in `backtest.py`.
"""
