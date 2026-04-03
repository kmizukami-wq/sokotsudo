package strategy

import "time"

// OHLCV represents a single candlestick bar.
type OHLCV struct {
	Open   float64
	High   float64
	Low    float64
	Close  float64
	Volume float64
	Time   time.Time
}

// Signal represents a trading signal.
type Signal int

const (
	SignalHold Signal = iota
	SignalBuy
	SignalSell
)

// Trade represents a completed round-trip trade.
type Trade struct {
	EntryTime  time.Time
	ExitTime   time.Time
	EntryPrice float64
	ExitPrice  float64
	PnL        float64
	PnLPercent float64
}

// PerformanceMetrics holds backtest performance results.
type PerformanceMetrics struct {
	TotalTrades   int
	WinningTrades int
	LosingTrades  int
	WinRate       float64
	TotalReturn   float64
	MaxDrawdown   float64
	SharpeRatio   float64
	FinalEquity   float64
}
