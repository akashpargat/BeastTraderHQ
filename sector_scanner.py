"""
Beast v2.0 — Sector Scanner
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
When ONE stock in a sector moves, scan the ENTIRE sector.
Rule #27 from skill: "When a SECTOR moves, scan the ENTIRE sector."

Tracks sector momentum and finds runners across related stocks.
"""
import logging
from datetime import datetime

log = logging.getLogger('Beast.SectorScanner')

# ── SECTOR DEFINITIONS ─────────────────────────────────

SECTORS = {
    'chips': {
        'name': 'Semiconductors',
        'stocks': ['NVDA', 'AMD', 'INTC', 'TSM', 'AVGO', 'QCOM', 'MU',
                   'MRVL', 'AMAT', 'LRCX', 'KLAC', 'ON', 'TXN', 'ARM'],
        'etf': 'SMH',
    },
    'ai': {
        'name': 'Artificial Intelligence',
        'stocks': ['NVDA', 'PLTR', 'AI', 'PATH', 'SNOW', 'DDOG',
                   'CRM', 'NOW', 'PANW', 'CRWD', 'ZS'],
        'etf': 'BOTZ',
    },
    'mag7': {
        'name': 'Magnificent 7',
        'stocks': ['AAPL', 'AMZN', 'GOOGL', 'META', 'MSFT', 'NVDA', 'TSLA'],
        'etf': 'QQQ',
    },
    'crypto': {
        'name': 'Crypto / Bitcoin',
        'stocks': ['COIN', 'MSTR', 'HOOD', 'RIOT', 'MARA', 'CLSK', 'BITF'],
        'etf': 'BITO',
    },
    'energy': {
        'name': 'Energy / Oil',
        'stocks': ['XOM', 'CVX', 'OXY', 'COP', 'DVN', 'EOG', 'SLB',
                   'HAL', 'MPC', 'VLO', 'PSX'],
        'etf': 'XLE',
    },
    'defense': {
        'name': 'Defense / Aerospace',
        'stocks': ['CAT', 'DE', 'LMT', 'RTX', 'NOC', 'GD', 'BA',
                   'HON', 'GE', 'LHX', 'KTOS', 'HII', 'AXON', 'RKLB'],
        'etf': 'ITA',
    },
    'cloud': {
        'name': 'Cloud / SaaS',
        'stocks': ['ORCL', 'CRM', 'NOW', 'SNOW', 'DDOG', 'NET',
                   'MDB', 'ZS', 'PANW', 'CRWD'],
        'etf': 'WCLD',
    },
    'retail': {
        'name': 'Retail / Consumer',
        'stocks': ['AMZN', 'COST', 'WMT', 'TGT', 'SHOP', 'ETSY',
                   'HD', 'LOW', 'NKE', 'LULU'],
        'etf': 'XRT',
    },
    'biotech': {
        'name': 'Biotech / Pharma',
        'stocks': ['MRNA', 'PFE', 'JNJ', 'LLY', 'ABBV', 'BMY',
                   'AMGN', 'GILD', 'REGN', 'VRTX'],
        'etf': 'XBI',
    },
    'meme': {
        'name': 'Meme / High Retail',
        'stocks': ['AMC', 'GME', 'PLTR', 'SOFI', 'IONQ', 'NOK',
                   'BB', 'HOOD', 'RIVN', 'LCID'],
        'etf': None,
    },
    'telecom_5g': {
        'name': 'Telecom / 5G / AI Infrastructure',
        'stocks': ['NOK', 'ERIC', 'CSCO', 'JNPR', 'CIEN', 'LITE',
                   'INFN', 'CALX', 'COMM', 'VZ', 'T', 'TMUS'],
        'etf': 'FIVG',
    },
    'solar': {
        'name': 'Solar / Clean Energy',
        'stocks': ['FSLR', 'ENPH', 'SEDG', 'RUN', 'PLUG', 'BE',
                   'SPWR', 'NOVA', 'CSIQ', 'JKS'],
        'etf': 'TAN',
    },
    'space': {
        'name': 'Space / Quantum',
        'stocks': ['RKLB', 'IONQ', 'RGTI', 'LUNR', 'ASTS', 'ASTR',
                   'SPCE', 'RDW', 'MNTS', 'BKSY'],
        'etf': 'UFO',
    },
}

