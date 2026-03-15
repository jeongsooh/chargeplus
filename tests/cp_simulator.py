"""
OCPP 1.6 Charge Point Simulator
충전기를 시뮬레이션하여 Gateway와의 OCPP 메시지 통신을 테스트한다.

사용법:
    python cp_simulator.py [--station-id CP-TEST-001] [--host localhost] [--port 9000]
"""
import asyncio
import json
import logging
import uuid
import argparse
from datetime import datetime, timezone

import websockets

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

CALL = 2
CALL_RESULT = 3
CALL_ERROR = 4


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def make_call(action: str, payload: dict) -> tuple[str, str]:
    msg_id = str(uuid.uuid4())
    return msg_id, json.dumps([CALL, msg_id, action, payload])


class ChargePointSimulator:
    def __init__(self, station_id: str, host: str, port: int):
        self.station_id = station_id
        self.ws_url = f"ws://{host}:{port}/ocpp/1.6/{station_id}"
        self.ws = None
        self.pending: dict[str, asyncio.Future] = {}
        self.transaction_id: int | None = None
        self.meter_value = 1_000_000  # Wh

    async def connect(self):
        logger.info(f"Connecting to {self.ws_url}")
        self.ws = await websockets.connect(
            self.ws_url,
            subprotocols=["ocpp1.6"],
            ping_interval=30,
            ping_timeout=10,
        )
        logger.info(f"Connected. Subprotocol: {self.ws.subprotocol}")
        return self

    async def disconnect(self):
        if self.ws:
            await self.ws.close()
            logger.info("Disconnected")

    async def _send(self, action: str, payload: dict) -> dict:
        """Send a CALL and wait for CALL_RESULT."""
        msg_id, raw = make_call(action, payload)
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self.pending[msg_id] = future

        await self.ws.send(raw)
        logger.info(f"  → [{action}] {json.dumps(payload)}")

        try:
            result = await asyncio.wait_for(future, timeout=15.0)
            logger.info(f"  ← [{action}Response] {json.dumps(result)}")
            return result
        except asyncio.TimeoutError:
            logger.error(f"  ✗ Timeout waiting for {action} response")
            del self.pending[msg_id]
            raise

    async def _listen(self):
        """Background task: receive messages from CSMS and resolve pending futures."""
        async for raw in self.ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON: {raw}")
                continue

            msg_type = msg[0]

            if msg_type == CALL_RESULT:
                _, msg_id, payload = msg
                if msg_id in self.pending:
                    self.pending.pop(msg_id).set_result(payload)
                else:
                    logger.warning(f"Unexpected CALL_RESULT for msg_id={msg_id}")

            elif msg_type == CALL_ERROR:
                _, msg_id, error_code, description, *_ = msg
                logger.error(f"  ✗ CALL_ERROR: {error_code} - {description}")
                if msg_id in self.pending:
                    self.pending.pop(msg_id).set_exception(
                        Exception(f"{error_code}: {description}")
                    )

            elif msg_type == CALL:
                # CSMS-initiated command (downstream)
                _, msg_id, action, payload = msg
                logger.info(f"  ← [CSMS→CP] {action}: {json.dumps(payload)}")
                await self._handle_csms_command(msg_id, action, payload)

    async def _handle_csms_command(self, msg_id: str, action: str, payload: dict):
        """Respond to CSMS-initiated commands."""
        if action == "RemoteStartTransaction":
            response = {"status": "Accepted"}
            await self.ws.send(json.dumps([CALL_RESULT, msg_id, response]))
            logger.info(f"  → [RemoteStartTransactionResponse] Accepted")
            # Simulate vehicle connecting after 1 second
            asyncio.create_task(self._simulate_vehicle_connect(payload))

        elif action == "RemoteStopTransaction":
            response = {"status": "Accepted"}
            await self.ws.send(json.dumps([CALL_RESULT, msg_id, response]))
            logger.info(f"  → [RemoteStopTransactionResponse] Accepted")
            # Simulate stopping after 0.5 seconds
            asyncio.create_task(self._simulate_vehicle_stop())

        elif action == "Reset":
            response = {"status": "Accepted"}
            await self.ws.send(json.dumps([CALL_RESULT, msg_id, response]))
            logger.info(f"  → [ResetResponse] Accepted (simulated)")

        elif action == "ChangeConfiguration":
            response = {"status": "Accepted"}
            await self.ws.send(json.dumps([CALL_RESULT, msg_id, response]))
            logger.info(f"  → [ChangeConfigurationResponse] Accepted")

        elif action == "GetConfiguration":
            response = {
                "configurationKey": [
                    {"key": "HeartbeatInterval", "readonly": False, "value": "60"},
                    {"key": "MeterValueSampleInterval", "readonly": False, "value": "30"},
                    {"key": "NumberOfConnectors", "readonly": True, "value": "1"},
                ],
                "unknownKey": []
            }
            await self.ws.send(json.dumps([CALL_RESULT, msg_id, response]))
            logger.info(f"  → [GetConfigurationResponse]")

        elif action == "TriggerMessage":
            response = {"status": "Accepted"}
            await self.ws.send(json.dumps([CALL_RESULT, msg_id, response]))

        else:
            # Unknown command
            response = {"status": "NotImplemented"}
            await self.ws.send(json.dumps([CALL_RESULT, msg_id, response]))
            logger.info(f"  → [{action}Response] NotImplemented")

    async def _simulate_vehicle_connect(self, remote_start_payload: dict):
        """Called after RemoteStartTransaction - simulate vehicle connecting."""
        await asyncio.sleep(1.0)
        connector_id = remote_start_payload.get("connectorId", 1)
        id_tag = remote_start_payload.get("idTag", "APP-1")

        # StatusNotification: Preparing
        await self._send("StatusNotification", {
            "connectorId": connector_id,
            "errorCode": "NoError",
            "status": "Preparing",
            "timestamp": utcnow(),
        })

        await asyncio.sleep(0.5)

        # StatusNotification: Charging
        await self._send("StatusNotification", {
            "connectorId": connector_id,
            "errorCode": "NoError",
            "status": "Charging",
            "timestamp": utcnow(),
        })

        # StartTransaction
        result = await self._send("StartTransaction", {
            "connectorId": connector_id,
            "idTag": id_tag,
            "meterStart": self.meter_value,
            "timestamp": utcnow(),
        })
        self.transaction_id = result.get("transactionId")
        logger.info(f"  ✓ Transaction started: ID={self.transaction_id}")

    async def _simulate_vehicle_stop(self):
        """Send StopTransaction."""
        await asyncio.sleep(0.5)
        if self.transaction_id is None:
            logger.warning("No active transaction to stop")
            return

        # Final MeterValues before stopping
        self.meter_value += 5000  # +5 kWh
        await self._send("MeterValues", {
            "connectorId": 1,
            "transactionId": self.transaction_id,
            "meterValue": [{
                "timestamp": utcnow(),
                "sampledValue": [{
                    "value": str(self.meter_value),
                    "context": "Transaction.End",
                    "format": "Raw",
                    "measurand": "Energy.Active.Import.Register",
                    "unit": "Wh",
                }]
            }]
        })

        result = await self._send("StopTransaction", {
            "transactionId": self.transaction_id,
            "idTag": "APP-1",
            "meterStop": self.meter_value,
            "timestamp": utcnow(),
            "reason": "Remote",
        })
        logger.info(f"  ✓ Transaction stopped")
        self.transaction_id = None

        # StatusNotification: Available
        await self._send("StatusNotification", {
            "connectorId": 1,
            "errorCode": "NoError",
            "status": "Available",
            "timestamp": utcnow(),
        })

    async def run_boot_sequence(self):
        """Step 1: Boot sequence (BootNotification + StatusNotification)."""
        print("\n" + "="*60)
        print("STEP 1: Boot Sequence")
        print("="*60)

        result = await self._send("BootNotification", {
            "chargePointVendor": "TestVendor",
            "chargePointModel": "Simulator-1",
            "chargePointSerialNumber": "SIM-001",
            "firmwareVersion": "1.0.0-test",
        })
        assert result["status"] == "Accepted", f"Boot rejected: {result}"
        interval = result.get("interval", 60)
        print(f"  ✓ BootNotification: Accepted, interval={interval}s")

        # Station-wide status
        await self._send("StatusNotification", {
            "connectorId": 0,
            "errorCode": "NoError",
            "status": "Available",
            "timestamp": utcnow(),
        })

        # Connector 1 status
        await self._send("StatusNotification", {
            "connectorId": 1,
            "errorCode": "NoError",
            "status": "Available",
            "timestamp": utcnow(),
        })
        print("  ✓ StatusNotification: Available")

    async def run_rfid_charge_cycle(self):
        """Step 2: Full RFID charge cycle (Authorize → Start → MeterValues → Stop)."""
        print("\n" + "="*60)
        print("STEP 2: RFID Charge Cycle")
        print("="*60)

        # Authorize
        result = await self._send("Authorize", {"idTag": "RFID-TEST-001"})
        auth_status = result.get("idTagInfo", {}).get("status")
        print(f"  ✓ Authorize: status={auth_status}")

        if auth_status not in ("Accepted", "Invalid"):
            logger.warning(f"Unexpected auth status: {auth_status}")

        # StatusNotification: Preparing
        await self._send("StatusNotification", {
            "connectorId": 1, "errorCode": "NoError",
            "status": "Preparing", "timestamp": utcnow(),
        })

        # StartTransaction
        result = await self._send("StartTransaction", {
            "connectorId": 1,
            "idTag": "RFID-TEST-001",
            "meterStart": self.meter_value,
            "timestamp": utcnow(),
        })
        tx_id = result.get("transactionId")
        tx_status = result.get("idTagInfo", {}).get("status")
        print(f"  ✓ StartTransaction: txId={tx_id}, status={tx_status}")

        # StatusNotification: Charging
        await self._send("StatusNotification", {
            "connectorId": 1, "errorCode": "NoError",
            "status": "Charging", "timestamp": utcnow(),
        })

        # MeterValues (3 samples, 1kWh each)
        for i in range(3):
            await asyncio.sleep(0.3)
            self.meter_value += 1000  # +1 kWh
            await self._send("MeterValues", {
                "connectorId": 1,
                "transactionId": tx_id,
                "meterValue": [{
                    "timestamp": utcnow(),
                    "sampledValue": [{
                        "value": str(self.meter_value),
                        "context": "Sample.Periodic",
                        "format": "Raw",
                        "measurand": "Energy.Active.Import.Register",
                        "unit": "Wh",
                    }]
                }]
            })
        print(f"  ✓ MeterValues: 3 samples, total {self.meter_value/1000:.1f} kWh")

        # StopTransaction
        self.meter_value += 500
        result = await self._send("StopTransaction", {
            "transactionId": tx_id,
            "idTag": "RFID-TEST-001",
            "meterStop": self.meter_value,
            "timestamp": utcnow(),
            "reason": "Local",
        })
        print(f"  ✓ StopTransaction: status={result.get('idTagInfo', {}).get('status')}")

        # StatusNotification: Available
        await self._send("StatusNotification", {
            "connectorId": 1, "errorCode": "NoError",
            "status": "Available", "timestamp": utcnow(),
        })

    async def run_heartbeat(self, count: int = 2):
        """Step 3: Heartbeat."""
        print("\n" + "="*60)
        print(f"STEP 3: Heartbeat ({count}x)")
        print("="*60)
        for i in range(count):
            result = await self._send("Heartbeat", {})
            print(f"  ✓ Heartbeat {i+1}: currentTime={result.get('currentTime')}")
            if i < count - 1:
                await asyncio.sleep(0.5)

    async def run_all(self):
        """Run all test steps."""
        listen_task = asyncio.create_task(self._listen())
        try:
            await self.run_boot_sequence()
            await self.run_heartbeat(2)
            await self.run_rfid_charge_cycle()

            print("\n" + "="*60)
            print("ALL OCPP TESTS PASSED ✓")
            print("="*60)
            print(f"  Station: {self.station_id}")
            print(f"  Gateway: {self.ws_url}")
            print()
        finally:
            listen_task.cancel()
            try:
                await listen_task
            except asyncio.CancelledError:
                pass


async def main(station_id: str, host: str, port: int, listen_mode: bool = False):
    sim = ChargePointSimulator(station_id, host, port)
    try:
        await sim.connect()
        if listen_mode:
            # Boot sequence only, then keep listening for CSMS commands (API test mode)
            listen_task = asyncio.create_task(sim._listen())
            try:
                await sim.run_boot_sequence()
                logger.info("Listen mode: ready for remote commands (Ctrl+C to stop)")
                await asyncio.sleep(3600)  # Keep alive for 1 hour
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
            finally:
                listen_task.cancel()
                try:
                    await listen_task
                except asyncio.CancelledError:
                    pass
        else:
            await sim.run_all()
    finally:
        await sim.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OCPP 1.6 Charge Point Simulator")
    parser.add_argument("--station-id", default="CP-TEST-001", help="Station ID")
    parser.add_argument("--host", default="localhost", help="Gateway host")
    parser.add_argument("--port", type=int, default=9000, help="Gateway port")
    parser.add_argument("--listen", action="store_true", help="Listen mode: boot only, wait for remote commands")
    args = parser.parse_args()

    asyncio.run(main(args.station_id, args.host, args.port, listen_mode=args.listen))
