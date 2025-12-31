"""
Portfolio Construction Models
=============================

Custom portfolio construction for momentum strategy.
Implements equal-weight and risk-parity approaches.
"""

from AlgorithmImports import *
from datetime import timedelta
from typing import List, Dict, Optional
import numpy as np


class MomentumPortfolioConstructionModel(PortfolioConstructionModel):
    """
    Equal-Weight Portfolio Construction for Momentum Strategy

    Features:
    - Equal dollar allocation to long and short positions
    - Position size limits
    - Gross/net exposure limits
    - Rebalancing frequency control
    """

    def __init__(
        self,
        rebalance_resolution: Resolution = Resolution.DAILY,
        max_position_weight: float = 0.12,
        max_gross_exposure: float = 2.0,
        target_net_exposure: float = 0.0
    ):
        """
        Initialize portfolio construction model

        Args:
            rebalance_resolution: Resolution for rebalancing
            max_position_weight: Maximum weight per position (default 12%)
            max_gross_exposure: Maximum gross exposure (default 200%)
            target_net_exposure: Target net exposure (default 0% market neutral)
        """
        super().__init__()

        self.rebalance_resolution = rebalance_resolution
        self.max_position_weight = max_position_weight
        self.max_gross_exposure = max_gross_exposure
        self.target_net_exposure = target_net_exposure

        # Tracking
        self.last_rebalance_time = None
        self.insight_collection = InsightCollection()

        # Set rebalancing function
        self.set_rebalancing_func(self._should_rebalance)

    def _should_rebalance(self, time: datetime) -> bool:
        """Determine if rebalancing should occur"""
        if self.last_rebalance_time is None:
            return True

        if self.rebalance_resolution == Resolution.DAILY:
            return time.date() > self.last_rebalance_time.date()

        return True

    def determine_target_percent(
        self,
        algorithm: QCAlgorithm,
        insights: List[Insight]
    ) -> List[PortfolioTarget]:
        """
        Determine target portfolio weights

        Args:
            algorithm: Algorithm instance
            insights: List of active insights

        Returns:
            List of portfolio targets
        """
        targets = []

        if not insights:
            return targets

        # Update insight collection
        self.insight_collection.add_range(insights)

        # Get active insights
        active_insights = list(self.insight_collection.get_active_insights(algorithm.utc_time))

        if not active_insights:
            return targets

        # Separate long and short insights
        long_insights = [i for i in active_insights if i.direction == InsightDirection.UP]
        short_insights = [i for i in active_insights if i.direction == InsightDirection.DOWN]

        # Calculate base weights (equal weight)
        total_positions = len(long_insights) + len(short_insights)
        if total_positions == 0:
            return targets

        base_weight = 1.0 / total_positions

        # Apply position limits
        weight = min(base_weight, self.max_position_weight)

        # Generate targets
        for insight in long_insights:
            targets.append(PortfolioTarget(insight.symbol, weight))

        for insight in short_insights:
            targets.append(PortfolioTarget(insight.symbol, -weight))

        # Validate gross exposure
        gross_exposure = sum(abs(t.quantity) for t in targets)
        if gross_exposure > self.max_gross_exposure:
            # Scale down proportionally
            scale = self.max_gross_exposure / gross_exposure
            targets = [PortfolioTarget(t.symbol, t.quantity * scale) for t in targets]

        # Update tracking
        self.last_rebalance_time = algorithm.time

        # Log summary
        long_count = len(long_insights)
        short_count = len(short_insights)
        algorithm.log(f"Portfolio: {long_count} long, {short_count} short, "
                     f"weight: {weight:.1%}, gross: {gross_exposure:.1%}")

        return targets

    def on_securities_changed(self, algorithm: QCAlgorithm, changes: SecurityChanges):
        """Handle security changes"""
        # Remove insights for removed securities
        for security in changes.removed_securities:
            self.insight_collection.remove(security.symbol)


