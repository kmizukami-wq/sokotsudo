package engine

import (
	"math"

	"github.com/sokotsudo/backtest/strategy"
)

// ComputeMetrics calculates performance metrics from trades and equity curve.
func ComputeMetrics(trades []strategy.Trade, equityCurve []float64, initialCap float64) strategy.PerformanceMetrics {
	m := strategy.PerformanceMetrics{
		TotalTrades: len(trades),
		FinalEquity: initialCap,
	}

	if len(equityCurve) > 0 {
		m.FinalEquity = equityCurve[len(equityCurve)-1]
	}

	for _, t := range trades {
		if t.PnL > 0 {
			m.WinningTrades++
		} else {
			m.LosingTrades++
		}
	}

	if m.TotalTrades > 0 {
		m.WinRate = float64(m.WinningTrades) / float64(m.TotalTrades) * 100
	}

	m.TotalReturn = (m.FinalEquity - initialCap) / initialCap * 100
	m.MaxDrawdown = calcMaxDrawdown(equityCurve)
	m.SharpeRatio = calcSharpe(equityCurve)

	return m
}

func calcMaxDrawdown(equity []float64) float64 {
	if len(equity) < 2 {
		return 0
	}
	peak := equity[0]
	maxDD := 0.0
	for _, e := range equity {
		if e > peak {
			peak = e
		}
		dd := (peak - e) / peak
		if dd > maxDD {
			maxDD = dd
		}
	}
	return maxDD * 100
}

func calcSharpe(equity []float64) float64 {
	if len(equity) < 2 {
		return 0
	}
	returns := make([]float64, len(equity)-1)
	for i := 1; i < len(equity); i++ {
		if equity[i-1] != 0 {
			returns[i-1] = (equity[i] - equity[i-1]) / equity[i-1]
		}
	}

	avg := mean(returns)
	sd := stddev(returns)
	if sd == 0 {
		return 0
	}
	return (avg / sd) * math.Sqrt(252)
}

func mean(xs []float64) float64 {
	if len(xs) == 0 {
		return 0
	}
	sum := 0.0
	for _, x := range xs {
		sum += x
	}
	return sum / float64(len(xs))
}

func stddev(xs []float64) float64 {
	if len(xs) == 0 {
		return 0
	}
	avg := mean(xs)
	sum := 0.0
	for _, x := range xs {
		d := x - avg
		sum += d * d
	}
	return math.Sqrt(sum / float64(len(xs)))
}
