#!/usr/bin/env python3
"""TRU Atlas: read-only standalone explorer; Python 3.10+ standard library only.

No blockchain data files are touched. No consensus changes. No wallet key access.
RPC calls are hardcoded read-only and the caller cannot choose an RPC method.
"""
import argparse
import json
import logging
import os
import re
import sys
import threading
import time
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / 'static'
LOG = logging.getLogger('tru-atlas')
HEX64 = re.compile(r'^[a-fA-F0-9]{64}$')
ADDRESS = re.compile(r'^T[1-9A-HJ-NP-Za-km-z]{33}$')
TOKEN_ID = re.compile(r'^[a-zA-Z0-9_-]{2,128}$')
MAX_JSON = 5_000_000


def load_dotenv(file):
    """Tiny optional .env reader; values are data, NEVER shell-evaluated."""
    if not file.is_file():
        return
    for raw in file.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
            continue
        value = value.strip()
        if value.startswith(('"', "'")) and len(value) >= 2 and value[0] == value[-1]:
            value = value[1:-1]
        os.environ.setdefault(key, value)


class ExplorerError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


class Cache:
    def __init__(self, max_items=192):
        self.data = OrderedDict()
        self.lock = threading.Lock()
        self.max_items = max_items

    def fetch(self, key, ttl, callback):
        now = time.monotonic()
        with self.lock:
            if key in self.data:
                exp, value = self.data[key]
                if exp > now:
                    self.data.move_to_end(key)
                    return value
                del self.data[key]
        value = callback()
        with self.lock:
            self.data[key] = (time.monotonic() + ttl, value)
            self.data.move_to_end(key)
            while len(self.data) > self.max_items:
                self.data.popitem(last=False)
        return value


