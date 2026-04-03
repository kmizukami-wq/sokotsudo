package strategy

import (
	"math"
	"testing"
	"time"
)

func TestCalculateMomentum(t *testing.T) {
	// period=3: compares closes[3] vs closes[3-3]=closes[0] => (110-100)/100 = 0.10
	closes := []float64{100, 102, 105, 110}
	got := CalculateMomentum(closes, 4) // len=4, period=4: closes[3] vs closes[0]
	want := 0.10                        // (110-100)/100
	if math.Abs(got-want) > 0.001 {
		t.Errorf("CalculateMomentum = %f, want %f", got, want)
	}
}

func TestCalculateMomentum_InsufficientData(t *testing.T) {
	closes := []float64{100, 102}
	got := CalculateMomentum(closes, 5)
	if got != 0.0 {
		t.Errorf("expected 0.0 for insufficient data, got %f", got)
	}
}

func TestCalculateMomentum_ZeroPrevClose(t *testing.T) {
	closes := []float64{0, 50, 100}
	got := CalculateMomentum(closes, 3)
	if got != 0.0 {
		t.Errorf("expected 0.0 for zero prev close, got %f", got)
	}
}

func TestGenerateSignal_Buy(t *testing.T) {
	strat := NewMomentumStrategy()
	strat.MomentumPeriod = 3
	strat.EntryThreshold = 0.05 // 5%

	// Build history with strong upward momentum: 100 -> 110 (10%)
	base := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	history := []OHLCV{
		{Close: 100, High: 101, Low: 99, Time: base},
		{Close: 102, High: 103, Low: 101, Time: base.AddDate(0, 0, 1)},
	}
	current := OHLCV{Close: 110, High: 111, Low: 109, Time: base.AddDate(0, 0, 2)}

	signal := strat.GenerateSignal(current, history, 2.0)
	if signal != SignalBuy {
		t.Errorf("expected SignalBuy, got %d", signal)
	}
	if strat.Position != 1 {
		t.Errorf("expected position 1, got %d", strat.Position)
	}
}

func TestGenerateSignal_Hold(t *testing.T) {
	strat := NewMomentumStrategy()
	strat.MomentumPeriod = 3
	strat.EntryThreshold = 0.05

	// Flat prices - no momentum
	base := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	history := []OHLCV{
		{Close: 100, High: 101, Low: 99, Time: base},
		{Close: 100.5, High: 101, Low: 100, Time: base.AddDate(0, 0, 1)},
	}
	current := OHLCV{Close: 101, High: 102, Low: 100, Time: base.AddDate(0, 0, 2)}

	signal := strat.GenerateSignal(current, history, 2.0)
	if signal != SignalHold {
		t.Errorf("expected SignalHold, got %d", signal)
	}
}

func TestGenerateSignal_SellOnMomentumReversal(t *testing.T) {
	strat := NewMomentumStrategy()
	strat.MomentumPeriod = 3
	strat.EntryThreshold = 0.05
	strat.ExitThreshold = -0.02

	// Simulate already in position
	strat.Position = 1
	strat.EntryPrice = 110
	strat.TrailingStopPrice = 100

	// Prices dropped: momentum reversal
	base := time.Date(2024, 1, 1, 0, 0, 0, 0, time.UTC)
	history := []OHLCV{
		{Close: 110, High: 111, Low: 109, Time: base},
		{Close: 108, High: 110, Low: 107, Time: base.AddDate(0, 0, 1)},
	}
	current := OHLCV{Close: 105, High: 108, Low: 104, Time: base.AddDate(0, 0, 2)}

	signal := strat.GenerateSignal(current, history, 2.0)
	if signal != SignalSell {
		t.Errorf("expected SignalSell, got %d", signal)
	}
}
