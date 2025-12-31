"""
Momentum Strategy 6M - Solution with CustomData reading LEAN format
===================================================================
Cross-Sectional Momentum Strategy with 6-month (126 days) lookback
Uses CustomData to read from converted LEAN ZIP files
"""
from AlgorithmImports import *
from datetime import timedelta
import pickle
import pandas as pd
from pathlib import Path
import zipfile
import io

class LeanEquityData(PythonData):
    """Custom data class that reads from LEAN format ZIP files"""
    
    def get_source(self, config, date, is_live_mode):
        """Return the source - LEAN format ZIP file"""
        # Try both local and Docker paths
        local_data_dir = Path('/Users/kacper/Desktop/Lean/Data')
        docker_data_dir = Path('/Lean/Data')
        
        data_dir = local_data_dir if local_data_dir.exists() else docker_data_dir
        
        symbol = config.symbol.value.lower()
        zip_file = data_dir / 'equity' / 'usa' / 'daily' / symbol / f"{symbol}.zip"
        
        if zip_file.exists():
            return SubscriptionDataSource(str(zip_file), SubscriptionTransportMedium.LOCAL_FILE)
        else:
            return SubscriptionDataSource("", SubscriptionTransportMedium.LOCAL_FILE)
    
    def reader(self, config, line, date, is_live_mode):
        """Read a line from the CSV file inside ZIP"""
        if not line or line.strip() == "":
            return None
        
        try:
            csv = line.split(',')
            if len(csv) < 6:
                return None
            
            # Parse LEAN format: YYYYMMDD HH:MM,Open,High,Low,Close,Volume
            time_str = csv[0].strip()
            open_price = float(csv[1])
            high_price = float(csv[2])
            low_price = float(csv[3])
            close_price = float(csv[4])
            volume = int(csv[5])
            
            # Parse time
            date_part = time_str.split()[0]
            time_obj = datetime.strptime(date_part, '%Y%m%d')
            
            # Create TradeBar-like data
            data = LeanEquityData()
            data.symbol = config.symbol
            data.time = time_obj
            data.end_time = time_obj + timedelta(days=1)
            data.value = close_price  # Set Value property - this is critical!
            data.open = open_price
            data.high = high_price
            data.low = low_price
            data.close = close_price
            data.volume = volume
            data.period = timedelta(days=1)
            
            return data
        except Exception as e:
            return None


