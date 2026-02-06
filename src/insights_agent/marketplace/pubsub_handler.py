"""Pub/Sub message handler for Google Cloud Marketplace events."""

import base64
import json
import logging
from typing import Any

from insights_agent.marketplace.models import ProcurementEvent
from insights_agent.marketplace.service import ProcurementService, get_procurement_service

logger = logging.getLogger(__name__)


class PubSubHandler:
    """Handler for Pub/Sub push messages from Google Cloud Marketplace.

    This handler:
    - Decodes and validates incoming push messages
    - Dispatches events to the ProcurementService
    """

    def __init__(
        self,
        procurement_service: ProcurementService | None = None,
    ) -> None:
        """Initialize the Pub/Sub handler.

        Args:
            procurement_service: Service for processing events.
        """
        self._procurement_service = procurement_service or get_procurement_service()

    def _decode_message(self, data: bytes) -> dict[str, Any]:
        """Decode a Pub/Sub message payload.

        Args:
            data: Raw message data (base64 encoded JSON).

        Returns:
            Decoded message as dictionary.
        """
        try:
            decoded = base64.b64decode(data).decode("utf-8")
            return json.loads(decoded)
        except (ValueError, json.JSONDecodeError) as e:
            logger.error("Failed to decode message: %s", e)
            raise

    def _parse_event(self, message_data: dict[str, Any]) -> ProcurementEvent:
        """Parse a procurement event from message data.

        Args:
            message_data: Decoded message data.

        Returns:
            ProcurementEvent instance.
        """
        return ProcurementEvent(**message_data)

    async def handle_push_message(self, push_body: dict[str, Any]) -> bool:
        """Handle a push-style Pub/Sub message (for HTTP endpoints).

        Args:
            push_body: The push message body from Pub/Sub.

        Returns:
            True if processed successfully, False otherwise.
        """
        try:
            message = push_body.get("message", {})
            data = message.get("data", "")

            if not data:
                logger.warning("Empty message data received")
                return False

            # Decode base64 data
            decoded_data = base64.b64decode(data).decode("utf-8")
            event_data = json.loads(decoded_data)

            event = self._parse_event(event_data)
            await self._procurement_service.process_event(event)
            return True

        except Exception as e:
            logger.exception("Error processing push message: %s", e)
            return False


# Global handler instance
_pubsub_handler: PubSubHandler | None = None


def get_pubsub_handler() -> PubSubHandler:
    """Get the global Pub/Sub handler instance.

    Returns:
        PubSubHandler instance.
    """
    global _pubsub_handler
    if _pubsub_handler is None:
        _pubsub_handler = PubSubHandler()
    return _pubsub_handler
