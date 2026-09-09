#!/usr/bin/env python3
"""Convert parquet OHLC data to strategy_compiler JSON format.

Usage:
    python convert_to_json.py input.parquet --out bars.json --instrument EURUSD
"""
import argparse
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import pyarrow.parquet as pq


def resample_ohlc(df, target_tf):
    """Resample OHLC data to a target timeframe.
    
    Args:
        df: DataFrame with index=close_time, columns=[open, high, low, close]
        target_tf: pandas frequency string ('5T', '1H', '1D', '1W', etc.)
    
    Returns:
        DataFrame with resampled OHLC
    """
    resampled = df.resample(target_tf).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last'
    }).dropna()
    
    resampled['open_time'] = resampled.index - pd.Timedelta(target_tf)
    resampled = resampled.reset_index()
    resampled = resampled.rename(columns={'close_time': 'close_time_renamed'})
    resampled['close_time'] = resampled['close_time_renamed']
    resampled = resampled.drop(columns=['close_time_renamed'])
    
    return resampled


def convert_parquet_to_json(input_path, output_path, instrument="EURUSD"):
    """Convert parquet OHLC to strategy_compiler JSON format.
    
    Expected parquet columns: timestamp, open, high, low, close
    Assumes timestamp is UTC.
    """
    print(f"Reading {input_path}...")
    df = pd.read_parquet(input_path)
    
    # Rename timestamp to close_time and ensure it's timezone-aware UTC
    if 'timestamp' in df.columns:
        df = df.rename(columns={'timestamp': 'close_time'})
    
    df['close_time'] = pd.to_datetime(df['close_time'])
    
    # If naive, localize to UTC; if already aware, convert to UTC
    if df['close_time'].dt.tz is None:
        df['close_time'] = df['close_time'].dt.tz_localize('UTC')
    else:
        df['close_time'] = df['close_time'].dt.tz_convert('UTC')
    
    # Sort by close_time
    df = df.sort_values('close_time').reset_index(drop=True)
    
    # Verify required columns
    required = ['close_time', 'open', 'high', 'low', 'close']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    
    # Set close_time as index for resampling
    df = df.set_index('close_time')[['open', 'high', 'low', 'close']]
    
    # Define timeframes: tf_name -> (pandas_freq, description)
    timeframes = {
        '1m': ('1T', '1 minute'),
        '3m': ('3T', '3 minutes'),
        '5m': ('5T', '5 minutes'),
        '15m': ('15T', '15 minutes'),
        '30m': ('30T', '30 minutes'),
        '1h': ('1H', '1 hour'),
        '4h': ('4H', '4 hours'),
        '1d': ('1D', '1 day'),
        '1w': ('1W', '1 week'),
    }
    
    series = {}
    
    for tf_name, (pandas_freq, desc) in timeframes.items():
        print(f"Resampling to {tf_name} ({desc})...")
        try:
            resampled = resample_ohlc(df, pandas_freq)
            
            # Convert to JSON-friendly format
            bars = []
            for _, row in resampled.iterrows():
                bars.append({
                    "open_time": row['open_time'].isoformat(),
                    "close_time": row['close_time'].isoformat(),
                    "open": float(row['open']),
                    "high": float(row['high']),
                    "low": float(row['low']),
                    "close": float(row['close'])
                })
            
            series[tf_name] = bars
            print(f"  ✓ {tf_name}: {len(bars)} bars")
        except Exception as e:
            print(f"  ✗ {tf_name}: {e}")
            raise
    
    # Build output payload
    payload = {
        "instrument": instrument,
        "series": series
    }
    
    # Write JSON
    print(f"\nWriting {output_path}...")
    with open(output_path, 'w') as fh:
        json.dump(payload, fh, indent=2)
    
    # Print summary
    total_bars = sum(len(bars) for bars in series.values())
    print(f"\n✓ Conversion complete")
    print(f"  Instrument: {instrument}")
    print(f"  Total bars across all timeframes: {total_bars}")
    print(f"  Timeframes: {', '.join(series.keys())}")
    for tf_name, bars in series.items():
        print(f"    {tf_name}: {len(bars)} bars")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Convert parquet OHLC to strategy_compiler JSON format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python convert_to_json.py data.parquet --out bars.json
  python convert_to_json.py eurusd.parquet --out eurusd_bars.json --instrument EURUSD
        """
    )
    ap.add_argument("input", help="input parquet file (columns: timestamp, open, high, low, close)")
    ap.add_argument("--out", required=True, help="output JSON file")
    ap.add_argument("--instrument", default="EURUSD", help="instrument name (default: EURUSD)")
    
    args = ap.parse_args()
    
    convert_parquet_to_json(args.input, args.out, args.instrument)