class Node:
    def __init__(self):
        self.mode = os.getenv('TRU_MODE', 'rpc').strip().lower()
        if self.mode not in ('rpc', 'api', 'demo'):
            raise ValueError('TRU_MODE must be rpc, api or demo')
        self.rpc_url = os.getenv('TRU_RPC_URL', 'http://127.0.0.1:21832/rpc')
        self.api_url = os.getenv('TRU_API_URL', '').rstrip('/')
        self.rpc_token = os.getenv('TRU_RPC_TOKEN', '').strip()
        token_file = os.getenv('TRU_RPC_TOKEN_FILE', '').strip()
        # Load cookie lazily, so Atlas can start before Core does and survive token rotation.
        self.rpc_cookie_path = Path(token_file).expanduser() if token_file else None
        if self.mode == 'api' and not self.api_url:
            raise ValueError('TRU_MODE=api requires TRU_API_URL')
        if self.mode == 'rpc' and not self.rpc_token and not self.rpc_cookie_path:
            LOG.warning('No RPC token supplied: set TRU_RPC_TOKEN or TRU_RPC_TOKEN_FILE')
        if self.mode == 'rpc':
            parts = urlsplit(self.rpc_url)
            if parts.scheme != 'http' or not parts.hostname:
                raise ValueError('RPC must be an HTTP URL')
            if parts.hostname not in ('127.0.0.1', 'localhost', '::1') and os.getenv('TRU_ALLOW_REMOTE_RPC') != '1':
                raise ValueError('Remote RPC disabled. Use SSH tunnel, or explicitly set TRU_ALLOW_REMOTE_RPC=1 on a trusted network.')
        self.cache = Cache()

    def _read_json(self, url, method='GET', payload=None, secret=False):
        headers = {'Accept': 'application/json', 'User-Agent': 'TRU-Atlas/1.1'}
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        if secret:
            token = self.rpc_token
            if self.rpc_cookie_path:
                try:
                    token = self.rpc_cookie_path.read_text(encoding='utf-8').strip()
                except (OSError, UnicodeError):
                    raise ExplorerError('RPC cookie unavailable. Check Core startup and permissions.')
            if not token:
                raise ExplorerError('Missing RPC credential. Set TRU_RPC_TOKEN_FILE or TRU_RPC_TOKEN.')
            headers['Authorization'] = 'Bearer ' + token
        req = Request(url, data=json.dumps(payload).encode() if payload is not None else None,
                      method=method, headers=headers)
        try:
            with urlopen(req, timeout=12) as response:
                if int(response.headers.get('Content-Length', '0')) > MAX_JSON:
                    raise ExplorerError('Upstream response exceeded size limit')
                raw = response.read(MAX_JSON + 1)
                if len(raw) > MAX_JSON:
                    raise ExplorerError('Upstream response exceeded size limit')
                return json.loads(raw)
        except HTTPError as e:
            if e.code == 404:
                raise ExplorerError('Not found on this node', 404) from e
            if e.code in (401, 403):
                LOG.error('Upstream authentication/authorization error (%s)', e.code)
                raise ExplorerError('Node refused access. Check server RPC credentials.', 502) from e
            raise ExplorerError('Upstream returned HTTP ' + str(e.code)) from e
        except (URLError, TimeoutError, ConnectionError) as e:
            raise ExplorerError('Cannot connect to configured TRU node') from e
        except (json.JSONDecodeError, UnicodeError) as e:
            raise ExplorerError('Node returned invalid JSON') from e

    def rpc(self, method, params=None):
        # Explicit safe read-only methods, never any caller-supplied method.
        allowed = {'getchaininfo', 'getblockcount', 'getblockbyheight', 'getblock',
                   'gettransaction', 'getrawtransaction', 'getaddresstransactions',
                   'getallminers', 'getrawmempool', 'getchainsupply', 'getchainmetadata'}
        if method not in allowed:
            raise ExplorerError('RPC method is not permitted', 403)
        result = self._read_json(self.rpc_url, 'POST',
                                 {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}, True)
        if isinstance(result, dict) and result.get('error'):
            message = result['error'].get('message', '') if isinstance(result['error'], dict) else ''
            if any(word in message.lower() for word in ('not found', 'unknown', 'no such')):
                raise ExplorerError('Record not found', 404)
            LOG.warning('Read-only RPC method %s returned an error: %s', method, message[:160])
            raise ExplorerError('Node could not fulfill read-only request')
        if isinstance(result, dict) and 'result' in result:
            return result['result']
        raise ExplorerError('Unexpected JSON-RPC response format')

    def public(self, path, params=None):
        if not self.api_url:
            raise ExplorerError('Public API is not configured', 501)
        # Paths are supplied only from hardcoded routes and validated IDs.
        q = ('?' + urlencode(params)) if params else ''
        return self._read_json(self.api_url + path + q)

    @staticmethod
    def block_normalize(b):
        if not isinstance(b, dict):
            raise ExplorerError('Invalid block data')
        tx = b.get('transactions', b.get('tx', []))
        return {'height': b.get('height'), 'hash': b.get('hash'),
                'prevHash': b.get('prevHash', b.get('prevhash')),
                'merkleRoot': b.get('merkleRoot', b.get('merkleroot')),
                'timestamp': b.get('timestamp'), 'nonce': b.get('nonce'),
                'bits': b.get('bits'), 'size': b.get('size'),
                'cadenceSeconds': b.get('cadenceSeconds'),
                'cadenceSource': b.get('cadenceSource'),
                'transactions': tx if isinstance(tx, list) else []}

    def status(self):
        if self.mode == 'demo':
            return demo_stats()
        if self.mode == 'api':
            s = self.public('/api/stats')
            s['mode'] = 'api'
            return s
        info = self.rpc('getchaininfo')
        s = {'mode': 'rpc', 'height': info.get('bestHeight'),
             'best_tip_hash': info.get('bestHash'),
             'difficulty': None, 'difficultyBits': info.get('difficulty'),
             'chainAudit': info.get('chain_audit'), 'chainValid': info.get('chainValid'),
             'networkHashrate': None, 'activeMiners': None, 'totalTransactions': None,
             'mempool_size': None, 'connectedPeerCount': None, 'issuedTokens': None,
             'activeAddresses': None, 'smartContracts': None, 'truscriptsCount': None}
        # RPC getchaininfo returns encoded difficulty bits, not explorer difficulty.
        try:
            pool = self.rpc('getrawmempool')
            s['mempool_size'] = len(pool) if isinstance(pool, list) else None
        except ExplorerError:
            pass
        try:
            supply = self.rpc('getchainsupply')
            if isinstance(supply, dict):
                s['supplyInfo'] = supply
        except ExplorerError:
            pass
        # Optional richer telemetry from the SAME Core's HTTP API. Only merge
        # data if the public API reports exactly the same active chain tip.
        if self.api_url:
            try:
                extra = self.public('/api/stats')
                if (isinstance(extra, dict) and extra.get('height') == s['height']
                        and extra.get('best_tip_hash') == s['best_tip_hash']):
                    for key in ('difficulty', 'networkHashrate', 'activeMiners',
                                'totalTransactions', 'mempool_size', 'connectedPeerCount',
                                'issuedTokens', 'targetBlockTime', 'cadence', 'activeAddresses',
                                'smartContracts', 'truscriptsCount', 'blockchainSize',
                                'latestBlockSize', 'totalIssuedTrus', 'block_reward', 'knownPeerCount',
                                'networkHashrateAuthority', 'p2pHashWorkVerified'):
                        if key in extra:
                            s[key] = extra[key]
                    s['advancedStatusTipMatched'] = True
                    s['mode'] = 'hybrid'
                else:
                    s['advancedStatusTipMatched'] = False
            except ExplorerError:
                pass
        return s

    def one_block(self, identifier):
        if self.mode == 'demo':
            b = next((b for b in demo_blocks() if str(b['height']) == str(identifier) or b['hash'] == identifier), None)
            if b is None:
                raise ExplorerError('Demo block not found', 404)
            return b
        if self.mode == 'api':
            if identifier.isdecimal():
                recent = self.public('/api/blocks')
                match = next((b for b in recent if str(b.get('height')) == identifier), None)
                if not match:
                    raise ExplorerError('Historical height lookup requires RPC mode', 501)
                identifier = match['hash']
            return self.block_normalize(self.public('/block/' + identifier))
        if identifier.isdecimal():
            b = self.rpc('getblockbyheight', {'height': int(identifier)})
        else:
            b = self.rpc('getblock', {'hash': identifier})
        return self.block_normalize(b)

    def blocks(self, limit, before=None):
        if self.mode == 'demo':
            items = demo_blocks()
            return [b for b in items if before is None or b['height'] < before][:limit]
        if self.mode == 'api':
            if before is not None:
                raise ExplorerError('Older block paging requires RPC mode', 501)
            raw = self.public('/api/blocks')
            return sorted([self.block_normalize(b) for b in raw], key=lambda b: b['height'] or 0, reverse=True)[:limit]
        info = self.cache.fetch('info-height', 4, lambda: self.rpc('getblockcount'))
        tip = int(info) if isinstance(info, (int, float)) else int(self.rpc('getchaininfo')['bestHeight'])
        start = min(tip, before - 1) if before is not None else tip
        if start < 1:
            return []
        # Cache immutable recent-ish blocks briefly: reorg may change hash at a height.
        return [self.cache.fetch(('block', h), 8, lambda h=h: self.one_block(str(h)))
                for h in range(start, max(0, start - limit), -1)]

    @staticmethod
    def atoms_from_tru(value):
        try:
            return str(int((Decimal(str(value)) * 100_000_000).quantize(Decimal('1'))))
        except (InvalidOperation, ValueError, TypeError):
            return None

    def transaction(self, txid):
        if self.mode == 'demo':
            return demo_tx(txid)
        if self.mode == 'api':
            return normalize_api_tx(self.public('/api/transaction/' + txid))
        if self.api_url:
            try:
                return normalize_api_tx(self.public('/api/transaction/' + txid))
            except ExplorerError:
                pass  # The standalone RPC adapter remains the fallback.
        raw = self.rpc('getrawtransaction', {'txid': txid, 'verbose': True})
        if not isinstance(raw, dict):
            raise ExplorerError('Unexpected transaction response')
        state = {}
        try:
            state = self.rpc('gettransaction', {'txid': txid})
        except ExplorerError:
            pass
        if state.get('txState') == 'NOT_FOUND':
            raise ExplorerError('Transaction not found', 404)
        vouts = []
        for v in raw.get('vout', []):
            script = v.get('scriptPubKey', {})
            vouts.append({'n': v.get('n'), 'amountAtoms': self.atoms_from_tru(v.get('value')),
                           'scriptPubKey': script.get('hex', '') if isinstance(script, dict) else script,
                           'scriptType': None, 'address': None, 'tokenData': None})
        vins = []
        for v in raw.get('vin', []):
            vins.append({'txid': v.get('txid'), 'vout': v.get('vout'),
                         'sequence': v.get('sequence'), 'scriptSig': v.get('scriptSig'),
                         'address': None, 'amountAtoms': None})
        return {'txid': txid, 'version': raw.get('version'), 'lockTime': raw.get('locktime'),
                'vin': vins, 'vout': vouts, 'isCoinbase': False,
                'blockHeight': state.get('blockheight'), 'blockHash': state.get('blockhash'),
                'timestamp': state.get('blocktime', state.get('time')),
                'confirmations': state.get('confirmations', 0), 'txState': state.get('txState', 'UNKNOWN'),
                'feeAtoms': None, 'hex': raw.get('hex'), 'source': 'rpc'}

    def transactions(self, limit, page=0):
        if self.mode == 'demo':
            return demo_transactions()[:limit]
        if self.mode == 'api':
            return [normalize_list_tx(t) for t in self.public('/api/transactions', {'start': limit*page, 'limit': limit})]
        # Use the block txid lists directly: read-only; bounded to 20 blocks.
        tip = int(self.status().get('height') or 0)
        collected = []
        skip = limit * page
        for h in range(tip, max(tip - 20, 0), -1):
            b = self.cache.fetch(('txscan-block', h), 10, lambda h=h: self.one_block(str(h)))
            for txid in reversed(b['transactions']):
                if skip:
                    skip -= 1
                    continue
                collected.append({'txid': txid, 'blockHeight': h, 'timestamp': b.get('timestamp'),
                                  'amountAtoms': None, 'vout': [], 'vin': []})
                if len(collected) >= limit:
                    return collected
        return collected

    def address(self, address):
        if self.mode == 'demo':
            return demo_address(address)
        if self.mode == 'api' or self.api_url:
            try:
                a = self.public('/api/address/' + address)
                if not isinstance(a, dict):
                    raise ExplorerError('Unexpected address response')
                a['source'] = 'api'
                return a
            except ExplorerError:
                if self.mode == 'api':
                    raise
                # In hybrid mode, Core RPC remains independent fallback.
        rows = self.rpc('getaddresstransactions', {'address': address, 'count': 100, 'maxBlocks': 0})
        if not isinstance(rows, list):
            raise ExplorerError('Unexpected address history response')
        return {'address': address, 'balance': None, 'balanceAvailable': False,
                'transactionCount': None, 'transactions': rows, 'tokens': [], 'scripts': [],
                'historyTruncated': len(rows) >= 100, 'historyCountShown': len(rows), 'source': 'rpc'}

    def miners(self):
        if self.mode == 'demo':
            return {'miners': [], 'summary': {}, 'source': 'demo'}
        if self.mode == 'api':
            raw = self.public('/api/miners')
        else:
            try:
                raw = self.public('/api/miners') if self.api_url else self.rpc('getallminers')
            except ExplorerError:
                raw = self.rpc('getallminers')
        if isinstance(raw, list):
            return {'miners': raw, 'summary': None, 'source': self.mode}
        if isinstance(raw, dict):
            return {'miners': raw.get('miners', []), 'summary': raw.get('summary', raw), 'source': self.mode}
        return {'miners': [], 'summary': None}

    def tokens(self, start=0, limit=25):
        if self.mode == 'demo':
            return {'items': [], 'available': False, 'reason': 'No sample token data is shipped'}
        if not self.api_url:
            return {'items': [], 'available': False, 'reason': 'Enable TRU_API_URL for token index data'}
        items = self.public('/api/tokens', {'start': start, 'limit': limit})
        return {'items': items if isinstance(items, list) else [], 'available': True,
                'limit': limit, 'start': start}

    def inscriptions(self, page=1, limit=25):
        if self.mode == 'demo':
            return {'truscripts': [], 'available': False, 'reason': 'No sample inscriptions'}
        if not self.api_url:
            return {'truscripts': [], 'available': False, 'reason': 'Enable TRU_API_URL for TRUScript index data'}
        result = self.public('/api/truscripts', {'page': page, 'limit': limit})
        result['available'] = True
        return result

    def addresses(self, start=0, limit=25, sort='balance_desc', search=''):
        if self.mode == 'demo':
            return {'addresses': [], 'total': 0, 'start': start, 'limit': limit,
                    'available': False, 'reason': 'Sample address directory is not provided'}
        if not self.api_url:
            return {'addresses': [], 'total': 0, 'start': start, 'limit': limit,
                    'available': False, 'reason': 'Set TRU_API_URL to enable the address index'}
        if sort not in ('balance_desc', 'balance_asc', 'txCount_desc', 'txCount_asc'):
            raise ExplorerError('Invalid address sort order', 400)
        if len(search) > 50 or not re.fullmatch(r'[a-zA-Z0-9]*', search):
            raise ExplorerError('Invalid address search', 400)
        result = self.public('/api/addresses', {'start': start, 'limit': limit, 'sort': sort, 'search': search})
        if not isinstance(result, dict) or not isinstance(result.get('addresses'), list):
            raise ExplorerError('Unexpected address index response')
        return {'addresses': result['addresses'], 'total': result.get('total'),
                'start': start, 'limit': limit, 'available': True, 'sort': sort, 'search': search}

    def contracts(self):
        if self.mode == 'demo':
            return {'contracts': [], 'available': False, 'reason': 'No sample contracts'}
        if not self.api_url:
            return {'contracts': [], 'available': False, 'reason': 'Set TRU_API_URL to enable contract inspection'}
        result = self.public('/api/contracts')
        if not isinstance(result, dict) or not isinstance(result.get('contracts'), list):
            raise ExplorerError('Unexpected contract index response')
        # Core provides contract classifications from its current index.
        return {'contracts': result['contracts'][:500], 'totalReported': len(result['contracts']), 'available': True}

    def contract_activity(self, address):
        if self.mode == 'demo':
            return {'address': address, 'contracts': [], 'available': False}
        if not self.api_url:
            return {'address': address, 'contracts': [], 'available': False,
                    'reason': 'Set TRU_API_URL for contract activity'}
        result = self.public('/api/contracts/' + address + '/txs')
        if not isinstance(result, dict):
            raise ExplorerError('Unexpected contract activity response')
        return {'address': address, 'contracts': result.get('contracts', []), 'available': True}

    def network(self):
        if self.mode == 'demo':
            return {'available': False, 'reason': 'Demo has no live network', 'uptime': None}
        if not self.api_url:
            return {'available': False, 'reason': 'Set TRU_API_URL for node health, supply and peers'}
        result = {'available': True, 'source': 'public-api'}
        # Return approved informational fields only. Never publish raw peer records,
        # IP addresses, RPC secrets, internal config, or dynamic unfiltered health JSON.
        for path, key in (('/api/supply','supply'),('/api/chain','chain'),('/api/health','health'),
                          ('/api/uptime','uptime'),('/api/token-burn','burn'),('/api/peers','peers')):
            try:
                raw = self.public(path)
                if not isinstance(raw, dict):
                    continue
                if key == 'peers':
                    result['peers'] = {'count': len(raw['peers']) if isinstance(raw.get('peers'), list) else None,
                                       'localCoreVersion': raw.get('localCoreVersion')}
                elif key == 'uptime':
                    result['uptime'] = {'uptimeSeconds': raw.get('uptimeSeconds')}
                elif key == 'health':
                    result['health'] = {k: raw[k] for k in ('schema','status','ok','healthy','version','chainvalid','chainValid','height','tip_fresh','connected_peers','tip_age_seconds','rpc_available') if k in raw and (raw[k] is None or isinstance(raw[k], (str,int,float,bool)))}
                elif key == 'chain':
                    result['chain'] = {k: raw[k] for k in ('schema','network','chain','height','bestHeight','bestHash','best_block_hash','genesisHash','genesis_hash','difficulty','targetBlockTime','target_block_time_seconds','ticker','name','core_version','consensus','pow_algorithm','decimals') if k in raw and (raw[k] is None or isinstance(raw[k], (str,int,float,bool)))}
                elif key == 'supply':
                    result['supply'] = {k: raw[k] for k in ('schema','totalSupply','circulatingSupply','maxSupply','issued','totalIssued','burned','totalBurned','totalIssuedTrus','supply','height','units','decimals','source','total_supply','total_supply_atoms','scheduled_issuance','scheduled_issuance_atoms','max_supply','max_supply_atoms','circulating_supply','circulating_supply_atoms','circulating_supply_status','circulating_candidate','immature_coinbase_atoms','provably_unspendable_utxo_atoms','method','circulation_policy') if k in raw and (raw[k] is None or isinstance(raw[k], (str,int,float,bool)))}
                elif key == 'burn':
                    result['burn'] = {k: raw[k] for k in ('version','sink','burnAddress','burnSink','status','policy','enabled','description','source','address','hash160','consensusChange','meaning','transactionType') if k in raw and (raw[k] is None or isinstance(raw[k], (str,int,float,bool)))}
            except ExplorerError:
                result[key] = {'unavailable': True}
        return result

    def charts(self):
        if self.mode == 'demo':
            bs = demo_blocks()
            return {'blocks': bs, 'hashrate': [], 'difficulty': []}
        if self.api_url:
            try:
                hrs = self.public('/api/hashrate_history', {'blocks': 80})
                diff = self.public('/api/difficulty_history')
                bs = self.blocks(10)
                return {'blocks': bs, 'hashrate': hrs, 'difficulty': diff}
            except ExplorerError:
                pass
        bs = self.blocks(36)
        return {'blocks': bs, 'hashrate': [], 'difficulty': []}


