"""
Cross-Sectional Momentum - Algorithm Framework Version
======================================================

Uses Lean's modular Algorithm Framework with custom modules:
- Universe Selection: LiquidUSEquityUniverse
- Alpha: MomentumAlphaModel
- Portfolio Construction: MomentumPortfolioConstructionModel
- Risk Management: MomentumRiskManagementModel
- Execution: ImmediateExecutionModel

This is the recommended approach for production deployment.
"""

from AlgorithmImports import *
from datetime import timedelta

# Import custom modules
from alpha_model import MomentumAlphaModel, EnhancedMomentumAlphaModel
from portfolio_model import (
    MomentumPortfolioConstructionModel,
    ConfidenceWeightedPortfolioModel,
    RiskParityPortfolioModel
)
from risk_model import (
    MomentumRiskManagementModel,
    VolatilityScaledRiskModel,
    SectorExposureRiskModel
)
from universe_model import (
    MomentumUniverseSelectionModel,
    LiquidUSEquityUniverse,
    EUCompliantUniverse
)


class MomentumFrameworkAlgorithm(QCAlgorithm):
    """
    Momentum Strategy using Algorithm Framework

    Modular design allows easy swapping of components.
    """

    def initialize(self):
        """Initialize algorithm with framework components"""

        # ==================== CONFIGURATION ====================

        # Backtest period
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 1)
        self.set_cash(100000)

        # Brokerage
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)

        # Settings
        self.settings.minimum_order_margin_portfolio_percentage = 0
        self.settings.free_portfolio_value_percentage = 0.05  # 5% cash buffer

        # ==================== STRATEGY PARAMETERS ====================

        # Can be modified for optimization (use instance attributes if set, otherwise defaults)
        lookback_days = getattr(self, '_lookback_days', 126)
        n_long = getattr(self, '_n_long', 5)
        n_short = getattr(self, '_n_short', 5)
        max_position_weight = getattr(self, '_max_position_weight', 0.12)
        max_drawdown = getattr(self, '_max_drawdown', 0.10)

        # ==================== FRAMEWORK MODULES ====================

        # 1. Universe Selection
        self.set_universe_selection(
            LiquidUSEquityUniverse(universe_size=500)
        )

        # 2. Alpha Model (signal generation)
        self.set_alpha(
            MomentumAlphaModel(
                lookback_days=lookback_days,
                n_long=n_long,
                n_short=n_short
            )
        )

        # 3. Portfolio Construction
        self.set_portfolio_construction(
            MomentumPortfolioConstructionModel(
                rebalance_resolution=Resolution.DAILY,
                max_position_weight=max_position_weight,
                max_gross_exposure=2.0,
                target_net_exposure=0.0
            )
        )

        # 4. Risk Management
        self.add_risk_management(
            MomentumRiskManagementModel(
                max_drawdown_pct=max_drawdown,
                daily_loss_limit=0.03,
                position_stop_loss=0.05,
                max_gross_exposure=2.0
            )
        )

        # 5. Execution
        self.set_execution(
            ImmediateExecutionModel()
        )

        # ==================== WARMUP ====================

        self.set_warm_up(timedelta(days=lookback_days + 10))

        # ==================== LOGGING ====================

        self.log("=" * 60)
        self.log("MOMENTUM FRAMEWORK ALGORITHM INITIALIZED")
        self.log(f"Lookback: {lookback_days} days")
        self.log(f"Long: {n_long} | Short: {n_short}")
        self.log(f"Max Position: {max_position_weight:.0%}")
        self.log(f"Max Drawdown: {max_drawdown:.0%}")
        self.log("=" * 60)

    def on_end_of_algorithm(self):
        """Final summary"""
        self.log("=" * 60)
        self.log("ALGORITHM COMPLETE")
        self.log(f"Final Portfolio Value: ${self.portfolio.total_portfolio_value:,.0f}")
        self.log("=" * 60)


class EnhancedMomentumFrameworkAlgorithm(QCAlgorithm):
    """
    Enhanced Momentum Strategy with additional features

    - Volatility-adjusted momentum
    - Risk parity portfolio construction
    - Volatility-scaled risk management
    - Sector exposure limits
    """

    def initialize(self):
        """Initialize enhanced algorithm"""

        # Configuration
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 1)
        self.set_cash(100000)

        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)

        # Parameters
        lookback_days = self.get_parameter("lookback_days", 126)
        n_long = self.get_parameter("n_long", 5)
        n_short = self.get_parameter("n_short", 5)

        # Framework Modules
        self.set_universe_selection(
            LiquidUSEquityUniverse(universe_size=500)
        )

        # Enhanced alpha with volatility adjustment
        self.set_alpha(
            EnhancedMomentumAlphaModel(
                lookback_days=lookback_days,
                n_long=n_long,
                n_short=n_short,
                volatility_lookback=21
            )
        )

        # Risk parity portfolio construction
        self.set_portfolio_construction(
            RiskParityPortfolioModel(
                volatility_lookback=21,
                max_position_weight=0.15,
                max_gross_exposure=2.0
            )
        )

        # Multiple risk management layers
        self.add_risk_management(
            VolatilityScaledRiskModel(
                max_drawdown_pct=0.10,
                daily_loss_limit=0.03,
                position_stop_loss=0.05,
                target_volatility=0.15
            )
        )

        self.add_risk_management(
            SectorExposureRiskModel(
                max_sector_exposure=0.30
            )
        )

        self.set_execution(
            ImmediateExecutionModel()
        )

        self.set_warm_up(timedelta(days=lookback_days + 30))

        self.log("ENHANCED MOMENTUM FRAMEWORK INITIALIZED")


class EUCompliantMomentumAlgorithm(QCAlgorithm):
    """
    EU/IBKR Compliant Momentum Strategy

    Uses pre-verified list of stocks for EU IBKR accounts.
    """

    def initialize(self):
        """Initialize EU-compliant algorithm"""

        # Configuration
        self.set_start_date(2015, 1, 1)
        self.set_end_date(2024, 12, 1)
        self.set_cash(100000)

        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)

        # Parameters
        lookback_days = 126
        n_long = 5
        n_short = 5

        # EU-Compliant Universe
        self.set_universe_selection(
            EUCompliantUniverse()
        )

        self.set_alpha(
            MomentumAlphaModel(
                lookback_days=lookback_days,
                n_long=n_long,
                n_short=n_short
            )
        )

        self.set_portfolio_construction(
            MomentumPortfolioConstructionModel(
                max_position_weight=0.12,
                max_gross_exposure=2.0
            )
        )

        self.add_risk_management(
            MomentumRiskManagementModel(
                max_drawdown_pct=0.10,
                daily_loss_limit=0.03
            )
        )

        self.set_execution(
            ImmediateExecutionModel()
        )

        self.set_warm_up(timedelta(days=lookback_days + 10))

        self.log("EU-COMPLIANT MOMENTUM ALGORITHM INITIALIZED")
