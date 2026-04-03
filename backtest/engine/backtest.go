package engine

import (
	"github.com/sokotsudo/backtest/strategy"
)

// BacktestEngine runs a backtest simulation.
type BacktestEngine struct {
	Data       []strategy.OHLCV
	Strategy   *strategy.MomentumStrategy
	InitialCap float64
}

// NewBacktestEngine creates a new backtest engine.
func NewBacktestEngine(data []strategy.OHLCV, strat *strategy.MomentumStrategy, initialCap float64) *BacktestEngine {
	return &BacktestEngine{
		Data:       data,
		Strategy:   strat,
		InitialCap: initialCap,
	}
}

// Run executes the backtest and returns trades and performance metrics.
func (e *BacktestEngine) Run() ([]strategy.Trade, strategy.PerformanceMetrics) {
	data := e.Data
	strat := e.Strategy
	n := len(data)

	// Calculate ATR for the entire dataset
	atr := CalculateATR(data, strat.ATRPeriod)

	// Determine lookback: need enough bars for both momentum and ATR
	lookback := strat.MomentumPeriod
	if strat.ATRPeriod+1 > lookback {
		lookback = strat.ATRPeriod + 1
	}

	if n <= lookback {
		return nil, strategy.PerformanceMetrics{FinalEquity: e.InitialCap}
	}

	equity := e.InitialCap
	var trades []strategy.Trade
	var equityCurve []float64

	var entryPrice float64
	var entryTime = data[0].Time
	var shares float64

	for i := lookback; i < n; i++ {
		current := data[i]
		history := data[:i]

		signal := strat.GenerateSignal(current, history, atr[i])

		switch signal {
		case strategy.SignalBuy:
			entryPrice = current.Close
			entryTime = current.Time
			shares = equity / entryPrice

		case strategy.SignalSell:
			if entryPrice > 0 {
				exitPrice := current.Close
				pnl := (exitPrice - entryPrice) * shares
				pnlPct := (exitPrice - entryPrice) / entryPrice * 100
				equity += pnl

				trades = append(trades, strategy.Trade{
					EntryTime:  entryTime,
					ExitTime:   current.Time,
					EntryPrice: entryPrice,
					ExitPrice:  exitPrice,
					PnL:        pnl,
					PnLPercent: pnlPct,
				})
				entryPrice = 0
				shares = 0
			}
		}

		// Track equity: if in position, mark-to-market
		if shares > 0 {
			equityCurve = append(equityCurve, (equity-entryPrice*shares)+current.Close*shares)
		} else {
			equityCurve = append(equityCurve, equity)
		}
	}

	// Force close if still in position at end of data
	if strat.Position == 1 && shares > 0 {
		lastBar := data[n-1]
		exitPrice := lastBar.Close
		pnl := (exitPrice - entryPrice) * shares
		pnlPct := (exitPrice - entryPrice) / entryPrice * 100
		equity += pnl
		trades = append(trades, strategy.Trade{
			EntryTime:  entryTime,
			ExitTime:   lastBar.Time,
			EntryPrice: entryPrice,
			ExitPrice:  exitPrice,
			PnL:        pnl,
			PnLPercent: pnlPct,
		})
		strat.Position = 0
		// Update last equity point
		if len(equityCurve) > 0 {
			equityCurve[len(equityCurve)-1] = equity
		}
	}

	metrics := ComputeMetrics(trades, equityCurve, e.InitialCap)
	return trades, metrics
}
