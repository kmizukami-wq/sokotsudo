package engine

import (
	"math"

	"github.com/sokotsudo/backtest/strategy"
)

// CalculateATR computes the Average True Range using Wilder's smoothing.
// Returns a slice the same length as data. The first `period` entries are 0.0.
func CalculateATR(data []strategy.OHLCV, period int) []float64 {
	n := len(data)
	atr := make([]float64, n)
	if n < period+1 {
		return atr
	}

	// Calculate True Range for each bar (starting from index 1)
	tr := make([]float64, n)
	for i := 1; i < n; i++ {
		highLow := data[i].High - data[i].Low
		highPrevClose := math.Abs(data[i].High - data[i-1].Close)
		lowPrevClose := math.Abs(data[i].Low - data[i-1].Close)
		tr[i] = math.Max(highLow, math.Max(highPrevClose, lowPrevClose))
	}

	// Initial ATR is the simple average of the first `period` true ranges
	sum := 0.0
	for i := 1; i <= period; i++ {
		sum += tr[i]
	}
	atr[period] = sum / float64(period)

	// Wilder's smoothing for subsequent values
	for i := period + 1; i < n; i++ {
		atr[i] = (atr[i-1]*float64(period-1) + tr[i]) / float64(period)
	}

	return atr
}
