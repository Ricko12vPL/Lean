"""
Universe Selection Models
=========================

Custom universe selection for momentum strategy.
Filters for liquid, tradable US equities.
"""

from AlgorithmImports import *
from typing import List, Set
from datetime import datetime


class MomentumUniverseSelectionModel(FundamentalUniverseSelectionModel):
    """
    Universe Selection for Momentum Strategy

    Features:
    - Liquidity filter (dollar volume)
    - Price filter (minimum price)
    - Market cap filter
    - Sector exclusions (optional)
    - Leveraged ETF exclusions
    """

    def __init__(
        self,
        universe_size: int = 500,
        min_price: float = 5.0,
        min_dollar_volume: float = 1_000_000,
        min_market_cap: float = 500_000_000,
        exclude_sectors: List[int] = None,
        exclude_leveraged: bool = True
    ):
        """
        Initialize universe selection model

        Args:
            universe_size: Maximum number of securities in universe
            min_price: Minimum stock price (default $5)
            min_dollar_volume: Minimum daily dollar volume (default $1M)
            min_market_cap: Minimum market cap (default $500M)
            exclude_sectors: Morningstar sector codes to exclude
            exclude_leveraged: Exclude leveraged/inverse ETFs
        """
        super().__init__(True, None)

        self.universe_size = universe_size
        self.min_price = min_price
        self.min_dollar_volume = min_dollar_volume
        self.min_market_cap = min_market_cap
        self.exclude_sectors = exclude_sectors or []
        self.exclude_leveraged = exclude_leveraged

        # Leveraged/inverse ETF exclusion list
        self.excluded_symbols: Set[str] = {
            # 3x Leveraged Long
            'TQQQ', 'TECL', 'SOXL', 'UPRO', 'SPXL', 'TNA', 'UDOW', 'LABU',
            'NUGT', 'FNGU', 'BULZ', 'NAIL', 'DPST', 'DFEN', 'MIDU', 'UMDD',
            'URTY', 'FAS', 'ERX', 'CURE', 'PILL', 'RETL', 'HIBL', 'WEBL',
            'WANT', 'DUSL', 'MEXX', 'UTSL', 'DRN',

            # 3x Leveraged Short
            'SQQQ', 'TECS', 'SOXS', 'SPXU', 'SPXS', 'TZA', 'SDOW', 'LABD',
            'DUST', 'FNGD', 'BERZ', 'WEBS', 'HIBS', 'FAZ', 'ERY', 'DRIP',
            'YANG', 'EDZ', 'DRV', 'SRTY', 'MIDZ', 'SMDD',

            # 2x Leveraged
            'QLD', 'SSO', 'DDM', 'UWM', 'MVV', 'SAA', 'ROM', 'UGE', 'UYG',
            'UCC', 'USD', 'UPW', 'UXI', 'UYM', 'DIG', 'UGL', 'AGQ', 'UCO',
            'BOIL', 'UBT', 'UST', 'BIB', 'CWEB',

            # 2x Inverse
            'QID', 'SDS', 'DXD', 'TWM', 'MZZ', 'SDD', 'REW', 'SZK', 'SKF',
            'SCC', 'SDP', 'SIJ', 'SMN', 'DUG', 'GLL', 'ZSL', 'SCO', 'KOLD',
            'TBT', 'TBZ', 'PST', 'BIS',

            # 1x Inverse
            'SH', 'PSQ', 'DOG', 'RWM', 'MYY', 'SEF', 'EUM', 'EFZ',

            # Volatility Products
            'VXX', 'UVXY', 'SVXY', 'VIXY', 'VIXM', 'VXZ', 'UVIX', 'SVIX',
            'TVIX', 'ZIV', 'VXF',

            # Commodity ETFs
            'USO', 'UNG', 'GLD', 'SLV', 'CORN', 'WEAT', 'SOYB', 'DBA',
            'DBB', 'DBC', 'DBO', 'DBP', 'DBS', 'GSG', 'PDBC', 'USCI',
            'COMT', 'BCI', 'FTGC', 'COM', 'RJI', 'RJA', 'RJN', 'RJZ',
            'JJC', 'JJN', 'JJU', 'JJM', 'JJG', 'JJA', 'JJE', 'JJT',
            'UGA', 'BNO', 'OIL', 'DJP', 'GAZ', 'ONG',

            # Other excluded (ADRs, CEFs, etc. that could cause issues)
            'JNUG', 'JDST', 'GUSH', 'OILU', 'OILD', 'GASL', 'GASX',
            'YINN', 'YANG', 'INDL', 'EDC', 'LBJ', 'EURL', 'EZJ',
            'RUSL', 'RUSS', 'BRZU', 'BRAZ'
        }

    def select(self, algorithm: QCAlgorithm, fundamental: List[Fundamental]) -> List[Symbol]:
        """
        Main selection method - filters fundamental data
        
        Args:
            algorithm: Algorithm instance
            fundamental: List of fundamental data
            
        Returns:
            List of selected symbols
        """
        filtered = []
        
        for stock in fundamental:
            # Must have fundamental data
            if not stock.has_fundamental_data:
                continue
                
            # Price filter
            if stock.price < self.min_price:
                continue
                
            # Dollar volume filter
            if stock.dollar_volume < self.min_dollar_volume:
                continue
                
            # Market cap filter (if available)
            if hasattr(stock, 'market_cap') and stock.market_cap:
                if stock.market_cap < self.min_market_cap:
                    continue
                    
            # Sector exclusions
            if hasattr(stock, 'asset_classification'):
                sector = stock.asset_classification.morningstar_sector_code
                if sector in self.exclude_sectors:
                    continue
                    
            # Exclude leveraged/inverse ETFs
            if self.exclude_leveraged:
                if stock.symbol.value in self.excluded_symbols:
                    continue
                    
            filtered.append(stock)
            
        # Sort by dollar volume
        sorted_stocks = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)
        
        # Return top symbols
        selected = [x.symbol for x in sorted_stocks[:self.universe_size]]
        
        if selected:
            algorithm.log(f"MomentumUniverse: Selected {len(selected)} securities")
            
        return selected

    def select_coarse(self, algorithm: QCAlgorithm, coarse: List[Fundamental]) -> List[Symbol]:
        """
        First pass filter: liquidity and basic criteria

        Args:
            algorithm: Algorithm instance
            coarse: List of coarse fundamental data

        Returns:
            List of symbols passing coarse filter
        """
        filtered = []

        for stock in coarse:
            # Must have fundamental data for fine filter
            if not stock.has_fundamental_data:
                continue

            # Price filter
            if stock.price < self.min_price:
                continue

            # Dollar volume filter
            if stock.dollar_volume < self.min_dollar_volume:
                continue

            # Exclude leveraged/inverse ETFs
            if self.exclude_leveraged:
                if stock.symbol.value in self.excluded_symbols:
                    continue

            filtered.append(stock)

        # Sort by dollar volume (most liquid first)
        sorted_stocks = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)

        # Return symbols for fine filter
        return [x.symbol for x in sorted_stocks[:self.universe_size * 2]]

    def select_fine(self, algorithm: QCAlgorithm, fine: List[FineFundamental]) -> List[Symbol]:
        """
        Second pass filter: fundamental data

        Args:
            algorithm: Algorithm instance
            fine: List of fine fundamental data

        Returns:
            List of symbols passing fine filter
        """
        filtered = []

        for stock in fine:
            # Market cap filter
            if stock.market_cap and stock.market_cap < self.min_market_cap:
                continue

            # Sector exclusions
            sector = stock.asset_classification.morningstar_sector_code
            if sector in self.exclude_sectors:
                continue

            # Additional quality filters (optional)
            # Skip stocks with negative book value
            if hasattr(stock, 'valuation_ratios'):
                pb = stock.valuation_ratios.pb_ratio
                if pb is not None and pb < 0:
                    continue

            filtered.append(stock)

        # Sort by market cap
        sorted_stocks = sorted(
            filtered,
            key=lambda x: x.market_cap if x.market_cap else 0,
            reverse=True
        )

        # Return top N symbols
        selected = [x.symbol for x in sorted_stocks[:self.universe_size]]

        algorithm.log(f"Universe: {len(selected)} securities selected")

        return selected


