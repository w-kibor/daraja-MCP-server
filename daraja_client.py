import os
import time
import base64
import logging
from datetime import datetime
from typing import Optional, Dict, Any

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger('daraja_client')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler('m_pesa_debug.log', encoding='utf-8')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)


class DarajaClient:
    """Client for Safaricom Daraja Sandbox.

    Environment variables loaded from .env:
    - DARAJA_CONSUMER_KEY
    - DARAJA_CONSUMER_SECRET
    - DARAJA_SHORTCODE (defaults to 174379)
    - DARAJA_PASSKEY (sandbox example provided)
    - DARAJA_CALLBACK_URL (optional)
    - DARAJA_BASE_URL (optional, defaults to sandbox)
    """

    def __init__(
        self,
        consumer_key: Optional[str] = None,
        consumer_secret: Optional[str] = None,
        shortcode: Optional[str] = None,
        passkey: Optional[str] = None,
    ) -> None:
        self.consumer_key = consumer_key or os.getenv('DARAJA_CONSUMER_KEY')
        self.consumer_secret = consumer_secret or os.getenv('DARAJA_CONSUMER_SECRET')
        self.shortcode = shortcode or os.getenv('DARAJA_SHORTCODE', '174379')
        # Example sandbox passkey used in Safaricom docs — replace with your account's passkey in production
        self.passkey = passkey or os.getenv('DARAJA_PASSKEY', 'bfb279f9aa9bdbcf1xxxxxxxxxxxxxxxxxxxxxxxxxxxx')
        self.base_url = os.getenv('DARAJA_BASE_URL', 'https://sandbox.safaricom.co.ke')

        self._token: Optional[str] = None
        self._token_expires_at: float = 0

    def _get_timestamp(self) -> str:
        return datetime.utcnow().strftime('%Y%m%d%H%M%S')

    def _generate_password(self, timestamp: str) -> str:
        raw = f"{self.shortcode}{self.passkey}{timestamp}"
        encoded = base64.b64encode(raw.encode('utf-8')).decode('utf-8')
        return encoded

    def _get_oauth(self) -> str:
        if self._token and time.time() < self._token_expires_at - 30:
            return self._token

        if not (self.consumer_key and self.consumer_secret):
            raise RuntimeError('DARAJA_CONSUMER_KEY and DARAJA_CONSUMER_SECRET must be set in .env or passed in')

        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        logger.debug('Requesting OAuth token from %s', url)
        r = requests.get(url, auth=(self.consumer_key, self.consumer_secret), timeout=10)
        r.raise_for_status()
        data = r.json()
        token = data.get('access_token')
        expires_in = int(data.get('expires_in', 3600))
        self._token = token
        self._token_expires_at = time.time() + expires_in
        logger.debug('Obtained OAuth token, expires in %s seconds', expires_in)
        return token

    def simulate_stk_push(self, phone_number: str, amount: int, description: str = 'Payment') -> Dict[str, Any]:
        """Simulate an STK Push to `phone_number` for `amount` KES with `description`.

        - `phone_number`: full international format starting with country code (e.g., 2547XXXXXXXX)
        - `amount`: integer amount in KES
        - `description`: short human-readable transaction description

        Returns the JSON response from Daraja.
        """
        token = self._get_oauth()
        timestamp = self._get_timestamp()
        password = self._generate_password(timestamp)

        callback = os.getenv('DARAJA_CALLBACK_URL', 'https://example.com/mpesa/callback')

        payload = {
            'BusinessShortCode': self.shortcode,
            'Password': password,
            'Timestamp': timestamp,
            'TransactionType': 'CustomerPayBillOnline',
            'Amount': int(amount),
            'PartyA': phone_number,
            'PartyB': self.shortcode,
            'PhoneNumber': phone_number,
            'CallBackURL': callback,
            'AccountReference': description[:12],
            'TransactionDesc': description,
        }

        url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        logger.debug('Sending STK push request to %s payload=%s', url, payload)
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()

    def query_transaction_status(self, checkout_request_id: str) -> Dict[str, Any]:
        """Query status of an STK transaction by `CheckoutRequestID`.

        - `checkout_request_id`: the CheckoutRequestID returned by `simulate_stk_push`.
        """
        token = self._get_oauth()
        timestamp = self._get_timestamp()
        password = self._generate_password(timestamp)

        payload = {
            'BusinessShortCode': self.shortcode,
            'Password': password,
            'Timestamp': timestamp,
            'CheckoutRequestID': checkout_request_id,
        }

        url = f"{self.base_url}/mpesa/stkpushquery/v1/query"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        logger.debug('Querying STK push status for %s', checkout_request_id)
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()

    def generate_test_credentials(self) -> Dict[str, str]:
        """Return canonical Daraja Sandbox test credentials and notes for quick testing.

        Note: Consumer key and secret are account-specific and must be generated in the Safaricom Developer Portal.
        This tool returns the widely-used sandbox `Shortcode` and example `Passkey` used in documentation.
        """
        return {
            'Shortcode': '174379',
            'Passkey': 'bfb279f9aa9bdbcf1xxxxxxxxxxxxxxxxxxxxxxxxxxxx',
            'Notes': 'Use your own `DARAJA_CONSUMER_KEY` and `DARAJA_CONSUMER_SECRET` from the Safaricom dashboard.'
        }

    def register_callback_url(self, url: str) -> Dict[str, Any]:
        """Register a single `url` as both ConfirmationURL and ValidationURL for C2B (sandbox).

        - `url`: publicly reachable HTTPS URL. The sandbox can use ngrok-forwarded URLs.
        """
        token = self._get_oauth()
        payload = {
            'ShortCode': self.shortcode,
            'ResponseType': 'Completed',
            'ConfirmationURL': url,
            'ValidationURL': url,
        }
        url_api = f"{self.base_url}/mpesa/c2b/v1/registerurl"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        logger.debug('Registering callback URL %s', url)
        r = requests.post(url_api, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()


# Hyper-explicit tool metadata for MCP exposure. Each tool lists its exact parameter names and formats.
TOOLS_METADATA = {
    'simulate_stk_push': {
        'description': (
            'simulate_stk_push(phone_number, amount, description): Trigger an STK Push via Daraja Sandbox. '
            'phone_number must be E.164 (e.g., 2547XXXXXXXX). amount must be integer KES. description is a short string.'
        ),
        'args': {
            'phone_number': 'string, E.164 format (e.g., 2547XXXXXXXX)',
            'amount': 'integer, KES',
            'description': 'string, short transaction description',
        }
    },
    'query_transaction_status': {
        'description': (
            'query_transaction_status(checkout_request_id): Query the status of an STK push using CheckoutRequestID.'
        ),
        'args': {
            'checkout_request_id': 'string, CheckoutRequestID returned by simulate_stk_push'
        }
    },
    'generate_test_credentials': {
        'description': 'generate_test_credentials(): Return sandbox Shortcode and example Passkey for quick testing.',
        'args': {}
    },
    'register_callback_url': {
        'description': (
            'register_callback_url(url): Register a single HTTPS `url` for both ConfirmationURL and ValidationURL '
            'for C2B/LNMO in the Daraja sandbox. url must be publicly reachable.'
        ),
        'args': {
            'url': 'string, HTTPS public URL to receive Daraja callbacks'
        }
    }
}
