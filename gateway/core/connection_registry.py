import asyncio
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionRegistry:
    """
    In-memory registry of active WebSocket connections.
    Maps station_id -> WebSocket and tracks pending command futures.
    """

    def __init__(self):
        self._connections: dict[str, WebSocket] = {}
        self._pending_cmds: dict[str, asyncio.Future] = {}

    async def register(self, station_id: str, ws: WebSocket) -> None:
        """Register a new WebSocket connection for the given station."""
        if station_id in self._connections:
            logger.warning(f"Station {station_id} already registered; replacing connection.")
        self._connections[station_id] = ws
        logger.info(f"Station {station_id} connected. Total: {len(self._connections)}")

    async def unregister(self, station_id: str) -> None:
        """Remove a station's WebSocket connection from the registry."""
        if station_id in self._connections:
            del self._connections[station_id]
            logger.info(f"Station {station_id} disconnected. Total: {len(self._connections)}")
        # Clean up any pending commands for this station
        pending_to_cancel = [
            msg_id for msg_id in list(self._pending_cmds.keys())
        ]
        # We cannot filter by station here easily, but futures will resolve or timeout naturally.

    async def send(self, station_id: str, message: str) -> bool:
        """
        Send a text message to the given station's WebSocket.
        Returns True on success, False if station not connected.
        """
        ws = self._connections.get(station_id)
        if ws is None:
            logger.warning(f"Cannot send to {station_id}: not connected.")
            return False
        try:
            await ws.send_text(message)
            return True
        except Exception as e:
            logger.error(f"Error sending to {station_id}: {e}")
            await self.unregister(station_id)
            return False

    def is_connected(self, station_id: str) -> bool:
        """Check if a station is currently connected."""
        return station_id in self._connections

    def set_pending_cmd(self, msg_id: str, future: asyncio.Future) -> None:
        """Register a pending command future awaiting a CP response."""
        self._pending_cmds[msg_id] = future

    def resolve_pending_cmd(self, msg_id: str, payload: dict) -> bool:
        """
        Resolve a pending command future with the given payload.
        Returns True if a pending command was found and resolved.
        """
        future = self._pending_cmds.pop(msg_id, None)
        if future is not None and not future.done():
            future.set_result(payload)
            return True
        return False

    def has_pending_cmd(self, msg_id: str) -> bool:
        """Check if there is a pending command future for the given msg_id."""
        return msg_id in self._pending_cmds

    def cancel_pending_cmd(self, msg_id: str) -> None:
        """Cancel a pending command future."""
        future = self._pending_cmds.pop(msg_id, None)
        if future is not None and not future.done():
            future.cancel()

    @property
    def connected_stations(self) -> list[str]:
        """Return list of currently connected station IDs."""
        return list(self._connections.keys())


# Singleton instance
registry = ConnectionRegistry()