class LiquidUSEquityUniverse(MomentumUniverseSelectionModel):
    """
    Pre-configured universe for liquid US equities

    - Top 500 by dollar volume
    - Excludes financials and utilities
    - Excludes all leveraged/inverse products
    """

    def __init__(self, universe_size: int = 500):
        super().__init__(
            universe_size=universe_size,
            min_price=5.0,
            min_dollar_volume=2_000_000,  # $2M minimum
            min_market_cap=1_000_000_000,  # $1B minimum
            exclude_sectors=[103, 207],  # Financials, Utilities
            exclude_leveraged=True
        )


class SmallCapMomentumUniverse(MomentumUniverseSelectionModel):
    """
    Universe for small-cap momentum strategy

    - Small caps ($300M - $2B market cap)
    - Higher liquidity threshold to ensure tradability
    """

    def __init__(self, universe_size: int = 300):
        super().__init__(
            universe_size=universe_size,
            min_price=3.0,
            min_dollar_volume=500_000,
            min_market_cap=300_000_000,  # $300M minimum
            exclude_sectors=[],  # No sector exclusions
            exclude_leveraged=True
        )

    def select_fine(self, algorithm: QCAlgorithm, fine: List[FineFundamental]) -> List[Symbol]:
        """Filter for small caps only"""
        filtered = []

        for stock in fine:
            market_cap = stock.market_cap

            # Small cap range: $300M - $2B
            if market_cap is None:
                continue
            if market_cap < 300_000_000 or market_cap > 2_000_000_000:
                continue

            # Exclude sectors
            sector = stock.asset_classification.morningstar_sector_code
            if sector in self.exclude_sectors:
                continue

            filtered.append(stock)

        # Sort by momentum potential (could use other metrics)
        sorted_stocks = sorted(
            filtered,
            key=lambda x: x.market_cap if x.market_cap else 0,
            reverse=True
        )

        return [x.symbol for x in sorted_stocks[:self.universe_size]]


