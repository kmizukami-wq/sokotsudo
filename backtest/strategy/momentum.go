package strategy

import (
	"math"
)

// MomentumStrategy implements a momentum-based trading logic
type MomentumStrategy struct {
	// Parameters
	MomentumPeriod  int
	EntryThreshold  float64 // Percentage change to trigger buy (e.g., 0.05 for 5%)
	ExitThreshold   float64 // Percentage change to trigger sell (e.g., -0.02 for -2%)
	ATRPeriod       int
	ATRMultiplier   float64

	// State
	Position          int // 0: No position, 1: Long
	EntryPrice        float64
	TrailingStopPrice float64
}

// NewMomentumStrategy creates a new strategy instance with default parameters
func NewMomentumStrategy() *MomentumStrategy {
	return &MomentumStrategy{
		MomentumPeriod:  20,
		EntryThreshold:  0.05, // 5% price increase over MomentumPeriod
		ExitThreshold:   -0.02, // 2% price decrease from peak after entry
		ATRPeriod:       14,
		ATRMultiplier:   2.0,
		Position:        0,
	}
}

// CalculateMomentum calculates the momentum (Rate of Change) for a given period
// It requires historical close prices.
func CalculateMomentum(closes []float64, period int) float64 {
	if len(closes) < period {
		return 0.0 // Not enough data
	}
	currentClose := closes[len(closes)-1]
	prevClose := closes[len(closes)-period]
	if prevClose == 0 {
		return 0.0 // Avoid division by zero
	}
	return (currentClose - prevClose) / prevClose
}

// GenerateSignal processes a new candle and returns a trading signal for Momentum Strategy
// This simplified version assumes historical closes are available for momentum calculation.
func (s *MomentumStrategy) GenerateSignal(current OHLCV, history []OHLCV, currentATR float64) Signal {
	signal := SignalHold

	// Extract close prices for momentum calculation
	closes := make([]float64, len(history))
	for i, ohlcv := range history {
		closes[i] = ohlcv.Close
	}

	// Add current close to history for momentum calculation
	closes = append(closes, current.Close)

	// Calculate momentum
	momentum := CalculateMomentum(closes, s.MomentumPeriod)

	// 1. No Position (Entry Logic)
	if s.Position == 0 {
		// Entry Condition: Momentum is above threshold
		if momentum > s.EntryThreshold {
			signal = SignalBuy
			s.Position = 1
			s.EntryPrice = current.Close
			// Initialize trailing stop based on ATR
			s.TrailingStopPrice = s.EntryPrice - (currentATR * s.ATRMultiplier)
		}
	} else if s.Position == 1 {
		// 2. In Position (Exit Logic)

		// Update trailing stop (always move up, never down)
		currentStop := current.Close - (currentATR * s.ATRMultiplier)
		s.TrailingStopPrice = math.Max(s.TrailingStopPrice, currentStop)

		// Exit Condition 1: Trailing stop hit
		if current.Low <= s.TrailingStopPrice {
			signal = SignalSell
			s.Position = 0
		} else if momentum < s.ExitThreshold {
			// Exit Condition 2: Momentum reverses or weakens significantly
			signal = SignalSell
			s.Position = 0
		}
	}

	return signal
}
