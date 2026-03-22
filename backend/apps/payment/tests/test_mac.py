"""
MAC 서명 단위 테스트.
C++ mynetwork.cpp 로직과 동일한 결과를 생성하는지 검증.
"""
import hashlib
import json

from django.test import TestCase

from apps.payment.services.mac import generate_mac, make_create_order_mac_fields, make_refund_mac_fields


class MACGenerationTest(TestCase):
    """MAC 생성 알고리즘 테스트."""

    SECRET_KEY = '6ca6af4578753e1afae2eb864f8aa288'
    ACCESS_CODE = 'DNHXPHRNMZ'
    MERCHANT_ID = '114743'

    def _expected_mac(self, fields: dict, restore_mattec: bool = False) -> str:
        """동일한 알고리즘으로 MAC 직접 계산 (검증용)."""
        s = json.dumps(fields, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        s = s.replace('":', '=')
        s = s.replace(',', '&')
        s = s.replace(' ', '')
        s = s.replace('{', '')
        s = s.replace('}', '')
        s = s.replace('"', '')
        if restore_mattec:
            s = s.replace('MATTEC', 'MA TT EC')
        s = self.SECRET_KEY + s
        return hashlib.md5(s.encode('utf-8')).hexdigest().upper()

    def test_create_order_mac_basic(self):
        """create-order MAC 기본 생성 테스트."""
        fields = make_create_order_mac_fields(
            amount=100000,
            customer_id='0108230311',
            customer_name='TEST.CHUHANG',
            access_code=self.ACCESS_CODE,
            merchant_id=self.MERCHANT_ID,
            order_info='MA TT EC372855',
            order_reference='6VQRTEST12345',
            return_url='https://beemate.co.kr:8080/return_url',
            cancel_url='https://beemate.co.kr:8080/cancel_url',
            ip_address='14.169.12.117',
        )
        result = generate_mac(fields, self.SECRET_KEY, restore_mattec=True)
        expected = self._expected_mac(fields, restore_mattec=True)
        self.assertEqual(result, expected)
        self.assertEqual(len(result), 32)  # MD5 hex = 32 chars
        self.assertEqual(result, result.upper())

    def test_create_order_mac_with_station_id(self):
        """ChargePlus station_id를 사용한 create-order MAC 테스트."""
        fields = make_create_order_mac_fields(
            amount=100000,
            customer_id='testuser',
            customer_name='Test User',
            access_code=self.ACCESS_CODE,
            merchant_id=self.MERCHANT_ID,
            order_info='MA TT EC CP001',
            order_reference='CP17432123456789',
            return_url='https://chargeplus.kr/api/payment/return/',
            cancel_url='https://chargeplus.kr/api/payment/cancel/',
            ip_address='192.168.1.1',
        )
        result = generate_mac(fields, self.SECRET_KEY, restore_mattec=True)
        expected = self._expected_mac(fields, restore_mattec=True)
        self.assertEqual(result, expected)

    def test_refund_mac(self):
        """refund MAC 생성 테스트."""
        fields = make_refund_mac_fields(
            txn_amount=50000,
            access_code=self.ACCESS_CODE,
            merchant_id=self.MERCHANT_ID,
            transaction_reference_id='MBTEST12345',
            trans_date='22032026',
        )
        result = generate_mac(fields, self.SECRET_KEY)
        expected = self._expected_mac(fields)
        self.assertEqual(result, expected)

    def test_mac_deterministic(self):
        """동일한 입력에 대해 항상 같은 MAC을 생성하는지 검증."""
        fields = make_create_order_mac_fields(
            amount=200000,
            customer_id='user1',
            customer_name='User One',
            access_code=self.ACCESS_CODE,
            merchant_id=self.MERCHANT_ID,
            order_info='MA TT EC CP002',
            order_reference='CP99887766554433',
            return_url='https://chargeplus.kr/api/payment/return/',
            cancel_url='https://chargeplus.kr/api/payment/cancel/',
            ip_address='1.2.3.4',
        )
        mac1 = generate_mac(fields, self.SECRET_KEY, restore_mattec=True)
        mac2 = generate_mac(fields, self.SECRET_KEY, restore_mattec=True)
        self.assertEqual(mac1, mac2)

    def test_mac_changes_with_different_amount(self):
        """금액이 다르면 MAC이 달라지는지 검증 (MAC 위변조 방지 확인)."""
        base_fields = dict(
            customer_id='user1', customer_name='User', access_code=self.ACCESS_CODE,
            merchant_id=self.MERCHANT_ID, order_info='MA TT EC CP001',
            order_reference='CP111', return_url='https://r.url', cancel_url='https://c.url',
            ip_address='1.1.1.1',
        )
        f1 = make_create_order_mac_fields(amount=100000, **base_fields)
        f2 = make_create_order_mac_fields(amount=200000, **base_fields)
        mac1 = generate_mac(f1, self.SECRET_KEY, restore_mattec=True)
        mac2 = generate_mac(f2, self.SECRET_KEY, restore_mattec=True)
        self.assertNotEqual(mac1, mac2)

    def test_mac_field_order_independent(self):
        """필드 딕셔너리 삽입 순서에 관계없이 동일한 MAC을 생성하는지 검증."""
        fields_a = {
            'amount': 100000, 'access_code': self.ACCESS_CODE,
            'currency': 'VND', 'cancel_url': 'https://c.url',
        }
        fields_b = {
            'cancel_url': 'https://c.url', 'currency': 'VND',
            'access_code': self.ACCESS_CODE, 'amount': 100000,
        }
        self.assertEqual(
            generate_mac(fields_a, self.SECRET_KEY),
            generate_mac(fields_b, self.SECRET_KEY),
        )
