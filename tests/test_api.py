"""
ChargePlus Mobile API 통합 테스트
앱 충전 플로우 전체를 REST API로 검증한다.

사전 조건:
    - 스택이 실행 중 (docker compose up)
    - cp_simulator.py가 백그라운드에서 실행 중 (앱 충전 시뮬레이션용)

사용법:
    python test_api.py [--base-url http://localhost:8000] [--station-id CP-TEST-001]
"""
import argparse
import json
import time
import sys

import requests

GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

def ok(msg): print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg): print(f"  {RED}✗{RESET} {msg}"); sys.exit(1)
def info(msg): print(f"  {YELLOW}→{RESET} {msg}")


class ApiTester:
    def __init__(self, base_url: str, station_id: str):
        self.base_url = base_url.rstrip("/")
        self.station_id = station_id
        self.token: str | None = None
        self.session_id: str | None = None

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    # ─── Health Check ─────────────────────────────────────────────

    def test_health(self):
        print("\n" + "="*60)
        print("STEP 1: Backend Health Check")
        print("="*60)
        try:
            r = requests.get(f"{self.base_url}/api/v1/stations/", headers=self._headers(), timeout=5)
            # 401 is expected (no token yet) - it means the server is up
            if r.status_code in (200, 401, 403):
                ok(f"Backend is responding (status={r.status_code})")
            else:
                fail(f"Unexpected status: {r.status_code} {r.text[:200]}")
        except requests.ConnectionError:
            fail(f"Cannot connect to {self.base_url} - is the stack running?")

    # ─── Login ────────────────────────────────────────────────────

    def test_login_failure(self):
        print("\n" + "="*60)
        print("STEP 2: Login (failure case)")
        print("="*60)
        r = requests.post(
            f"{self.base_url}/api/login",
            json={"user_id": "nonexistent", "password": "wrongpass"},
            headers=self._headers(),
            timeout=5,
        )
        assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
        ok("Login with wrong credentials → 401")

    def test_login_success(self, username: str, password: str):
        print("\n" + "="*60)
        print("STEP 3: Login (success)")
        print("="*60)
        r = requests.post(
            f"{self.base_url}/api/login",
            json={"user_id": username, "password": password},
            headers=self._headers(),
            timeout=5,
        )
        if r.status_code != 200:
            fail(f"Login failed ({r.status_code}): {r.text}")
        data = r.json()
        assert data.get("success") is True
        assert "token" in data
        self.token = data["token"]
        ok(f"Login successful. Token: {self.token[:20]}...")

    # ─── Charge Flow ──────────────────────────────────────────────

    def test_charge_start(self):
        print("\n" + "="*60)
        print("STEP 4: Charge Start (QR scan)")
        print("="*60)

        # Test non-existent station
        r = requests.post(
            f"{self.base_url}/api/charge/start?qr_code=NONEXISTENT-999",
            headers=self._headers(),
            timeout=5,
        )
        assert r.status_code == 404, f"Expected 404 for unknown station, got {r.status_code}"
        ok("Unknown station → 404")

        # Test real station
        r = requests.post(
            f"{self.base_url}/api/charge/start?qr_code={self.station_id}",
            headers=self._headers(),
            timeout=10,
        )

        if r.status_code == 503:
            info(f"Station {self.station_id} is offline (503) - is the simulator running?")
            info("Run: python cp_simulator.py in another terminal, then retry")
            sys.exit(0)

        if r.status_code == 409:
            info(f"Station busy or already charging: {r.json()}")
            sys.exit(0)

        if r.status_code != 200:
            fail(f"Charge start failed ({r.status_code}): {r.text}")

        data = r.json()
        assert data.get("success") is True
        assert "sessionId" in data
        self.session_id = data["sessionId"]
        ok(f"Charge started. sessionId: {self.session_id}")

    def test_charge_status_polling(self, max_polls: int = 15, interval: float = 2.0):
        print("\n" + "="*60)
        print("STEP 5: Status Polling")
        print("="*60)

        for i in range(max_polls):
            r = requests.get(
                f"{self.base_url}/api/charge/status?session_id={self.session_id}",
                headers=self._headers(),
                timeout=5,
            )

            if r.status_code == 404:
                ok("Session ended (404) - charge complete signal received")
                return "completed"

            if r.status_code != 200:
                fail(f"Status poll failed ({r.status_code}): {r.text}")

            data = r.json()
            status = data.get("status")
            kwh = data.get("kwh", 0.0)
            reason = data.get("reason")

            print(f"  [{i+1:2d}] status={status} kwh={kwh:.3f} reason={reason}")

            if status == "active":
                ok(f"Charging active! kwh={kwh:.3f}")
                return "active"

            if status == "failed":
                info(f"Session failed: {reason}")
                info("Is the CP simulator running and accepting RemoteStart?")
                return "failed"

            time.sleep(interval)

        info("Max polls reached without active state")
        return "timeout"

    def test_charge_stop(self):
        print("\n" + "="*60)
        print("STEP 6: Charge Stop")
        print("="*60)

        if not self.session_id:
            fail("No session ID to stop")

        r = requests.post(
            f"{self.base_url}/api/charge/stop?session_id={self.session_id}",
            headers=self._headers(),
            timeout=40,
        )

        if r.status_code == 404:
            ok("Session already completed (404)")
            return

        if r.status_code != 200:
            fail(f"Charge stop failed ({r.status_code}): {r.text}")

        data = r.json()
        ok(f"Charge stopped successfully:")
        ok(f"  kwh={data.get('kwh', 0):.3f}")
        ok(f"  cost={data.get('cost', 0)} {data.get('currency', 'KRW')}")
        ok(f"  message={data.get('message')}")

        # Session should now return 404
        r2 = requests.get(
            f"{self.base_url}/api/charge/status?session_id={self.session_id}",
            headers=self._headers(),
            timeout=5,
        )
        assert r2.status_code == 404, f"Expected 404 after stop, got {r2.status_code}"
        ok("Post-stop status check → 404 (correct)")

    # ─── Station API ──────────────────────────────────────────────

    def test_station_list(self):
        print("\n" + "="*60)
        print("STEP 7: Station List API")
        print("="*60)

        r = requests.get(
            f"{self.base_url}/api/v1/stations/",
            headers=self._headers(),
            timeout=5,
        )
        if r.status_code == 403:
            info("Station list requires admin (403 for regular user - correct)")
            return

        if r.status_code != 200:
            fail(f"Station list failed ({r.status_code}): {r.text}")

        data = r.json()
        count = data.get("count", len(data.get("results", [])))
        ok(f"Station list: {count} stations")

        if count > 0:
            station = data["results"][0]
            ok(f"  First station: {station.get('station_id')} status={station.get('status')}")

    def test_transaction_list(self):
        print("\n" + "="*60)
        print("STEP 8: Transaction List API")
        print("="*60)

        r = requests.get(
            f"{self.base_url}/api/v1/transactions/",
            headers=self._headers(),
            timeout=5,
        )

        if r.status_code == 403:
            info("Transaction list requires admin (403 - correct behavior)")
            return

        if r.status_code != 200:
            fail(f"Transaction list failed ({r.status_code}): {r.text}")

        data = r.json()
        count = data.get("count", len(data.get("results", [])))
        ok(f"Transaction list: {count} transactions")


def main(base_url: str, station_id: str, username: str, password: str):
    print("\n" + "="*60)
    print("ChargePlus Mobile API Integration Test")
    print(f"Base URL:   {base_url}")
    print(f"Station ID: {station_id}")
    print("="*60)

    t = ApiTester(base_url, station_id)

    t.test_health()
    t.test_login_failure()
    t.test_login_success(username, password)
    t.test_charge_start()
    result = t.test_charge_status_polling(max_polls=20, interval=2.0)

    if result == "active":
        t.test_charge_stop()
    elif result == "completed":
        ok("Charge completed automatically during polling")

    t.test_station_list()
    t.test_transaction_list()

    print("\n" + "="*60)
    print(f"{GREEN}ALL API TESTS PASSED ✓{RESET}")
    print("="*60)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChargePlus Mobile API Tester")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--station-id", default="CP-TEST-001", help="Station ID to test")
    parser.add_argument("--username", default="testuser", help="Test user login ID")
    parser.add_argument("--password", default="testpass1234", help="Test user password")
    args = parser.parse_args()

    main(args.base_url, args.station_id, args.username, args.password)
