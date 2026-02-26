from __future__ import annotations

from sources.base import SourceAdapter
from sources.bitstamp import BitstampAdapter
from sources.coin_metrics import CoinMetricsAdapter
from sources.coinbase import CoinbaseAdapter
from sources.coingecko import CoinGeckoAdapter
from sources.deribit import DeribitAdapter
from sources.farside import FarsideAdapter
from sources.fred import FredAdapter
from sources.glassnode import GlassnodeAdapter
from sources.kraken import KrakenAdapter


def get_phase1_sources() -> list[SourceAdapter]:
    return [
        FredAdapter(),
        CoinbaseAdapter(),
        FarsideAdapter(),
        CoinGeckoAdapter(),
    ]


def get_all_sources() -> list[SourceAdapter]:
    return [
        *get_phase1_sources(),
        # Phase 2 placeholders (TODO adapters)
        KrakenAdapter(),
        BitstampAdapter(),
        DeribitAdapter(),
        # Phase 3 paid placeholders
        GlassnodeAdapter(),
        CoinMetricsAdapter(),
    ]


def get_source_map() -> dict[str, SourceAdapter]:
    return {source.source_id: source for source in get_all_sources()}
