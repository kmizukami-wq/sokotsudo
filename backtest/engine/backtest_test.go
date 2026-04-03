package engine

import (
	"math"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/sokotsudo/backtest/strategy"
)

func TestCalculateATR(t *testing.T) {
	data := []strategy.OHLCV{
		{High: 48.70, Low: 47.79, Close: 48.16},
		{High: 48.72, Low: 48.14, Close: 48.61},
		{High: 48.90, Low: 48.39, Close: 48.75},
		{High: 48.87, Low: 48.37, Close: 48.63},
		{High: 48.82, Low: 48.24, Close: 48.74},
	}

	atr := CalculateATR(data, 3)

	// ATR should be 0 for first 3 entries
	for i := 0; i < 3; i++ {
		if atr[i] != 0 {
			t.Errorf("atr[%d] = %f, want 0", i, atr[i])
		}
	}
	// ATR[3] should be the simple average of TR[1], TR[2], TR[3]
	if atr[3] <= 0 {
		t.Errorf("atr[3] = %f, expected > 0", atr[3])
	}
	// ATR[4] should use Wilder's smoothing
	if atr[4] <= 0 {
		t.Errorf("atr[4] = %f, expected > 0", atr[4])
	}
}

func TestLoadCSV(t *testing.T) {
	content := `Date,Open,High,Low,Close,Volume
2024-01-02,100.00,102.00,99.00,101.50,1000000
2024-01-03,101.50,103.00,101.00,102.00,1100000
`
	dir := t.TempDir()
	path := filepath.Join(dir, "test.csv")
	if err := os.WriteFile(path, []byte(content), 0644); err != nil {
		t.Fatal(err)
	}

	data, err := LoadCSV(path)
	if err != nil {
		t.Fatalf("LoadCSV error: %v", err)
	}
	if len(data) != 2 {
		t.Fatalf("expected 2 rows, got %d", len(data))
	}
	if data[0].Close != 101.50 {
		t.Errorf("first close = %f, want 101.50", data[0].Close)
	}
	if data[1].Volume != 1100000 {
		t.Errorf("second volume = %f, want 1100000", data[1].Volume)
	}
}

func TestComputeMetrics_MaxDrawdown(t *testing.T) {
	equity := []float64{100, 110, 105, 115, 100, 120}
	// Peak 115, trough 100 => DD = 15/115 = 13.04%
	m := ComputeMetrics(nil, equity, 100)
	if math.Abs(m.MaxDrawdown-13.04) > 0.5 {
		t.Errorf("MaxDrawdown = %.2f, want ~13.04", m.MaxDrawdown)
	}
}

func TestComputeMetrics_WinRate(t *testing.T) {
	trades := []strategy.Trade{
		{PnL: 100},
		{PnL: -50},
		{PnL: 200},
	}
	m := ComputeMetrics(trades, []float64{100, 110}, 100)
	if math.Abs(m.WinRate-66.67) > 0.5 {
		t.Errorf("WinRate = %.2f, want ~66.67", m.WinRate)
	}
}

func TestBacktestEngine_Run(t *testing.T) {
	// Create a dataset with clear upward momentum then reversal
	base := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	var data []strategy.OHLCV

	price := 100.0
	// 30 bars of steady prices (warmup)
	for i := 0; i < 30; i++ {
		data = append(data, strategy.OHLCV{
			Time:  base.AddDate(0, 0, i),
			Open:  price,
			High:  price + 0.5,
			Low:   price - 0.5,
			Close: price + 0.1,
		})
		price += 0.1
	}
	// 25 bars of strong upward movement (should trigger buy)
	for i := 30; i < 55; i++ {
		price *= 1.005 // 0.5% per day
		data = append(data, strategy.OHLCV{
			Time:  base.AddDate(0, 0, i),
			Open:  price - 0.3,
			High:  price + 0.5,
			Low:   price - 0.5,
			Close: price,
		})
	}
	// 20 bars of sharp decline (should trigger sell)
	for i := 55; i < 75; i++ {
		price *= 0.99 // 1% drop per day
		data = append(data, strategy.OHLCV{
			Time:  base.AddDate(0, 0, i),
			Open:  price + 0.3,
			High:  price + 0.5,
			Low:   price - 1.0,
			Close: price,
		})
	}

	strat := strategy.NewMomentumStrategy()
	eng := NewBacktestEngine(data, strat, 100000)
	trades, metrics := eng.Run()

	// Should have at least 1 trade
	if len(trades) == 0 {
		t.Error("expected at least 1 trade")
	}
	// Metrics should be computed
	if metrics.FinalEquity == 0 {
		t.Error("final equity should not be 0")
	}
	t.Logf("Trades: %d, Final Equity: %.2f, Return: %.2f%%", metrics.TotalTrades, metrics.FinalEquity, metrics.TotalReturn)
}