def normalize_list_tx(tx):
    out = dict(tx)
    # C++ /api/transactions vout[].amount is in atoms, not TRU.
    amount = 0
    for v in out.get('vout', []):
        try:
            amount += int(v.get('amount', 0))
        except (TypeError, ValueError):
            pass
    out['amountAtoms'] = str(amount)
    return out


def normalize_api_tx(tx):
    result = dict(tx)
    for v in result.get('vout', []):
        v['amountAtoms'] = str(v.get('amount')) if v.get('amount') is not None else None
    for v in result.get('vin', []):
        v['amountAtoms'] = str(v.get('amount')) if v.get('amount') is not None else None
    result['feeAtoms'] = str(result.get('fee')) if result.get('fee') is not None else None
    result['source'] = 'api'
    return result


# Deliberately unmistakable demo data, with no invented real-chain numbers.
def demo_blocks():
    out = []
    start = 60000
    epoch = 1792240000
    for i in range(25):
        h = start-i
        hx = f'{h:064x}'
        out.append({'height': h, 'hash': hx, 'prevHash': f'{h-1:064x}',
                    'merkleRoot': f'{h+33:064x}', 'timestamp': epoch-i*125,
                    'nonce': 100000+i, 'transactions': [f'{h+10_000_000:064x}', f'{h+20_000_000:064x}'],
                    'cadenceSeconds': 125+(i%6)*9, 'cadenceSource': 'demo', 'size': 1700 + i * 19})
    return out


