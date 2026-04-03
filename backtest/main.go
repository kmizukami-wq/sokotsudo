package main

import (
	"fmt"
	"os"

	"github.com/sokotsudo/backtest/engine"
	"github.com/sokotsudo/backtest/strategy"
)

func main() {
	csvPath := "testdata/sample.csv"
	if len(os.Args) > 1 {
		csvPath = os.Args[1]
	}

	// Load data
	data, err := engine.LoadCSV(csvPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error loading data: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("Loaded %d bars from %s\n\n", len(data), csvPath)

	// Create strategy with default parameters
	strat := strategy.NewMomentumStrategy()

	// Run backtest
	initialCap := 100000.0
	eng := engine.NewBacktestEngine(data, strat, initialCap)
	trades, metrics := eng.Run()

	// Print results
	fmt.Println("=== Backtest Results ===")
	fmt.Printf("Period:           %s ~ %s\n", data[0].Time.Format("2006-01-02"), data[len(data)-1].Time.Format("2006-01-02"))
	fmt.Printf("Initial Capital:  $%.2f\n", initialCap)
	fmt.Printf("Final Equity:     $%.2f\n", metrics.FinalEquity)
	fmt.Println()
	fmt.Printf("Total Trades:     %d\n", metrics.TotalTrades)
	fmt.Printf("Winning Trades:   %d\n", metrics.WinningTrades)
	fmt.Printf("Losing Trades:    %d\n", metrics.LosingTrades)
	fmt.Printf("Win Rate:         %.2f%%\n", metrics.WinRate)
	fmt.Println()
	fmt.Printf("Total Return:     %.2f%%\n", metrics.TotalReturn)
	fmt.Printf("Max Drawdown:     %.2f%%\n", metrics.MaxDrawdown)
	fmt.Printf("Sharpe Ratio:     %.4f\n", metrics.SharpeRatio)
	fmt.Println()

	// Print strategy parameters
	fmt.Println("=== Strategy Parameters ===")
	fmt.Printf("Momentum Period:  %d\n", strat.MomentumPeriod)
	fmt.Printf("Entry Threshold:  %.2f%%\n", strat.EntryThreshold*100)
	fmt.Printf("Exit Threshold:   %.2f%%\n", strat.ExitThreshold*100)
	fmt.Printf("ATR Period:       %d\n", strat.ATRPeriod)
	fmt.Printf("ATR Multiplier:   %.1f\n", strat.ATRMultiplier)
	fmt.Println()

	// Print trade log
	if len(trades) > 0 {
		fmt.Println("=== Trade Log ===")
		fmt.Printf("%-12s %-12s %10s %10s %12s %8s\n", "Entry Date", "Exit Date", "Entry", "Exit", "PnL", "PnL%")
		fmt.Println("------------------------------------------------------------------------")
		for _, t := range trades {
			fmt.Printf("%-12s %-12s %10.2f %10.2f %12.2f %7.2f%%\n",
				t.EntryTime.Format("2006-01-02"),
				t.ExitTime.Format("2006-01-02"),
				t.EntryPrice,
				t.ExitPrice,
				t.PnL,
				t.PnLPercent,
			)
		}
	} else {
		fmt.Println("No trades generated.")
	}
}
