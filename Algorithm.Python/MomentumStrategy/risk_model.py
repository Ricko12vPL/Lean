"""
Risk Management Models
======================

Custom risk management for momentum strategy.
Implements multiple kill switches and position limits.
"""

from AlgorithmImports import *
from datetime import timedelta, datetime
from typing import List, Dict, Optional


class MomentumRiskManagementModel(RiskManagementModel):
    """
    Comprehensive Risk Management for Momentum Strategy

    Features:
    - Portfolio max drawdown limit
    - Daily loss limit
    - Single position stop loss
    - Gross exposure limit
    - Volatility-based position sizing
    """

    def __init__(
        self,
        max_drawdown_pct: float = 0.10,
        daily_loss_limit: float = 0.03,
        position_stop_loss: float = 0.05,
        max_gross_exposure: float = 2.0,
        trailing_stop_pct: float = 0.08
    ):
        """
        Initialize risk management model

        Args:
            max_drawdown_pct: Maximum portfolio drawdown (default 10%)
            daily_loss_limit: Maximum daily loss (default 3%)
            position_stop_loss: Stop loss per position (default 5%)
            max_gross_exposure: Maximum gross exposure (default 200%)
            trailing_stop_pct: Trailing stop percentage (default 8%)
        """
        super().__init__()

        self.max_drawdown_pct = max_drawdown_pct
        self.daily_loss_limit = daily_loss_limit
        self.position_stop_loss = position_stop_loss
        self.max_gross_exposure = max_gross_exposure
        self.trailing_stop_pct = trailing_stop_pct

        # Tracking
        self.high_water_mark = 0.0
        self.daily_starting_equity = 0.0
        self.last_equity_date = None
        self.position_high_marks: Dict[Symbol, float] = {}

        # Risk state
        self.is_risk_off = False
        self.risk_off_until: Optional[datetime] = None

    def manage_risk(
        self,
        algorithm: QCAlgorithm,
        targets: List[PortfolioTarget]
    ) -> List[PortfolioTarget]:
        """
        Manage portfolio risk

        Args:
            algorithm: Algorithm instance
            targets: Current portfolio targets

        Returns:
            Adjusted portfolio targets
        """
        current_equity = algorithm.portfolio.total_portfolio_value

        # Initialize on first call
        if self.high_water_mark == 0:
            self.high_water_mark = current_equity
            self.daily_starting_equity = current_equity

        # Reset daily tracking
        if self.last_equity_date != algorithm.time.date():
            self.daily_starting_equity = current_equity
            self.last_equity_date = algorithm.time.date()

        # Update high water mark
        if current_equity > self.high_water_mark:
            self.high_water_mark = current_equity

        # Check if we're in risk-off mode
        if self.is_risk_off:
            if algorithm.time < self.risk_off_until:
                # Stay in risk-off mode - liquidate all
                return self._liquidate_all(algorithm, targets, "Risk-off mode active")
            else:
                # Exit risk-off mode
                self.is_risk_off = False
                algorithm.log("Risk-off mode ended")

        # Check portfolio-level risk limits
        risk_targets = self._check_portfolio_risk(algorithm, targets, current_equity)
        if risk_targets is not None:
            return risk_targets

        # Check position-level risk limits
        targets = self._check_position_risk(algorithm, targets)

        # Check gross exposure
        targets = self._check_gross_exposure(algorithm, targets, current_equity)

        return targets

    def _check_portfolio_risk(
        self,
        algorithm: QCAlgorithm,
        targets: List[PortfolioTarget],
        current_equity: float
    ) -> Optional[List[PortfolioTarget]]:
        """Check portfolio-level risk limits"""

        # Check max drawdown
        drawdown = (self.high_water_mark - current_equity) / self.high_water_mark
        if drawdown > self.max_drawdown_pct:
            algorithm.log(f"MAX DRAWDOWN BREACHED: {drawdown:.2%} > {self.max_drawdown_pct:.0%}")
            self._enter_risk_off_mode(algorithm, timedelta(days=1))
            return self._liquidate_all(algorithm, targets, "Max drawdown limit")

        # Check daily loss limit
        daily_pnl = (current_equity - self.daily_starting_equity) / self.daily_starting_equity
        if daily_pnl < -self.daily_loss_limit:
            algorithm.log(f"DAILY LOSS LIMIT BREACHED: {daily_pnl:.2%}")
            self._enter_risk_off_mode(algorithm, timedelta(hours=24))
            return self._liquidate_all(algorithm, targets, "Daily loss limit")

        return None

    def _check_position_risk(
        self,
        algorithm: QCAlgorithm,
        targets: List[PortfolioTarget]
    ) -> List[PortfolioTarget]:
        """Check position-level risk limits"""
        adjusted_targets = []

        for target in targets:
            symbol = target.symbol

            # Get current position
            holding = algorithm.portfolio[symbol]

            if not holding.invested:
                # No position - keep target
                adjusted_targets.append(target)
                continue

            # Update position high water mark
            current_value = abs(holding.holdings_value)
            if symbol not in self.position_high_marks:
                self.position_high_marks[symbol] = current_value
            elif current_value > self.position_high_marks[symbol]:
                self.position_high_marks[symbol] = current_value

            # Check stop loss
            avg_cost = holding.average_price
            current_price = holding.price

            if holding.is_long:
                pnl_pct = (current_price - avg_cost) / avg_cost
            else:
                pnl_pct = (avg_cost - current_price) / avg_cost

            # Hard stop loss
            if pnl_pct < -self.position_stop_loss:
                algorithm.log(f"STOP LOSS: {symbol.value} at {pnl_pct:.2%}")
                adjusted_targets.append(PortfolioTarget(symbol, 0))
                continue

            # Trailing stop
            if symbol in self.position_high_marks:
                high_mark = self.position_high_marks[symbol]
                if current_value < high_mark * (1 - self.trailing_stop_pct):
                    algorithm.log(f"TRAILING STOP: {symbol.value}")
                    adjusted_targets.append(PortfolioTarget(symbol, 0))
                    continue

            # Position OK - keep target
            adjusted_targets.append(target)

        return adjusted_targets

    def _check_gross_exposure(
        self,
        algorithm: QCAlgorithm,
        targets: List[PortfolioTarget],
        current_equity: float
    ) -> List[PortfolioTarget]:
        """Check and adjust for gross exposure limits"""

        # Calculate current gross exposure
        long_value = sum(
            h.holdings_value for h in algorithm.portfolio.values()
            if h.invested and h.quantity > 0
        )
        short_value = sum(
            abs(h.holdings_value) for h in algorithm.portfolio.values()
            if h.invested and h.quantity < 0
        )

        gross_exposure = (long_value + short_value) / current_equity if current_equity > 0 else 0

        # If over limit, scale down targets
        if gross_exposure > self.max_gross_exposure:
            scale_factor = self.max_gross_exposure / gross_exposure
            algorithm.log(f"Scaling positions by {scale_factor:.2f} for gross exposure")

            targets = [
                PortfolioTarget(t.symbol, t.quantity * scale_factor)
                for t in targets
            ]

        return targets

    def _enter_risk_off_mode(self, algorithm: QCAlgorithm, duration: timedelta):
        """Enter risk-off mode"""
        self.is_risk_off = True
        self.risk_off_until = algorithm.time + duration
        algorithm.log(f"Entering risk-off mode until {self.risk_off_until}")

    def _liquidate_all(
        self,
        algorithm: QCAlgorithm,
        targets: List[PortfolioTarget],
        reason: str
    ) -> List[PortfolioTarget]:
        """Generate liquidation targets for all positions"""
        algorithm.log(f"LIQUIDATING ALL: {reason}")

        liquidation_targets = []

        # Liquidate all current positions
        for holding in algorithm.portfolio.values():
            if holding.invested:
                liquidation_targets.append(PortfolioTarget(holding.symbol, 0))

        # Also set all incoming targets to 0
        for target in targets:
            if target.symbol not in [t.symbol for t in liquidation_targets]:
                liquidation_targets.append(PortfolioTarget(target.symbol, 0))

        return liquidation_targets

    def on_securities_changed(self, algorithm: QCAlgorithm, changes: SecurityChanges):
        """Clean up tracking for removed securities"""
        for security in changes.removed_securities:
            if security.symbol in self.position_high_marks:
                del self.position_high_marks[security.symbol]