class ConfidenceWeightedPortfolioModel(MomentumPortfolioConstructionModel):
    """
    Confidence-Weighted Portfolio Construction

    Weights positions by insight confidence level.
    Higher confidence = larger position.
    """

    def determine_target_percent(
        self,
        algorithm: QCAlgorithm,
        insights: List[Insight]
    ) -> List[PortfolioTarget]:
        """Determine target weights based on confidence"""
        targets = []

        if not insights:
            return targets

        # Update insight collection
        self.insight_collection.add_range(insights)

        # Get active insights
        active_insights = list(self.insight_collection.get_active_insights(algorithm.utc_time))

        if not active_insights:
            return targets

        # Separate long and short
        long_insights = [i for i in active_insights if i.direction == InsightDirection.UP]
        short_insights = [i for i in active_insights if i.direction == InsightDirection.DOWN]

        # Calculate confidence-weighted allocation
        def confidence_weights(insights_list):
            if not insights_list:
                return {}
            total_conf = sum(i.confidence for i in insights_list)
            if total_conf == 0:
                return {i.symbol: 1.0 / len(insights_list) for i in insights_list}
            return {i.symbol: i.confidence / total_conf for i in insights_list}

        long_weights = confidence_weights(long_insights)
        short_weights = confidence_weights(short_insights)

        # Allocate 50% to long, 50% to short (market neutral)
        long_allocation = 0.5
        short_allocation = 0.5

        # Generate targets
        for symbol, rel_weight in long_weights.items():
            weight = rel_weight * long_allocation
            weight = min(weight, self.max_position_weight)
            targets.append(PortfolioTarget(symbol, weight))

        for symbol, rel_weight in short_weights.items():
            weight = rel_weight * short_allocation
            weight = min(weight, self.max_position_weight)
            targets.append(PortfolioTarget(symbol, -weight))

        # Update tracking
        self.last_rebalance_time = algorithm.time

        return targets


class RiskParityPortfolioModel(MomentumPortfolioConstructionModel):
    """
    Risk Parity Portfolio Construction

    Equalizes risk contribution from each position.
    Uses inverse volatility weighting.
    """

    def __init__(
        self,
        volatility_lookback: int = 21,
        rebalance_resolution: Resolution = Resolution.DAILY,
        max_position_weight: float = 0.15,
        max_gross_exposure: float = 2.0
    ):
        super().__init__(rebalance_resolution, max_position_weight, max_gross_exposure)
        self.volatility_lookback = volatility_lookback
        self.volatility_by_symbol: Dict[Symbol, float] = {}

    def determine_target_percent(
        self,
        algorithm: QCAlgorithm,
        insights: List[Insight]
    ) -> List[PortfolioTarget]:
        """Determine target weights using inverse volatility"""
        targets = []

        if not insights:
            return targets

        # Update insight collection
        self.insight_collection.add_range(insights)
        active_insights = list(self.insight_collection.get_active_insights(algorithm.utc_time))

        if not active_insights:
            return targets

        # Get volatilities for each symbol
        volatilities = {}
        for insight in active_insights:
            symbol = insight.symbol
            if symbol in algorithm.securities:
                history = algorithm.history(symbol, self.volatility_lookback, Resolution.DAILY)
                if len(history) >= self.volatility_lookback // 2:
                    returns = history['close'].pct_change().dropna()
                    vol = returns.std() * np.sqrt(252)  # Annualized
                    if vol > 0:
                        volatilities[symbol] = vol

        if not volatilities:
            # Fall back to equal weight
            return super().determine_target_percent(algorithm, insights)

        # Calculate inverse volatility weights
        inv_vols = {s: 1.0 / v for s, v in volatilities.items()}

        # Separate long and short
        long_insights = [i for i in active_insights if i.direction == InsightDirection.UP
                        and i.symbol in inv_vols]
        short_insights = [i for i in active_insights if i.direction == InsightDirection.DOWN
                         and i.symbol in inv_vols]

        # Calculate weights
        long_inv_vol_sum = sum(inv_vols[i.symbol] for i in long_insights) if long_insights else 1
        short_inv_vol_sum = sum(inv_vols[i.symbol] for i in short_insights) if short_insights else 1

        for insight in long_insights:
            weight = (inv_vols[insight.symbol] / long_inv_vol_sum) * 0.5
            weight = min(weight, self.max_position_weight)
            targets.append(PortfolioTarget(insight.symbol, weight))

        for insight in short_insights:
            weight = (inv_vols[insight.symbol] / short_inv_vol_sum) * 0.5
            weight = min(weight, self.max_position_weight)
            targets.append(PortfolioTarget(insight.symbol, -weight))

        self.last_rebalance_time = algorithm.time

        return targets
