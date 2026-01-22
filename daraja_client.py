import os
import time
import base64
import logging
from datetime import datetime
from typing import Optional, Dict, Any

import requests
from dotenv import load_dotenv
import re
import difflib
from typing import List

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
        # documentation index cache: list of (paragraph, source_url)
        self._docs_index: List[tuple] = []
        self._docs_sources: List[str] = [os.getenv('DARAJA_DOCS_URL', 'https://developer.safaricom.co.ke/')]

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

    # -- Documentation indexing and search -------------------------------------------------
    def _extract_text_paragraphs(self, html: str) -> List[str]:
        # Very small, robust HTML -> text stripper to get paragraphs
        text = re.sub(r'(?is)<script.*?>.*?</script>', '', html)
        text = re.sub(r'(?is)<style.*?>.*?</style>', '', text)
        # Replace common block tags with newlines
        text = re.sub(r'(?i)</?(p|div|h[1-6]|li|br|section|article)[^>]*>', '\n', text)
        # Remove remaining tags
        text = re.sub(r'<[^>]+>', '', text)
        # Collapse whitespace
        text = re.sub(r'\n{2,}', '\n\n', text)
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        return paragraphs

    def _build_docs_index(self) -> None:
        if self._docs_index:
            return
        for src in self._docs_sources:
            try:
                logger.debug('Fetching docs from %s', src)
                r = requests.get(src, timeout=10)
                r.raise_for_status()
                paras = self._extract_text_paragraphs(r.text)
                for p in paras:
                    # keep short paragraphs too
                    self._docs_index.append((p, src))
                logger.info('Indexed %d paragraphs from %s', len(paras), src)
            except Exception as e:
                logger.exception('Failed to fetch docs from %s: %s', src, e)

    def doc_search(self, query: str, top_n: int = 1) -> Dict[str, Any]:
        """Search indexed Daraja docs for the paragraph best matching `query`.

        Returns a dict with `query`, `matches` (list of {'paragraph','source','score'}).
        """
        if not query or not query.strip():
            raise ValueError('query must be a non-empty string')

        # lazy index build (non-blocking attempts with reasonable timeouts)
        if not self._docs_index:
            self._build_docs_index()

        if not self._docs_index:
            return {'query': query, 'matches': [], 'note': 'No documentation indexed; set DARAJA_DOCS_URL or ensure network access.'}

        # Compute similarity using difflib ratio; also boost exact-token matches
        candidates = []
        q = query.lower()
        for para, src in self._docs_index:
            p_low = para.lower()
            ratio = difflib.SequenceMatcher(None, q, p_low).ratio()
            # token overlap boost
            q_tokens = set(re.findall(r"\w+", q))
            p_tokens = set(re.findall(r"\w+", p_low))
            if q_tokens:
                overlap = len(q_tokens & p_tokens) / len(q_tokens)
            else:
                overlap = 0.0
            score = 0.6 * ratio + 0.4 * overlap
            candidates.append((score, para, src))

        candidates.sort(reverse=True, key=lambda t: t[0])
        results = []
        for score, para, src in candidates[:top_n]:
            results.append({'paragraph': para, 'source': src, 'score': round(float(score), 4)})

        return {'query': query, 'matches': results}

    def start_ngrok_and_register(self, port: int = 8000, callback_path: str = '/mpesa/callback', ngrok_auth_token: Optional[str] = None, use_https: bool = True) -> Dict[str, Any]:
        """Start an ngrok HTTPS tunnel to `port` and register `public_url+callback_path` with Daraja.

        - `port`: local port to expose (default 8000)
        - `callback_path`: path appended to the public URL when registering with Daraja
        - `ngrok_auth_token`: optional ngrok auth token (or set NGROK_AUTH_TOKEN env var)
        - `use_https`: whether to prefer an HTTPS tunnel (default True)

        Returns dict: `public_url`, `callback_url`, `register_result`.
        """
        try:
            from pyngrok import ngrok
        except Exception:
            raise RuntimeError('pyngrok is required for ngrok support; install with `pip install pyngrok`')

        # set auth token if provided
        token = ngrok_auth_token or os.getenv('NGROK_AUTH_TOKEN')
        if token:
            try:
                ngrok.set_auth_token(token)
                logger.debug('ngrok auth token set')
            except Exception:
                logger.exception('Failed to set ngrok auth token; proceeding without setting it')

        proto = 'https' if use_https else 'http'
        logger.info('Starting ngrok tunnel for port %s (proto=%s)', port, proto)
        try:
            tunnel = ngrok.connect(port, proto)
        except TypeError:
            # pyngrok older signature fallback
            tunnel = ngrok.connect(port)

        public_url = getattr(tunnel, 'public_url', str(tunnel))
        logger.info('Ngrok tunnel started: %s', public_url)
        callback_url = public_url.rstrip('/') + callback_path

        logger.debug('Registering callback URL %s with Daraja', callback_url)
        reg_res = self.register_callback_url(callback_url)
        return {'public_url': public_url, 'callback_url': callback_url, 'register_result': reg_res}


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
    ,
    'doc_search': {
        'description': 'doc_search(query): Find the paragraph in the official Daraja docs that best answers `query`.',
        'args': {
            'query': 'string, the developer question or phrase to search for',
            'top_n': 'integer, optional, number of top paragraph matches to return (default 1)'
        }
    }
    ,
    'start_ngrok_and_register': {
        'description': (
            'start_ngrok_and_register(port=8000, callback_path="/mpesa/callback", ngrok_auth_token=None): '
            'Start an ngrok tunnel to the local `port` and register the public HTTPS callback URL with Daraja.'
        ),
        'args': {
            'port': 'integer, local port to expose (default 8000)',
            'callback_path': 'string, path appended to public URL when registering (default /mpesa/callback)',
            'ngrok_auth_token': 'string, optional ngrok auth token (or set NGROK_AUTH_TOKEN env var)'
        }
    }
}