def demo_stats():
    return {'mode': 'demo', 'height': 60000, 'best_tip_hash': f'{60000:064x}',
            'networkHashrate': 286_000_000, 'difficulty': 580_000_000,
            'mempool_size': 7, 'activeMiners': 3, 'totalTransactions': 124890,
            'connectedPeerCount': 6, 'issuedTokens': 18, 'targetBlockTime': 120,
            'cadence': {'effectiveSeconds': 125, 'effectiveSource': 'demo'}}


def demo_transactions():
    out = []
    for b in demo_blocks()[:10]:
        for t in b['transactions']:
            out.append({'txid': t, 'blockHeight': b['height'], 'timestamp': b['timestamp'],
                        'amountAtoms': str(120_000_000 + (b['height']%5)*50_000_000)})
    return out


def demo_tx(txid):
    row = next((t for t in demo_transactions() if t['txid'] == txid), None)
    if not row:
        raise ExplorerError('Demo transaction not found', 404)
    return {'txid': txid, 'blockHeight': row['blockHeight'], 'blockHash': f"{row['blockHeight']:064x}",
            'confirmations': 60000-row['blockHeight']+1, 'isCoinbase': False,
            'vin': [{'txid': f'{row["blockHeight"]-80:064x}', 'vout': 0, 'amountAtoms': '200000000'}],
            'vout': [{'amountAtoms': row['amountAtoms'], 'n': 0, 'scriptType': 'p2pkh'}],
            'feeAtoms': '10000', 'txState': 'CONFIRMED'}


