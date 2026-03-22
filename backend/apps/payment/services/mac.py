"""
MB Paygate MAC 서명 유틸리티.

C++ mynetwork.cpp의 MAC 생성 로직을 Python으로 정확히 포팅.
Qt의 QJsonObject는 키를 알파벳 순으로 저장하므로 sort_keys=True로 직렬화.

알고리즘:
1. JSON 객체를 compact 직렬화 (키 알파벳 순)
2. '":' → '=' 치환
3. ',' → '&' 치환
4. 공백, '{', '}', '"' 제거
5. (create-order만) 'MATTEC' → 'MA TT EC' 복원
6. hashkey prefix 추가
7. MD5 → 대문자 hex
"""
import hashlib
import json


def generate_mac(fields: dict, secret_key: str, restore_mattec: bool = False) -> str:
    """
    MB Paygate MAC 생성.

    Args:
        fields: MAC 계산 대상 필드 딕셔너리
        secret_key: MB_SECRET_KEY (hashkey)
        restore_mattec: True이면 create-order용 MATTEC 복원 적용 (order_info에 공백 포함 시)

    Returns:
        대문자 MD5 hex 문자열
    """
    # 1. Compact JSON, 알파벳 순 키 (Qt QJsonObject 동작과 동일)
    s = json.dumps(fields, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

    # 2. '":' → '='
    s = s.replace('":', '=')

    # 3. ',' → '&'
    s = s.replace(',', '&')

    # 4. 공백/중괄호/따옴표 제거
    s = s.replace(' ', '')
    s = s.replace('{', '')
    s = s.replace('}', '')
    s = s.replace('"', '')

    # 5. create-order: order_info의 공백 복원 (MATTEC → MA TT EC)
    if restore_mattec:
        s = s.replace('MATTEC', 'MA TT EC')

    # 6. hashkey prefix
    s = secret_key + s

    # 7. MD5 → 대문자 hex
    return hashlib.md5(s.encode('utf-8')).hexdigest().upper()


def make_create_order_mac_fields(
    amount: int,
    customer_id: str,
    customer_name: str,
    access_code: str,
    merchant_id: str,
    order_info: str,
    order_reference: str,
    return_url: str,
    cancel_url: str,
    ip_address: str,
) -> dict:
    """create-order MAC 계산 대상 필드를 반환."""
    return {
        "amount": amount,
        "currency": "VND",
        "customerID": customer_id,
        "customerName": customer_name,
        "access_code": access_code,
        "merchant_id": merchant_id,
        "order_info": order_info,
        "order_reference": order_reference,
        "return_url": return_url,
        "cancel_url": cancel_url,
        "pay_type": "pay",
        "ip_address": ip_address,
        "payment_method": "QR",
    }


def make_refund_mac_fields(
    txn_amount: int,
    access_code: str,
    merchant_id: str,
    transaction_reference_id: str,
    trans_date: str,
) -> dict:
    """refund MAC 계산 대상 필드를 반환."""
    return {
        "txn_amount": txn_amount,
        "desc": "refund",
        "access_code": access_code,
        "merchant_id": merchant_id,
        "transaction_reference_id": transaction_reference_id,
        "trans_date": trans_date,
    }


def make_inquiry_mac_fields(
    merchant_id: str,
    order_reference: str,
    pg_transaction_reference: str,
    pay_date: str,
) -> dict:
    """inquiry MAC 계산 대상 필드를 반환."""
    return {
        "merchant_id": merchant_id,
        "order_reference": order_reference,
        "pg_transaction_reference": pg_transaction_reference,
        "pay_date": pay_date,
    }
