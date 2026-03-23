"""
MB Paygate API 클라이언트.

MB_SANDBOX=true이면 sandbox URL 사용.
각 메서드에서 MAC 자동 생성 후 requests.post 호출.
"""
import logging
from datetime import datetime

import requests
from django.conf import settings

from .mac import (
    generate_mac,
    make_create_order_mac_fields,
    make_refund_mac_fields,
    make_inquiry_mac_fields,
)

logger = logging.getLogger(__name__)

SANDBOX_BASE = 'https://api-sandbox.mbbank.com.vn/pg-paygate/ite-pg-paygate/paygate'
PROD_BASE = 'https://BE.mbbank.com.vn/pg-paygate/paygate'  # 운영 URL (추후 확인 필요)


class MBPaygateClient:
    """MB Paygate REST API 래퍼."""

    def __init__(self):
        self.secret_key = settings.MB_SECRET_KEY
        self.access_code = settings.MB_ACCESS_CODE
        self.merchant_id = settings.MB_MERCHANT_ID
        self.sandbox = getattr(settings, 'MB_SANDBOX', True)
        self.base_url = SANDBOX_BASE if self.sandbox else PROD_BASE

    def create_order(
        self,
        order_reference: str,
        amount: int,
        station_id: str,
        customer_id: str,
        customer_name: str,
        ip_address: str,
        return_url: str,
        cancel_url: str,
    ) -> dict:
        """
        create-order API 호출.

        Returns:
            dict with keys: qr_url, payment_url, error_code, trans_date
        """
        order_info = f"MA TT EC {station_id}"
        trans_date = datetime.now().strftime('%d%m%Y')

        mac_fields = make_create_order_mac_fields(
            amount=amount,
            customer_id=customer_id,
            customer_name=customer_name,
            access_code=self.access_code,
            merchant_id=self.merchant_id,
            order_info=order_info,
            order_reference=order_reference,
            return_url=return_url,
            cancel_url=cancel_url,
            ip_address=ip_address,
        )
        mac = generate_mac(mac_fields, self.secret_key, restore_mattec=True)

        payload = {
            **mac_fields,
            "mac_type": "MD5",
            "mac": mac,
            "device": "",
            "merchant_user_reference": "",
            "token_issuer_code": "",
            "token": "",
        }

        url = f"{self.base_url}/v2/create-order"
        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"MB create-order response for {order_reference}: {data}")
            data['trans_date'] = trans_date
            return data
        except requests.RequestException as e:
            logger.error(f"MB create-order request failed for {order_reference}: {e}")
            return {'error_code': 'CONN_ERR', 'trans_date': trans_date}

    def refund(
        self,
        txn_amount: int,
        transaction_reference_id: str,
        trans_date: str,
    ) -> dict:
        """
        refund API 호출.

        Returns:
            dict with key: error_code
        """
        mac_fields = make_refund_mac_fields(
            txn_amount=txn_amount,
            access_code=self.access_code,
            merchant_id=self.merchant_id,
            transaction_reference_id=transaction_reference_id,
            trans_date=trans_date,
        )
        mac = generate_mac(mac_fields, self.secret_key)

        payload = {
            **mac_fields,
            "mac_type": "MD5",
            "mac": mac,
        }

        url = f"{self.base_url}/refund/single"
        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"MB refund response for {transaction_reference_id}: {data}")
            return data
        except requests.RequestException as e:
            logger.error(f"MB refund request failed for {transaction_reference_id}: {e}")
            return {'error_code': 'CONN_ERR'}

    def inquiry(
        self,
        order_reference: str,
        pay_date: str = '',
    ) -> dict:
        """
        거래 조회 API 호출.

        Returns:
            dict with keys: error_code, status, ...
        """
        if not pay_date:
            pay_date = datetime.now().strftime('%d%m%Y')

        mac_fields = make_inquiry_mac_fields(
            merchant_id=self.merchant_id,
            order_reference=order_reference,
            pg_transaction_reference='',
            pay_date=pay_date,
        )
        mac = generate_mac(mac_fields, self.secret_key)

        payload = {
            **mac_fields,
            "mac_type": "MD5",
            "mac": mac,
        }

        url = f"{self.base_url}/detail"
        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"MB inquiry response for {order_reference}: {data}")
            return data
        except requests.RequestException as e:
            logger.error(f"MB inquiry request failed for {order_reference}: {e}")
            return {'error_code': 'CONN_ERR'}
