from __future__ import annotations

from config.settings import get_settings
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

settings = get_settings()


def get_phase1_sources() -> list[SourceAdapter]:
    return [
        FredAdapter(),
        CoinbaseAdapter(),
        FarsideAdapter(),
        CoinGeckoAdapter(),
    ]


def get_phase2_sources() -> list[SourceAdapter]:
    return [
        KrakenAdapter(),
        BitstampAdapter(),
        DeribitAdapter(),
    ]


def get_phase3_sources() -> list[SourceAdapter]:
    sources: list[SourceAdapter] = []
    if settings.glassnode_api_key:
        sources.append(GlassnodeAdapter())
    sources.append(CoinMetricsAdapter())
    return sources


def get_active_sources() -> list[SourceAdapter]:
    return [
        *get_phase1_sources(),
        *get_phase2_sources(),
        *get_phase3_sources(),
    ]


def get_all_sources() -> list[SourceAdapter]:
    return [
        *get_phase1_sources(),
        *get_phase2_sources(),
        GlassnodeAdapter(),
        CoinMetricsAdapter(),
    ]


def get_source_map() -> dict[str, SourceAdapter]:
    return {source.source_id: source for source in get_all_sources()}