class VolatilityScaledRiskModel(MomentumRiskManagementModel):
    """
    Volatility-Scaled Risk Management

    Adjusts position sizes based on market volatility.
    Reduces exposure in high volatility environments.
    """

    def __init__(
        self,
        max_drawdown_pct: float = 0.10,
        daily_loss_limit: float = 0.03,
        position_stop_loss: float = 0.05,
        max_gross_exposure: float = 2.0,
        target_volatility: float = 0.15,
        vix_high_threshold: float = 30.0,
        vix_extreme_threshold: float = 40.0
    ):
        super().__init__(
            max_drawdown_pct, daily_loss_limit,
            position_stop_loss, max_gross_exposure
        )

        self.target_volatility = target_volatility
        self.vix_high_threshold = vix_high_threshold
        self.vix_extreme_threshold = vix_extreme_threshold

        # VIX tracking
        self.vix_symbol: Optional[Symbol] = None
        self.current_vix: float = 15.0  # Default

    def manage_risk(
        self,
        algorithm: QCAlgorithm,
        targets: List[PortfolioTarget]
    ) -> List[PortfolioTarget]:
        """Manage risk with volatility scaling"""

        # Get base risk management
        targets = super().manage_risk(algorithm, targets)

        # Apply volatility scaling
        targets = self._apply_volatility_scaling(algorithm, targets)

        return targets

    def _apply_volatility_scaling(
        self,
        algorithm: QCAlgorithm,
        targets: List[PortfolioTarget]
    ) -> List[PortfolioTarget]:
        """Scale positions based on VIX level"""

        # Try to get VIX value
        if self.vix_symbol and self.vix_symbol in algorithm.securities:
            vix_security = algorithm.securities[self.vix_symbol]
            if vix_security.price > 0:
                self.current_vix = vix_security.price

        # Calculate scaling factor
        if self.current_vix >= self.vix_extreme_threshold:
            # Extreme volatility - reduce to 25%
            scale_factor = 0.25
            algorithm.log(f"EXTREME VOL: VIX {self.current_vix:.1f} - scaling to 25%")
        elif self.current_vix >= self.vix_high_threshold:
            # High volatility - reduce to 50%
            scale_factor = 0.50
            algorithm.log(f"HIGH VOL: VIX {self.current_vix:.1f} - scaling to 50%")
        else:
            # Normal volatility
            scale_factor = 1.0

        if scale_factor < 1.0:
            targets = [
                PortfolioTarget(t.symbol, t.quantity * scale_factor)
                for t in targets
            ]

        return targets