class EUCompliantUniverse(MomentumUniverseSelectionModel):
    """
    EU/IBKR Compliant Universe

    Based on list of stocks verified for EU IBKR accounts.
    Only includes stocks confirmed for short selling.
    """

    # EU-compliant stock list (verified for IBKR EU accounts)
    EU_COMPLIANT_SYMBOLS = {
        'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'NVDA', 'META', 'TSLA',
        'BRK.B', 'UNH', 'JNJ', 'V', 'XOM', 'JPM', 'MA', 'PG', 'HD', 'CVX',
        'MRK', 'ABBV', 'LLY', 'PEP', 'KO', 'COST', 'AVGO', 'TMO', 'MCD',
        'WMT', 'CSCO', 'ACN', 'ABT', 'DHR', 'CRM', 'LIN', 'NKE', 'ADBE',
        'TXN', 'VZ', 'PM', 'NEE', 'CMCSA', 'UPS', 'RTX', 'ORCL', 'HON',
        'BMY', 'AMGN', 'LOW', 'QCOM', 'UNP', 'IBM', 'SPGI', 'GE', 'SBUX',
        'CAT', 'BA', 'INTC', 'INTU', 'AMD', 'PLD', 'MDLZ', 'DE', 'GILD',
        'ADI', 'AXP', 'TJX', 'BLK', 'AMAT', 'ISRG', 'BKNG', 'VRTX', 'SYK',
        'MMC', 'REGN', 'CVS', 'ADP', 'MO', 'CI', 'LRCX', 'ZTS', 'PGR',
        'CB', 'SCHW', 'CME', 'TMUS', 'NOW', 'SO', 'FIS', 'DUK', 'EOG',
        'BDX', 'CL', 'ITW', 'NOC', 'SLB', 'CSX', 'MMM', 'MU', 'ICE',
        'APD', 'KLAC', 'SHW', 'AON', 'SNPS', 'FDX', 'NSC', 'CCI', 'WM',
        'PNC', 'CDNS', 'TGT', 'ORLY', 'MCK', 'MAR', 'EMR', 'ATVI', 'USB',
        'EL', 'GD', 'PSA', 'NXPI', 'ADM', 'AZO', 'MCHP', 'HUM', 'MPC',
        'AEP', 'D', 'DG', 'FTNT', 'APH', 'MNST', 'PAYX', 'SRE', 'KMB',
        'ECL', 'DXCM', 'JCI', 'CTAS', 'VLO', 'NEM', 'GIS', 'A', 'MSCI',
        'F', 'PSX', 'TEL', 'CARR', 'ROST', 'ILMN', 'KMI', 'O', 'CMG',
        'HSY', 'WELL', 'KDP', 'XEL', 'ANET', 'PCAR', 'DLTR', 'EA', 'KHC',
        'BIIB', 'WMB', 'PH', 'CTSH', 'AIG', 'MSI', 'LHX', 'IDXX', 'TRV',
        'DD', 'EXC', 'ED', 'YUM', 'STZ', 'GPN', 'IQV', 'ALB', 'KEYS',
        'FAST', 'CPRT', 'VRSK', 'ODFL', 'AWK', 'ON', 'PPG', 'RMD', 'ROK',
        'AME', 'DOW', 'BKR', 'WEC', 'DLR', 'HES', 'CBRE', 'OKE', 'SBAC',
        'DVN', 'CDW', 'MTD', 'WBD', 'EIX', 'HPQ', 'GLW', 'EFX', 'ANSS',
        'ZBH', 'HAL', 'FANG', 'EBAY', 'ENPH', 'GWW', 'EXR', 'FTV', 'NUE'
    }

    def __init__(self):
        super().__init__(
            universe_size=len(self.EU_COMPLIANT_SYMBOLS),
            min_price=5.0,
            min_dollar_volume=1_000_000,
            min_market_cap=500_000_000,
            exclude_sectors=[],
            exclude_leveraged=True
        )

    def select_coarse(self, algorithm: QCAlgorithm, coarse: List[CoarseFundamental]) -> List[Symbol]:
        """Filter to EU-compliant symbols only"""
        filtered = []

        for stock in coarse:
            # Only include EU-compliant symbols
            if stock.symbol.value not in self.EU_COMPLIANT_SYMBOLS:
                continue

            # Basic filters
            if stock.price < self.min_price:
                continue
            if stock.dollar_volume < self.min_dollar_volume:
                continue

            filtered.append(stock)

        # Sort by dollar volume
        sorted_stocks = sorted(filtered, key=lambda x: x.dollar_volume, reverse=True)

        return [x.symbol for x in sorted_stocks]

    def select_fine(self, algorithm: QCAlgorithm, fine: List[FineFundamental]) -> List[Symbol]:
        """No additional filtering needed for EU-compliant list"""
        return [x.symbol for x in fine]
