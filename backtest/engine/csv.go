package engine

import (
	"encoding/csv"
	"fmt"
	"os"
	"strconv"
	"time"

	"github.com/sokotsudo/backtest/strategy"
)

// LoadCSV loads OHLCV data from a CSV file.
// Expected format: Date,Open,High,Low,Close,Volume (with header row).
func LoadCSV(filepath string) ([]strategy.OHLCV, error) {
	f, err := os.Open(filepath)
	if err != nil {
		return nil, fmt.Errorf("open csv: %w", err)
	}
	defer f.Close()

	reader := csv.NewReader(f)
	records, err := reader.ReadAll()
	if err != nil {
		return nil, fmt.Errorf("read csv: %w", err)
	}

	if len(records) < 2 {
		return nil, fmt.Errorf("csv has no data rows")
	}

	var data []strategy.OHLCV
	for i, row := range records[1:] { // skip header
		lineNum := i + 2
		if len(row) < 6 {
			return nil, fmt.Errorf("line %d: expected 6 columns, got %d", lineNum, len(row))
		}

		t, err := time.Parse("2006-01-02", row[0])
		if err != nil {
			return nil, fmt.Errorf("line %d: parse date %q: %w", lineNum, row[0], err)
		}

		open, err := strconv.ParseFloat(row[1], 64)
		if err != nil {
			return nil, fmt.Errorf("line %d: parse open: %w", lineNum, err)
		}
		high, err := strconv.ParseFloat(row[2], 64)
		if err != nil {
			return nil, fmt.Errorf("line %d: parse high: %w", lineNum, err)
		}
		low, err := strconv.ParseFloat(row[3], 64)
		if err != nil {
			return nil, fmt.Errorf("line %d: parse low: %w", lineNum, err)
		}
		close_, err := strconv.ParseFloat(row[4], 64)
		if err != nil {
			return nil, fmt.Errorf("line %d: parse close: %w", lineNum, err)
		}
		vol, err := strconv.ParseFloat(row[5], 64)
		if err != nil {
			return nil, fmt.Errorf("line %d: parse volume: %w", lineNum, err)
		}

		data = append(data, strategy.OHLCV{
			Time:   t,
			Open:   open,
			High:   high,
			Low:    low,
			Close:  close_,
			Volume: vol,
		})
	}

	return data, nil
}