class SectorExposureRiskModel(RiskManagementModel):
    """
    Sector Exposure Risk Management

    Limits exposure to any single sector.
    Prevents concentration risk.
    """

    def __init__(self, max_sector_exposure: float = 0.30):
        """
        Args:
            max_sector_exposure: Maximum exposure to any sector (default 30%)
        """
        super().__init__()
        self.max_sector_exposure = max_sector_exposure
        self.sector_by_symbol: Dict[Symbol, str] = {}

    def manage_risk(
        self,
        algorithm: QCAlgorithm,
        targets: List[PortfolioTarget]
    ) -> List[PortfolioTarget]:
        """Manage sector exposure risk"""

        # Calculate sector exposures
        sector_exposure: Dict[str, float] = {}

        for target in targets:
            symbol = target.symbol
            sector = self._get_sector(algorithm, symbol)

            if sector:
                exposure = abs(target.quantity)
                sector_exposure[sector] = sector_exposure.get(sector, 0) + exposure

        # Check for over-exposed sectors
        for sector, exposure in sector_exposure.items():
            if exposure > self.max_sector_exposure:
                # Scale down positions in this sector
                scale_factor = self.max_sector_exposure / exposure
                algorithm.log(f"SECTOR LIMIT: {sector} at {exposure:.1%}, "
                            f"scaling to {self.max_sector_exposure:.0%}")

                targets = [
                    PortfolioTarget(
                        t.symbol,
                        t.quantity * scale_factor if self._get_sector(algorithm, t.symbol) == sector
                        else t.quantity
                    )
                    for t in targets
                ]

        return targets

    def _get_sector(self, algorithm: QCAlgorithm, symbol: Symbol) -> Optional[str]:
        """Get sector for symbol"""
        if symbol in self.sector_by_symbol:
            return self.sector_by_symbol[symbol]

        if symbol in algorithm.securities:
            security = algorithm.securities[symbol]
            if hasattr(security, 'fundamentals') and security.fundamentals:
                sector = security.fundamentals.asset_classification.morningstar_sector_code
                sector_name = str(sector) if sector else "Unknown"
                self.sector_by_symbol[symbol] = sector_name
                return sector_name

        return None