# Wash sale substitutes (from skill file)
WASH_SALE_SUBS = {
    'ORCL': ['CRM', 'NOW'],
    'XOM': ['CVX', 'OXY'],
    'COIN': ['HOOD'],
    'CAT': ['DE'],
    'META': ['SNAP', 'PINS'],
    'MSTR': ['COIN'],
    'PLTR': ['AI', 'PATH'],
    'AMD': ['INTC', 'NVDA'],
    'AMZN': ['SHOP', 'WMT'],
    'MSFT': ['GOOGL', 'CRM'],
}


class SectorScanner:
    """Scans entire sectors when one stock moves."""

    def __init__(self):
        self._alerts = {}

    def find_sector(self, symbol: str) -> list[str]:
        """Find which sectors a stock belongs to."""
        found = []
        for sector_id, sector in SECTORS.items():
            if symbol in sector['stocks']:
                found.append(sector_id)
        return found

    def get_sector_stocks(self, sector_id: str) -> list[str]:
        """Get all stocks in a sector."""
        if sector_id in SECTORS:
            return SECTORS[sector_id]['stocks']
        return []

    def detect_sector_move(self, movers: list[dict]) -> list[dict]:
        """Given a list of movers, detect if a SECTOR is moving.
        
        Args:
            movers: list of {'symbol': str, 'change_pct': float}
        
        Returns: list of sectors that have 2+ stocks moving same direction
        """
        sector_moves = {}

        for mover in movers:
            symbol = mover['symbol']
            change = mover.get('change_pct', 0)
            sectors = self.find_sector(symbol)

            for sector_id in sectors:
                if sector_id not in sector_moves:
                    sector_moves[sector_id] = {'up': [], 'down': []}
                if change > 0.02:  # >2% up
                    sector_moves[sector_id]['up'].append(symbol)
                elif change < -0.02:  # >2% down
                    sector_moves[sector_id]['down'].append(symbol)

        # Sector alert if 2+ stocks moving same direction
        alerts = []
        for sector_id, moves in sector_moves.items():
            if len(moves['up']) >= 2:
                alerts.append({
                    'sector': sector_id,
                    'name': SECTORS[sector_id]['name'],
                    'direction': 'UP',
                    'movers': moves['up'],
                    'scan_all': SECTORS[sector_id]['stocks'],
                    'etf': SECTORS[sector_id].get('etf'),
                })
                log.info(f"🔥 SECTOR ALERT: {SECTORS[sector_id]['name']} — "
                        f"{len(moves['up'])} stocks UP 2%+: {moves['up']}")
            if len(moves['down']) >= 2:
                alerts.append({
                    'sector': sector_id,
                    'name': SECTORS[sector_id]['name'],
                    'direction': 'DOWN',
                    'movers': moves['down'],
                    'scan_all': SECTORS[sector_id]['stocks'],
                    'etf': SECTORS[sector_id].get('etf'),
                })
                log.info(f"🔻 SECTOR ALERT: {SECTORS[sector_id]['name']} — "
                        f"{len(moves['down'])} stocks DOWN 2%+: {moves['down']}")

        return alerts

    def get_wash_sale_sub(self, symbol: str) -> list[str]:
        """Get wash sale substitutes for a symbol."""
        return WASH_SALE_SUBS.get(symbol, [])

    def get_all_sectors_summary(self) -> dict:
        """Get sector count summary."""
        return {sid: {'name': s['name'], 'count': len(s['stocks'])}
                for sid, s in SECTORS.items()}
