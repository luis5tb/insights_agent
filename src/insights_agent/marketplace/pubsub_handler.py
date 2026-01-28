"""Pub/Sub message handler for Google Cloud Marketplace events."""

import asyncio
import base64
import json
import logging
from typing import Any

from google.cloud import pubsub_v1

from insights_agent.config import get_settings
from insights_agent.marketplace.models import ProcurementEvent
from insights_agent.marketplace.service import ProcurementService, get_procurement_service

logger = logging.getLogger(__name__)


class PubSubHandler:
    """Handler for Pub/Sub messages from Google Cloud Marketplace.

    This handler:
    - Subscribes to the Marketplace Pub/Sub topic
    - Decodes and validates incoming messages
    - Dispatches events to the ProcurementService
    """

    def __init__(
        self,
        procurement_service: ProcurementService | None = None,
        project_id: str | None = None,
        subscription_id: str | None = None,
    ) -> None:
        """Initialize the Pub/Sub handler.

        Args:
            procurement_service: Service for processing events.
            project_id: GCP project ID (uses settings if not provided).
            subscription_id: Pub/Sub subscription ID (uses settings if not provided).
        """
        self._procurement_service = procurement_service or get_procurement_service()
        self._settings = get_settings()
        self._project_id = project_id or self._settings.google_cloud_project
        self._subscription_id = subscription_id or self._get_default_subscription_id()
        self._subscriber: pubsub_v1.SubscriberClient | None = None
        self._streaming_pull_future: Any = None
        self._running = False

    def _get_default_subscription_id(self) -> str:
        """Get the default subscription ID from settings."""
        # Default to a conventional name based on service name
        service_name = self._settings.service_control_service_name
        if service_name:
            return f"{service_name}-marketplace-subscription"
        return "marketplace-procurement-subscription"

    @property
    def subscription_path(self) -> str:
        """Get the full subscription path."""
        if not self._project_id:
            raise ValueError("Project ID not configured")
        return f"projects/{self._project_id}/subscriptions/{self._subscription_id}"

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

    async def handle_message(self, message_data: bytes) -> bool:
        """Handle a single Pub/Sub message.

        Args:
            message_data: Raw message data.

        Returns:
            True if processed successfully, False otherwise.
        """
        try:
            decoded = self._decode_message(message_data)
            event = self._parse_event(decoded)
            await self._procurement_service.process_event(event)
            return True
        except Exception as e:
            logger.exception("Error processing message: %s", e)
            return False

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

    def _callback(self, message: pubsub_v1.subscriber.message.Message) -> None:
        """Callback for processing pulled messages.

        Args:
            message: The Pub/Sub message.
        """
        try:
            decoded = self._decode_message(message.data)
            event = self._parse_event(decoded)

            # Run async handler in event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(
                    self._procurement_service.process_event(event)
                )
            else:
                loop.run_until_complete(
                    self._procurement_service.process_event(event)
                )

            message.ack()
            logger.debug("Acknowledged message: %s", message.message_id)

        except Exception as e:
            logger.exception("Error in message callback: %s", e)
            message.nack()

    def start(self) -> None:
        """Start the Pub/Sub subscriber (pull mode)."""
        if self._running:
            logger.warning("Subscriber already running")
            return

        try:
            self._subscriber = pubsub_v1.SubscriberClient()
            self._streaming_pull_future = self._subscriber.subscribe(
                self.subscription_path,
                callback=self._callback,
            )
            self._running = True
            logger.info("Started Pub/Sub subscriber: %s", self.subscription_path)

        except Exception as e:
            logger.exception("Failed to start subscriber: %s", e)
            raise

    def stop(self) -> None:
        """Stop the Pub/Sub subscriber."""
        if not self._running:
            return

        if self._streaming_pull_future:
            self._streaming_pull_future.cancel()
            self._streaming_pull_future = None

        if self._subscriber:
            self._subscriber.close()
            self._subscriber = None

        self._running = False
        logger.info("Stopped Pub/Sub subscriber")

    @property
    def is_running(self) -> bool:
        """Check if the subscriber is running."""
        return self._running


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