class Momentum6MSolutionAlgorithm(QCAlgorithm):
    """Momentum Strategy with 6-month (126 days) lookback - solution version"""
    
    def initialize(self):
        """Initialize with 6M parameters"""
        # Backtest period
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 31)
        self.set_cash(5000)
        
        # Initialize orders list
        self.all_orders = []
        
        # Strategy parameters
        self.lookback_days = 126  # 6 months
        self.n_long = 5
        self.n_short = 5
        
        # Data directory for .pkl files (for momentum calculation)
        local_path = Path('/Users/kacper/Desktop/X_Quant/x_quant/data/data_ibkr1h')
        docker_path = Path('/X_Quant/x_quant/data/data_ibkr1h')
        self.data_dir = local_path if local_path.exists() else docker_path
        
        # Load available symbols from .pkl files for momentum calculation
        self.symbols_data = self.load_symbols_data()
        
        # Add symbols using CustomData (reads from LEAN ZIP files)
        self.symbols = {}
        for symbol_str in list(self.symbols_data.keys())[:50]:  # Limit to 50 for performance
            try:
                symbol = self.add_data(LeanEquityData, symbol_str, Resolution.DAILY).symbol
                self.symbols[symbol_str] = symbol
            except:
                continue
        
        # Momentum scores
        self.momentum_scores = {}
        
        # Schedule rebalancing
        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open("SPY", 30),
            self.rebalance
        )
        
        # Add SPY as benchmark
        try:
            spy = self.add_equity("SPY", Resolution.DAILY).symbol
            self.set_benchmark(spy)  # Set SPY as benchmark for Alpha/Beta calculations
        except:
            pass
        
        self.log("=" * 60)
        self.log("MOMENTUM 6M STRATEGY INITIALIZED (Solution Version)")
        self.log(f"Lookback: {self.lookback_days} days (6 months)")
        self.log(f"Long: {self.n_long} | Short: {self.n_short}")
        self.log(f"Loaded {len(self.symbols_data)} symbols from .pkl files")
        self.log(f"Tracking {len(self.symbols)} symbols with CustomData")
        self.log("=" * 60)
    
    def load_symbols_data(self):
        """Load price data from .pkl files for momentum calculation"""
        symbols_data = {}
        
        if not self.data_dir.exists():
            self.log(f"ERROR: Data directory not found: {self.data_dir}")
            return symbols_data
        
        # Get all .pkl files
        pkl_files = list(self.data_dir.glob('*.pkl'))
        
        for pkl_file in pkl_files[:100]:  # Limit to first 100 for performance
            try:
                # Extract symbol from filename
                symbol = pkl_file.stem.replace('_15Y_1H_IBKR', '').upper()
                
                # Skip excluded symbols
                excluded = {'TQQQ', 'SQQQ', 'TECL', 'TECS', 'SOXL', 'SOXS', 'UPRO', 'SPXU',
                           'SPXL', 'SPXS', 'TNA', 'TZA', 'UDOW', 'SDOW', 'LABU', 'LABD',
                           'NUGT', 'DUST', 'VXX', 'UVXY', 'SVXY', 'USO', 'UNG', 'GLD', 'SLV', 'SPY'}
                if symbol in excluded:
                    continue
                
                # Load pickle file
                with open(pkl_file, 'rb') as f:
                    data_dict = pickle.load(f)
                
                if 'data' not in data_dict:
                    continue
                
                df = data_dict['data'].copy()
                
                # Remove timezone if present
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                
                # Resample to daily
                daily = pd.DataFrame()
                daily['Close'] = df['Adj_Close'].resample('D').last() if 'Adj_Close' in df.columns else df['Close'].resample('D').last()
                daily = daily.dropna()
                
                # Filter to backtest period
                daily = daily[(daily.index >= pd.Timestamp('2015-01-01')) & 
                             (daily.index <= pd.Timestamp('2024-12-31'))]
                
                if len(daily) < self.lookback_days + 100:  # Need enough data
                    continue
                
                symbols_data[symbol] = daily['Close']
                
            except Exception as e:
                continue
        
        return symbols_data
    
    def calculate_momentum_scores(self):
        """Calculate momentum scores from loaded .pkl data"""
        scores = {}
        current_date = pd.Timestamp(self.time)
        
        for symbol_str, prices in self.symbols_data.items():
            try:
                # Calculate momentum from historical data
                prices_series = prices[prices.index <= current_date]
                
                if len(prices_series) < self.lookback_days + 1:
                    continue
                
                # Get current and past prices from .pkl data
                current_price_pkl = prices_series.iloc[-1]
                past_price = prices_series.iloc[-self.lookback_days]
                
                # Calculate momentum (percentage change)
                if past_price > 0 and current_price_pkl > 0:
                    momentum = (current_price_pkl / past_price - 1) * 100
                else:
                    continue
                
                # Filter extreme values
                if abs(momentum) > 500:
                    continue
                
                scores[symbol_str] = momentum
                
            except Exception as e:
                continue
        
        return scores
    
    def rebalance(self):
        """Rebalance portfolio based on momentum"""
        if self.is_warming_up:
            return
        
        scores = self.calculate_momentum_scores()
        
        if len(scores) < (self.n_long + self.n_short):
            if self.time.day % 5 == 0:  # Log every 5 days
                self.log(f"Insufficient securities with momentum data: {len(scores)} (need {self.n_long + self.n_short})")
            return
        
        # Rank by momentum
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # Select long and short positions
        long_symbols = [x[0] for x in ranked[:self.n_long]]
        short_symbols = [x[0] for x in ranked[-self.n_short:]]
        
        # Calculate weights
        total_positions = self.n_long + self.n_short
        weight = 1.0 / total_positions
        
        # Liquidate positions not in new targets
        for holding in self.portfolio.values():
            if holding.invested and holding.symbol.value not in long_symbols + short_symbols:
                if holding.symbol.value != "SPY":
                    self.liquidate(holding.symbol)
        
        # Set target positions - use set_holdings which works with CustomData
        for symbol_str in long_symbols:
            if symbol_str in self.symbols:
                symbol = self.symbols[symbol_str]
                try:
                    # Check if we have data
                    if symbol in self.current_slice and symbol in self.securities:
                        security = self.securities[symbol]
                        if security.has_data and security.price > 0:
                            self.set_holdings(symbol, weight)
                            self.log(f"LONG: {symbol_str} (weight: {weight:.1%}, momentum: {scores[symbol_str]:+.2f}%)")
                except Exception as e:
                    self.log(f"ERROR setting LONG {symbol_str}: {e}")
        
        for symbol_str in short_symbols:
            if symbol_str in self.symbols:
                symbol = self.symbols[symbol_str]
                try:
                    # Check if we have data
                    if symbol in self.current_slice and symbol in self.securities:
                        security = self.securities[symbol]
                        if security.has_data and security.price > 0:
                            self.set_holdings(symbol, -weight)
                            self.log(f"SHORT: {symbol_str} (weight: {-weight:.1%}, momentum: {scores[symbol_str]:+.2f}%)")
                except Exception as e:
                    self.log(f"ERROR setting SHORT {symbol_str}: {e}")
        
        # Log summary
        long_val = sum(self.portfolio[self.symbols[s]].holdings_value for s in long_symbols if s in self.symbols and self.portfolio[self.symbols[s]].invested)
        short_val = sum(abs(self.portfolio[self.symbols[s]].holdings_value) for s in short_symbols if s in self.symbols and self.portfolio[self.symbols[s]].invested)
        self.log(f"REBALANCE: Long ${long_val:,.0f} | Short ${short_val:,.0f} | Total Positions: {len([s for s in long_symbols + short_symbols if s in self.symbols and self.portfolio[self.symbols[s]].invested])}")
    
    def on_order_event(self, order_event):
        """Log all order events for reporting"""
        if order_event.status == OrderStatus.FILLED:
            try:
                order = self.transactions.get_order_by_id(order_event.order_id)
                order_type = "Buy Market" if order_event.quantity > 0 else "Sell Market"
                
                # Get fill quantity - use fill_quantity if available, otherwise quantity
                fill_quantity = order_event.fill_quantity if order_event.fill_quantity != 0 else order_event.quantity
                quantity = int(fill_quantity)
                # Keep sign consistent with order direction
                if order_event.quantity < 0:
                    quantity = -abs(quantity)
                
                # Get fill price
                fill_price = float(order_event.fill_price) if order_event.fill_price > 0 else 0.0
                
                # Determine tag - "Liquidated" only for closing positions
                tag = ""
                if order and hasattr(order, 'tag') and order.tag:
                    tag = order.tag
                else:
                    # Check if we're closing a position
                    holding = self.portfolio.get(order_event.symbol)
                    if holding:
                        # If we had a position and now we're reducing it, it's liquidation
                        if holding.quantity != 0:
                            if (holding.quantity > 0 and fill_quantity < 0) or (holding.quantity < 0 and fill_quantity > 0):
                                tag = "Liquidated"
                
                # Store order for reporting
                if not hasattr(self, 'all_orders'):
                    self.all_orders = []
                self.all_orders.append({
                    'date': order_event.utc_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'symbol': order_event.symbol.value,
                    'type': order_type,
                    'price': fill_price,
                    'quantity': quantity,
                    'status': 'Filled',
                    'tag': tag
                })
                
                # Log to console with full details
                self.log(f"ORDER FILLED: {order_event.utc_time.strftime('%Y-%m-%d %H:%M:%S')} | {order_event.symbol.value} | {order_type} | Fill: ${fill_price:.2f} USD | Qty: {quantity} | Tag: {tag}")
            except Exception as e:
                self.log(f"ERROR in on_order_event: {e}")
                import traceback
                self.log(f"Traceback: {traceback.format_exc()}")
    
    def on_end_of_algorithm(self):
        """Final summary"""
        final_equity = self.portfolio.total_portfolio_value
        total_return = (final_equity - 5000) / 5000
        
        # Log all orders summary
        if hasattr(self, 'all_orders') and self.all_orders:
            self.log("=" * 60)
            self.log(f"TOTAL ORDERS EXECUTED: {len(self.all_orders)}")
            self.log("=" * 60)
        
        self.log("=" * 60)
        self.log("ALGORITHM COMPLETE")
        self.log(f"Starting Equity: $5,000")
        self.log(f"Final Portfolio Value: ${final_equity:,.0f}")
        self.log(f"Total Return: {total_return:+.2%}")
        self.log("=" * 60)

