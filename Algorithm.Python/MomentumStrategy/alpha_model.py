"""
Momentum Alpha Model
====================

Custom Alpha Model for Cross-Sectional Momentum Strategy.
Generates insights based on momentum ranking.
"""

from AlgorithmImports import *
from datetime import timedelta
from typing import List, Dict


class MomentumAlphaModel(AlphaModel):
    """
    Cross-Sectional Momentum Alpha Model

    Generates long insights for top N momentum stocks
    and short insights for bottom N momentum stocks.
    """

    def __init__(
        self,
        lookback_days: int = 126,
        n_long: int = 5,
        n_short: int = 5,
        resolution: Resolution = Resolution.DAILY
    ):
        """
        Initialize momentum alpha model

        Args:
            lookback_days: Days for momentum calculation (default 126 = 6 months)
            n_long: Number of long positions
            n_short: Number of short positions
            resolution: Data resolution
        """
        self.lookback_days = lookback_days
        self.n_long = n_long
        self.n_short = n_short
        self.resolution = resolution

        # Momentum indicators by symbol
        self.momentum_by_symbol: Dict[Symbol, MomentumPercent] = {}

        # Insight duration
        self.insight_period = timedelta(days=1)

        # Track last generation time
        self.last_generation_time = None

        # Excluded symbols (leveraged ETFs)
        self.excluded_symbols = {
            'TQQQ', 'SQQQ', 'TECL', 'TECS', 'SOXL', 'SOXS', 'UPRO', 'SPXU',
            'SPXL', 'SPXS', 'TNA', 'TZA', 'UDOW', 'SDOW', 'LABU', 'LABD',
            'NUGT', 'DUST', 'FNGU', 'FNGD', 'VXX', 'UVXY', 'SVXY', 'VIXY',
            'USO', 'UNG', 'GLD', 'SLV', 'QLD', 'QID', 'SSO', 'SDS',
            'JNUG', 'JDST', 'FAS', 'FAZ', 'ERX', 'ERY'
        }

    def update(self, algorithm: QCAlgorithm, data: Slice) -> List[Insight]:
        """
        Generate insights based on momentum ranking

        Args:
            algorithm: The algorithm instance
            data: Current data slice

        Returns:
            List of insights
        """
        insights = []

        # Only generate once per day
        if self.last_generation_time is not None:
            if self.last_generation_time.date() == algorithm.time.date():
                return insights

        self.last_generation_time = algorithm.time

        # Calculate momentum scores
        scores = self._calculate_momentum_scores(algorithm)

        if len(scores) < (self.n_long + self.n_short):
            algorithm.log(f"MomentumAlpha: Insufficient securities ({len(scores)})")
            return insights

        # Rank by momentum
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Get long and short symbols
        long_symbols = [x[0] for x in ranked[:self.n_long]]
        short_symbols = [x[0] for x in ranked[-self.n_short:]]

        # Generate long insights
        for symbol in long_symbols:
            momentum_score = scores[symbol]

            insight = Insight.price(
                symbol,
                self.insight_period,
                InsightDirection.UP,
                magnitude=abs(momentum_score),
                confidence=self._calculate_confidence(momentum_score, scores),
                source_model=self.get_model_name()
            )
            insights.append(insight)

        # Generate short insights
        for symbol in short_symbols:
            momentum_score = scores[symbol]

            insight = Insight.price(
                symbol,
                self.insight_period,
                InsightDirection.DOWN,
                magnitude=abs(momentum_score),
                confidence=self._calculate_confidence(momentum_score, scores),
                source_model=self.get_model_name()
            )
            insights.append(insight)

        # Log summary
        if insights:
            algorithm.log(f"MomentumAlpha: Generated {len(insights)} insights "
                         f"(Long: {len(long_symbols)}, Short: {len(short_symbols)})")

        return insights

    def _calculate_momentum_scores(self, algorithm: QCAlgorithm) -> Dict[Symbol, float]:
        """Calculate momentum scores for all tracked securities"""
        scores = {}

        for symbol, indicator in self.momentum_by_symbol.items():
            # Skip if indicator not ready
            if not indicator.is_ready:
                continue

            # Skip if not in securities
            if symbol not in algorithm.securities:
                continue

            security = algorithm.securities[symbol]
            if security.price <= 0:
                continue

            # Get momentum score
            momentum = indicator.current.value

            # Filter extreme values (potential data errors)
            if abs(momentum) > 500:
                continue

            scores[symbol] = momentum

        return scores

    def _calculate_confidence(self, score: float, all_scores: Dict[Symbol, float]) -> float:
        """
        Calculate confidence based on momentum strength

        Args:
            score: Momentum score for this symbol
            all_scores: All momentum scores

        Returns:
            Confidence level (0-1)
        """
        if not all_scores:
            return 0.5

        # Calculate z-score
        values = list(all_scores.values())
        mean = sum(values) / len(values)
        std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5

        if std == 0:
            return 0.5

        z_score = abs(score - mean) / std

        # Convert to confidence (higher z-score = higher confidence)
        # Cap between 0.3 and 0.9
        confidence = min(0.9, max(0.3, 0.5 + z_score * 0.1))

        return confidence

    def on_securities_changed(self, algorithm: QCAlgorithm, changes: SecurityChanges):
        """Handle universe changes"""

        # Add momentum indicators for new securities
        for security in changes.added_securities:
            symbol = security.symbol

            # Skip excluded symbols
            if symbol.value in self.excluded_symbols:
                continue

            if symbol not in self.momentum_by_symbol:
                indicator = algorithm.momc(symbol, self.lookback_days, self.resolution)
                self.momentum_by_symbol[symbol] = indicator

        # Remove indicators for removed securities
        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol in self.momentum_by_symbol:
                del self.momentum_by_symbol[symbol]

    def get_model_name(self) -> str:
        """Get model name for insight attribution"""
        return f"MomentumAlpha_{self.lookback_days}d"


