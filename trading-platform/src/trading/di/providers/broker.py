from __future__ import annotations

import logging

from dishka import Provider, Scope, provide

from trading.broker.base.broker import Broker
from trading.broker.base.broker_stream import BrokerStream
from trading.broker.paper_broker import PaperBroker
from trading.broker.zerodha_broker.kite_client.kite_client import KiteClient
from trading.broker.zerodha_broker.zerodha import ZerodhaBroker
from trading.config.settings import Settings

logger = logging.getLogger(__name__)


class BrokerProvider(Provider):
    """
    Broker and streaming — isolated so a MockBrokerProvider can replace
    this entire provider in tests without touching infrastructure.
    """

    scope = Scope.APP

    @provide
    def kite_client(self, settings: Settings) -> KiteClient:
        return KiteClient(settings.zerodha_api_key)

    @provide
    def broker(self, client: KiteClient, settings: Settings) -> Broker:
        client.set_access_token(settings.zerodha_access_token)
        real_broker = ZerodhaBroker(client)
        if settings.paper_trading:
            logger.info("BrokerProvider: paper trading mode enabled")
            return PaperBroker(real_broker)
        return real_broker

    @provide
    def broker_stream(self, client: KiteClient) -> BrokerStream:
        from trading.broker.zerodha_broker.zerodha_stream import ZerodhaStream

        return ZerodhaStream(client)
