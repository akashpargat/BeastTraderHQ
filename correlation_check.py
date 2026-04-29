"""
Beast V3 — Portfolio Correlation Checker
Detects sector concentration risk in holdings.
"""
import logging

log = logging.getLogger('Beast.CorrelationCheck')


class CorrelationChecker:
    """Check portfolio for sector concentration risk."""

    SECTOR_MAP = {
        'AMD': 'Chips', 'NVDA': 'Chips', 'INTC': 'Chips', 'MU': 'Chips', 'TSM': 'Chips',
        'GOOGL': 'BigTech', 'META': 'BigTech', 'AMZN': 'BigTech', 'AAPL': 'BigTech', 'MSFT': 'BigTech',
        'PLTR': 'AI', 'CRM': 'Cloud', 'LMT': 'Defense', 'DVN': 'Energy', 'OXY': 'Energy',
        'NOK': 'Telecom', 'SOFI': 'Fintech', 'COIN': 'Crypto', 'TSLA': 'EV',
    }

    def check(self, positions: list) -> dict:
        """Returns sector concentration, warnings, beta estimate.

        Args:
            positions: list of Position objects (need .symbol, .market_value)

        Returns:
            {'sectors': {name: {'pct': float, 'stocks': list, 'value': float}},
             'warnings': list, 'max_sector': str, 'max_pct': float}
        """
        sectors = {}
        total_value = 0.0

        for p in positions:
            sym = p.symbol if hasattr(p, 'symbol') else str(p)
            val = float(p.market_value) if hasattr(p, 'market_value') else 0.0
            sector = self.SECTOR_MAP.get(sym, 'Other')
            total_value += val

            if sector not in sectors:
                sectors[sector] = {'stocks': [], 'value': 0.0, 'pct': 0.0}
            sectors[sector]['stocks'].append(sym)
            sectors[sector]['value'] += val

        # Calculate percentages
        for name, data in sectors.items():
            data['pct'] = round((data['value'] / total_value * 100) if total_value > 0 else 0, 1)
            data['value'] = round(data['value'], 2)

        # Warnings
        warnings = []
        max_sector = ''
        max_pct = 0.0

        for name, data in sectors.items():
            if data['pct'] > max_pct:
                max_pct = data['pct']
                max_sector = name
            if data['pct'] > 40:
                warnings.append(
                    f"⚠️ {name} sector at {data['pct']:.0f}% — over 40% concentration limit "
                    f"({', '.join(data['stocks'])})"
                )
            if len(data['stocks']) >= 3 and data['pct'] > 30:
                warnings.append(
                    f"📊 {name} has {len(data['stocks'])} correlated stocks ({data['pct']:.0f}%)"
                )

        if not warnings:
            warnings.append("✅ Portfolio diversification looks healthy")

        return {
            'sectors': sectors,
            'warnings': warnings,
            'max_sector': max_sector,
            'max_pct': round(max_pct, 1),
            'total_value': round(total_value, 2),
            'position_count': len(positions),
        }