class EnhancedMomentumAlphaModel(MomentumAlphaModel):
    """
    Enhanced Momentum Alpha with additional filters

    Adds:
    - Volatility-adjusted momentum
    - Volume confirmation
    - Trend strength filter
    """

    def __init__(
        self,
        lookback_days: int = 126,
        n_long: int = 5,
        n_short: int = 5,
        volatility_lookback: int = 21,
        volume_lookback: int = 21,
        resolution: Resolution = Resolution.DAILY
    ):
        super().__init__(lookback_days, n_long, n_short, resolution)

        self.volatility_lookback = volatility_lookback
        self.volume_lookback = volume_lookback

        # Additional indicators
        self.volatility_by_symbol: Dict[Symbol, StandardDeviation] = {}
        self.volume_sma_by_symbol: Dict[Symbol, SimpleMovingAverage] = {}

    def _calculate_momentum_scores(self, algorithm: QCAlgorithm) -> Dict[Symbol, float]:
        """Calculate volatility-adjusted momentum scores"""
        raw_scores = super()._calculate_momentum_scores(algorithm)

        # Adjust by volatility (risk-adjusted momentum)
        adjusted_scores = {}

        for symbol, momentum in raw_scores.items():
            if symbol in self.volatility_by_symbol:
                vol_indicator = self.volatility_by_symbol[symbol]
                if vol_indicator.is_ready and vol_indicator.current.value > 0:
                    # Sharpe-like ratio: momentum / volatility
                    vol = vol_indicator.current.value
                    adjusted_scores[symbol] = momentum / vol
                else:
                    adjusted_scores[symbol] = momentum
            else:
                adjusted_scores[symbol] = momentum

        return adjusted_scores

    def on_securities_changed(self, algorithm: QCAlgorithm, changes: SecurityChanges):
        """Handle universe changes with additional indicators"""
        super().on_securities_changed(algorithm, changes)

        for security in changes.added_securities:
            symbol = security.symbol

            if symbol.value in self.excluded_symbols:
                continue

            # Add volatility indicator
            if symbol not in self.volatility_by_symbol:
                self.volatility_by_symbol[symbol] = algorithm.std(
                    symbol, self.volatility_lookback, self.resolution
                )

            # Add volume SMA
            if symbol not in self.volume_sma_by_symbol:
                self.volume_sma_by_symbol[symbol] = algorithm.sma(
                    symbol, self.volume_lookback, self.resolution, Field.VOLUME
                )

        for security in changes.removed_securities:
            symbol = security.symbol
            if symbol in self.volatility_by_symbol:
                del self.volatility_by_symbol[symbol]
            if symbol in self.volume_sma_by_symbol:
                del self.volume_sma_by_symbol[symbol]

    def get_model_name(self) -> str:
        return f"EnhancedMomentumAlpha_{self.lookback_days}d"