def demo_address(address):
    return {'address': address, 'balance': 12.8, 'transactionCount': 2,
            'transactions': demo_transactions()[:2], 'tokens': [], 'scripts': [], 'source': 'demo'}


NODE = None
SLOTS = threading.BoundedSemaphore(16)


class Handler(BaseHTTPRequestHandler):
    server_version = 'TRUAtlas/1.1'
    sys_version = ''

    def log_message(self, fmt, *args):
        LOG.info('%s - %s', self.address_string(), fmt % args)

    def send_bytes(self, status, body, content_type, cache='no-store'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', cache)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send_bytes(status, json.dumps(payload, separators=(',', ':'), default=str).encode('utf-8'), 'application/json; charset=utf-8')

    def do_HEAD(self):
        # Public static media often receives a HEAD probe before a Range GET.
        # Keep this an exact allowlist; no filesystem path comes from the caller.
        static_types = {'/':'index.html','/index.html':'index.html',
                        '/app.js':'app.js','/styles.css':'styles.css',
                        '/themes.css':'themes.css','/theme-boot.js':'theme-boot.js',
                        '/favicon.svg':'favicon.svg',
                        '/assets/tru-atlas-logo.webp':'assets/tru-atlas-logo.webp',
                        '/assets/tru-hero-poster.webp':'assets/tru-hero-poster.webp',
                        '/assets/tru-hero-once.mp4':'assets/tru-hero-once.mp4'}
        path = urlsplit(self.path).path
        if path not in static_types:
            self.send_response(404)
            self.send_header('Content-Length','0')
            self.end_headers()
            return
        file = STATIC / static_types[path]
        mime = ('video/mp4' if path.endswith('.mp4') else 'image/webp' if path.endswith('.webp')
                else 'image/svg+xml' if path.endswith('.svg') else 'text/css' if path.endswith('.css')
                else 'text/javascript' if path.endswith('.js') else 'text/html')
        self.send_response(200)
        self.send_header('Content-Length',str(file.stat().st_size))
        self.send_header('Content-Type',mime)
        self.send_header('Cache-Control','public, max-age=86400' if path.startswith('/assets/') else 'no-cache')
        self.send_header('X-Content-Type-Options','nosniff')
        if path.endswith('.mp4'):
            self.send_header('Accept-Ranges','bytes')
        self.end_headers()

    def do_POST(self):
        self.send_json(405, {'error': 'This explorer is strictly read-only'})

    def do_PUT(self):
        self.do_POST()

    def do_DELETE(self):
        self.do_POST()

    def do_GET(self):
        if not SLOTS.acquire(blocking=False):
            self.send_json(503, {'error': 'Explorer busy; retry shortly'})
            return
        try:
            self.route()
        except ExplorerError as e:
            self.send_json(e.status, {'error': str(e)})
        except (ValueError, KeyError, IndexError):
            self.send_json(400, {'error': 'Invalid request'})
        except BrokenPipeError:
            pass
        except Exception:
            LOG.exception('Unexpected explorer error')
            try:
                self.send_json(500, {'error': 'Explorer encountered an internal error'})
            except (BrokenPipeError, ConnectionResetError):
                pass
        finally:
            SLOTS.release()

    def route(self):
        split = urlsplit(self.path)
        path = split.path
        qs = parse_qs(split.query, keep_blank_values=True)
        if path == '/healthz':
            return self.send_json(200, {'ok': True, 'mode': NODE.mode, 'demo': NODE.mode == 'demo'})
        if path.startswith('/api/v1/'):
            def number(k, default, low, high):
                val = qs.get(k, [str(default)])[0]
                if not val.isdecimal() or not low <= int(val) <= high:
                    raise ExplorerError('Invalid query parameter ' + k, 400)
                return int(val)
            if path == '/api/v1/status':
                result = NODE.cache.fetch('status', 5, NODE.status)
            elif path == '/api/v1/blocks':
                limit = number('limit', 12, 1, 30)
                before = number('before', 1, 1, 2_147_483_647) if 'before' in qs else None
                result = NODE.cache.fetch(('blocks', limit, before), 8, lambda: NODE.blocks(limit, before))
            elif path == '/api/v1/transactions':
                limit, page = number('limit', 12, 1, 30), number('page', 0, 0, 20)
                result = NODE.cache.fetch(('transactions', limit, page), 10, lambda: NODE.transactions(limit, page))
            elif path == '/api/v1/addresses':
                start, limit = number('start', 0, 0, 1_000_000), number('limit', 25, 1, 100)
                sort, search = qs.get('sort', ['balance_desc'])[0], qs.get('search', [''])[0]
                if len(sort) > 30 or len(search) > 50:
                    raise ExplorerError('Invalid address query', 400)
                result = NODE.cache.fetch(('addresses', start, limit, sort, search), 30,
                                          lambda: NODE.addresses(start, limit, sort, search))
            elif path == '/api/v1/contracts':
                result = NODE.cache.fetch('contracts', 35, NODE.contracts)
            elif path.startswith('/api/v1/contract-activity/'):
                address = path.removeprefix('/api/v1/contract-activity/')
                if not ADDRESS.fullmatch(address):
                    raise ExplorerError('Invalid contract address', 400)
                result = NODE.cache.fetch(('contract-activity', address), 25, lambda: NODE.contract_activity(address))
            elif path == '/api/v1/network':
                result = NODE.cache.fetch('network', 45, NODE.network)
            elif path == '/api/v1/miners':
                result = NODE.cache.fetch('miners', 20, NODE.miners)
            elif path == '/api/v1/tokens':
                limit, start = number('limit', 25, 1, 100), number('start', 0, 0, 1_000_000)
                result = NODE.cache.fetch(('tokens', limit, start), 30, lambda: NODE.tokens(start, limit))
            elif path == '/api/v1/inscriptions':
                limit, page = number('limit', 25, 1, 100), number('page', 1, 1, 10000)
                result = NODE.cache.fetch(('inscriptions', limit, page), 30, lambda: NODE.inscriptions(page, limit))
            elif path == '/api/v1/charts':
                result = NODE.cache.fetch('charts', 35, NODE.charts)
            elif path.startswith('/api/v1/block/'):
                identifier = path.removeprefix('/api/v1/block/')
                if not (HEX64.fullmatch(identifier) or (identifier.isdecimal() and 0 < int(identifier) < 2_147_483_648)):
                    raise ExplorerError('Invalid block hash or height', 400)
                result = NODE.cache.fetch(('block-detail', identifier), 8, lambda: NODE.one_block(identifier))
            elif path.startswith('/api/v1/tx/'):
                txid = path.removeprefix('/api/v1/tx/')
                if not HEX64.fullmatch(txid):
                    raise ExplorerError('Invalid TXID', 400)
                result = NODE.cache.fetch(('tx', txid), 10, lambda: NODE.transaction(txid))
            elif path.startswith('/api/v1/address/'):
                addr = path.removeprefix('/api/v1/address/')
                if not ADDRESS.fullmatch(addr):
                    raise ExplorerError('Invalid TRU address', 400)
                result = NODE.cache.fetch(('address', addr), 20, lambda: NODE.address(addr))
            elif path == '/api/v1/config':
                result = {'mode': NODE.mode, 'demo': NODE.mode == 'demo',
                          'advancedData': NODE.mode == 'api' or bool(NODE.api_url),
                          'historicalHeightLookup': NODE.mode in ('rpc', 'demo'),
                          'readOnly': True, 'name': os.getenv('TRU_EXPLORER_NAME', 'TRU Atlas'),
                          'network': os.getenv('TRU_NETWORK_LABEL', 'TRU Mainnet')}
            else:
                raise ExplorerError('Route not found', 404)
            return self.send_json(200, result)
        # Never expose .env, source, or arbitrary paths. Exact static allowlist.
        files = {'/assets/tru-atlas-logo.webp': ('assets/tru-atlas-logo.webp', 'image/webp'),
                 '/assets/tru-hero-poster.webp': ('assets/tru-hero-poster.webp', 'image/webp'),
                 '/assets/tru-hero-once.mp4': ('assets/tru-hero-once.mp4', 'video/mp4'),
                 '/': ('index.html', 'text/html; charset=utf-8'),
                 '/index.html': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/styles.css': ('styles.css', 'text/css; charset=utf-8'),
                 '/themes.css': ('themes.css', 'text/css; charset=utf-8'),
                 '/theme-boot.js': ('theme-boot.js', 'text/javascript; charset=utf-8'),
                 '/favicon.svg': ('favicon.svg', 'image/svg+xml')}
        if path not in files:
            raise ExplorerError('Not found', 404)
        filename, ct = files[path]
        data = (STATIC / filename).read_bytes()
        cache = 'public, max-age=86400' if path.startswith('/assets/') else 'no-cache'
        if path.endswith('.mp4'):
            # Safari and mobile browsers commonly request byte ranges for MP4.
            # Do not permit multiple ranges or read any user-selected file paths.
            length = len(data)
            requested = self.headers.get('Range', '')
            if requested:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
                if not match or (not match.group(1) and not match.group(2)):
                    return self.send_range_invalid(length)
                first, last = match.groups()
                if first:
                    start = int(first)
                    end = int(last) if last else length - 1
                else:
                    suffix = int(last)
                    if suffix < 1:
                        return self.send_range_invalid(length)
                    start, end = max(0, length - suffix), length - 1
                if start >= length or end < start:
                    return self.send_range_invalid(length)
                end = min(end, length - 1)
                chunk = data[start:end + 1]
                self.send_response(206)
                self.send_header('Content-Type', ct)
                self.send_header('Content-Length', str(len(chunk)))
                self.send_header('Content-Range', f'bytes {start}-{end}/{length}')
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Cache-Control', cache)
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                self.wfile.write(chunk)
                return
            self.send_response(200)
            self.send_header('Content-Type', ct)
            self.send_header('Content-Length', str(length))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', cache)
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)
            return
        return self.send_bytes(200, data, ct, cache)

    def send_range_invalid(self, total):
        self.send_response(416)
        self.send_header('Content-Range', f'bytes */{total}')
        self.send_header('Content-Length', '0')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()


def main():
    global NODE
    load_dotenv(ROOT / '.env')
    parser = argparse.ArgumentParser(description='TRU Atlas independent read-only explorer')
    parser.add_argument('--demo', action='store_true', help='Preview clearly labeled demo data without a node')
    parser.add_argument('--host', default=os.getenv('TRU_BIND', '127.0.0.1'))
    parser.add_argument('--port', default=int(os.getenv('TRU_PORT', '3030')), type=int)
    args = parser.parse_args()
    if args.demo:
        os.environ['TRU_MODE'] = 'demo'
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    NODE = Node()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.daemon_threads = True
    print(f'TRU Atlas listening on http://{args.host}:{args.port} (source={NODE.mode})', flush=True)
    if NODE.mode == 'demo':
        print('DEMO MODE: all heights, amounts, and hashes are example data only', flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
