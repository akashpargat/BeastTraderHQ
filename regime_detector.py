"""
Beast v2.0 — Regime Detector (with Hysteresis)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Detects BULL/BEAR/CHOPPY/RED_ALERT based on SPY.
Hysteresis prevents thrashing on threshold boundaries.
"""
import logging
from datetime import datetime, timedelta
from models import Regime

log = logging.getLogger('Beast.RegimeDetector')

# Thresholds
BULL_THRESHOLD = 0.003      # SPY > +0.3%
BEAR_THRESHOLD = -0.003     # SPY < -0.3%
RED_ALERT_THRESHOLD = -0.01 # SPY < -1.0%
HYSTERESIS_BAND = 0.002     # Dead zone ±0.2%
MIN_DWELL_SECONDS = 1800    # 30 minutes before regime change


class RegimeDetector:
    """SPY-based regime detection with hysteresis to prevent thrashing."""

    def __init__(self):
        self.current_regime = Regime.CHOPPY
        self.last_change_time = datetime.min
        self.confirmation_count = 0
        self._pending_regime: Regime = None
        self.spy_change_pct = 0.0

    def detect(self, spy_change_pct: float) -> Regime:
        """Detect regime with hysteresis and dwell time."""
        self.spy_change_pct = spy_change_pct
        raw = self._raw_regime(spy_change_pct)

        # If raw matches current, reset pending
        if raw == self.current_regime:
            self._pending_regime = None
            self.confirmation_count = 0
            return self.current_regime

        # RED_ALERT overrides dwell time (safety)
        if raw == Regime.RED_ALERT:
            self._switch(raw, spy_change_pct)
            return self.current_regime

        # Check dwell time
        elapsed = (datetime.now() - self.last_change_time).total_seconds()
        if elapsed < MIN_DWELL_SECONDS:
            log.debug(
                f"Regime {raw.value} detected but dwell time not met "
                f"({elapsed:.0f}s < {MIN_DWELL_SECONDS}s). Staying {self.current_regime.value}"
            )
            return self.current_regime

        # Require 2 consecutive confirmations
        if raw == self._pending_regime:
            self.confirmation_count += 1
        else:
            self._pending_regime = raw
            self.confirmation_count = 1

        if self.confirmation_count >= 2:
            self._switch(raw, spy_change_pct)

        return self.current_regime

    def _raw_regime(self, pct: float) -> Regime:
        """Raw regime without hysteresis."""
        if pct <= RED_ALERT_THRESHOLD:
            return Regime.RED_ALERT
        elif pct < BEAR_THRESHOLD:
            return Regime.BEAR

        # Apply hysteresis band for BULL/CHOPPY boundary
        if self.current_regime == Regime.BULL:
            # Must drop below threshold - hysteresis to leave BULL
            if pct < BULL_THRESHOLD - HYSTERESIS_BAND:
                return Regime.CHOPPY
            return Regime.BULL
        elif self.current_regime == Regime.CHOPPY:
            # Must rise above threshold + hysteresis to enter BULL
            if pct > BULL_THRESHOLD + HYSTERESIS_BAND:
                return Regime.BULL
            return Regime.CHOPPY
        else:
            # From BEAR, standard thresholds
            if pct > BULL_THRESHOLD:
                return Regime.BULL
            elif pct > BEAR_THRESHOLD:
                return Regime.CHOPPY
            return Regime.BEAR

    def _switch(self, new_regime: Regime, pct: float):
        old = self.current_regime
        self.current_regime = new_regime
        self.last_change_time = datetime.now()
        self._pending_regime = None
        self.confirmation_count = 0
        log.info(
            f"🔄 REGIME CHANGE: {old.value} → {new_regime.value} "
            f"(SPY {pct:+.2%})"
        )

    def get_status(self) -> dict:
        return {
            'regime': self.current_regime.value,
            'spy_change_pct': f"{self.spy_change_pct:+.2%}",
            'last_change': self.last_change_time.isoformat() if self.last_change_time != datetime.min else 'never',
            'pending': self._pending_regime.value if self._pending_regime else None,
            'confirmations': self.confirmation_count,
        }
