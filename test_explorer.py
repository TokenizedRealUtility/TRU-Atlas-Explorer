"""Run with: python3 -m unittest discover -s tests -v"""
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server


class RpcAdapterTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'TRU_MODE': 'rpc', 'TRU_RPC_URL': 'http://127.0.0.1:21832/rpc',
                                           'TRU_RPC_TOKEN': 'X'*64, 'TRU_RPC_TOKEN_FILE': '', 'TRU_API_URL': ''})
        self.env.start()
        self.node = server.Node()

    def tearDown(self):
        self.env.stop()

    def test_correct_method_and_params(self):
        calls=[]
        def mock_rpc(method, params=None):
            calls.append((method, params))
            if method == 'getblockbyheight':
                return {'height': 14, 'hash':'a'*64, 'prevhash':'b'*64,'merkleroot':'c'*64,
                        'timestamp':1700000000, 'nonce':57,'tx':['d'*64]}
            if method == 'getchaininfo': return {'bestHeight':14,'bestHash':'a'*64, 'difficulty':123}
            if method == 'getrawmempool': return []
            if method == 'getblockcount': return 14
            if method == 'getchainsupply': return {}
            raise AssertionError(method)
        with patch.object(self.node,'rpc', side_effect=mock_rpc):
            b=self.node.one_block('14')
            self.assertEqual(b['merkleRoot'], 'c'*64)
            self.assertEqual(b['transactions'], ['d'*64])
            self.assertEqual(self.node.blocks(2)[0]['height'], 14)
            s=self.node.status()
            self.assertIsNone(s['difficulty'])
            self.assertEqual(s['difficultyBits'],123)
        self.assertIn(('getblockbyheight', {'height':14}),calls)

    def test_hybrid_stats_only_merge_matching_tip(self):
        self.node.api_url = 'http://127.0.0.1:8080'
        def rpc(method, params=None):
            if method == 'getchaininfo':
                return {'bestHeight': 222, 'bestHash': 'a'*64, 'difficulty': 486604799}
            if method == 'getrawmempool': return []
            if method == 'getchainsupply': return {}
            raise AssertionError(method)
        with patch.object(self.node, 'rpc',side_effect=rpc):
            with patch.object(self.node, 'public',return_value={'height':221,'best_tip_hash':'b'*64,'difficulty':99}):
                stale=self.node.status()
                self.assertIsNone(stale['difficulty'])
                self.assertFalse(stale['advancedStatusTipMatched'])
            with patch.object(self.node, 'public',return_value={'height':222,'best_tip_hash':'a'*64,'difficulty':99,'networkHashrate':1234}):
                current=self.node.status()
                self.assertEqual(current['difficulty'],99)
                self.assertEqual(current['networkHashrate'],1234)
                self.assertTrue(current['advancedStatusTipMatched'])

    def test_hybrid_address_enrichment(self):
        self.node.api_url = 'http://127.0.0.1:8080'
        address = 'T'+'1'*33
        with patch.object(self.node, 'public',return_value={'address':address,'balance':2.5,'tokens':[],'transactions':[]}):
            out=self.node.address(address)
            self.assertEqual(out['balance'],2.5)
            self.assertEqual(out['source'],'api')

    def test_value_units(self):
        self.assertEqual(self.node.atoms_from_tru('0.001'), '100000')
        self.assertEqual(self.node.atoms_from_tru('1.00000001'), '100000001')
        self.assertIsNone(self.node.atoms_from_tru('abc'))

    def test_tx_read_only_methods(self):
        def mock_rpc(method, params=None):
            if method == 'getrawtransaction':
                return {'txid':'a'*64, 'version':1, 'locktime':0, 'vin':[{'txid':'b'*64,'vout':0}],
                        'vout':[{'value':1.25,'n':0,'scriptPubKey':{'hex':'76a9'}}]}
            if method == 'gettransaction':
                return {'txState':'CONFIRMED','blockheight':99,'blockhash':'c'*64,'confirmations':2}
            raise AssertionError('unexpected RPC: '+method)
        with patch.object(self.node, 'rpc',side_effect=mock_rpc):
            t=self.node.transaction('a'*64)
            self.assertEqual(t['vout'][0]['amountAtoms'], '125000000')
            self.assertEqual(t['blockHeight'], 99)
            self.assertIsNone(t['feeAtoms'])

    def test_blocklist_normalize(self):
        result=server.Node.block_normalize({'height': 100, 'hash':'a'*64, 'transactions':['b'*64]})
        self.assertEqual(result['transactions'], ['b'*64])

    def test_remote_rpc_disabled_without_override(self):
        with patch.dict(os.environ, {'TRU_RPC_URL':'http://example.com:21832/rpc', 'TRU_ALLOW_REMOTE_RPC':''}):
            with self.assertRaises(ValueError): server.Node()

    def test_rpc_method_allowlist(self):
        with self.assertRaises(server.ExplorerError):
            self.node.rpc('sendrawtransaction', {'txHex':'00'})

    def test_api_output_in_atoms(self):
        n=server.normalize_api_tx({'vout':[{'amount':100000000}],'vin':[{'amount':111000000}], 'fee':1000})
        self.assertEqual(n['feeAtoms'],'1000')
        self.assertEqual(n['vout'][0]['amountAtoms'],'100000000')


class DemoHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import socket
        s=socket.socket();s.bind(('127.0.0.1',0));cls.port=s.getsockname()[1];s.close()
        env=os.environ.copy();env.pop('TRU_RPC_TOKEN',None)
        cls.proc=subprocess.Popen([sys.executable,str(ROOT/'server.py'),'--demo','--port',str(cls.port)],
                                  cwd=str(ROOT), env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for i in range(40):
            try:
                with urlopen(cls.base()+'/healthz', timeout=.5) as resp: break
            except Exception: time.sleep(.1)
        else: raise RuntimeError('demo server failed to start')

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:cls.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:cls.proc.kill()

    @classmethod
    def base(cls): return 'http://127.0.0.1:'+str(cls.port)

    def get(self,path):
        with urlopen(self.base()+path,timeout=5) as r:
            return json.loads(r.read())

    def test_core_routes(self):
        c=self.get('/api/v1/config');self.assertTrue(c['readOnly']);self.assertTrue(c['demo'])
        self.assertEqual(self.get('/api/v1/status')['height'],60000)
        block=self.get('/api/v1/block/60000')
        self.assertEqual(len(block['transactions']),2)
        self.assertEqual(self.get('/api/v1/blocks?limit=4')[1]['height'],59999)
        self.assertEqual(len(self.get('/api/v1/transactions?limit=4')),4)
        self.assertEqual(len(self.get('/api/v1/charts')['blocks']),25)
        self.assertFalse(self.get('/api/v1/tokens')['available'])
        self.assertFalse(self.get('/api/v1/inscriptions')['available'])

    def test_safety_and_input_validation(self):
        paths=['/api/v1/block/nope','/api/v1/tx/xyz','/api/v1/address/not-an-address',
               '/api/v1/blocks?limit=100000','/.env','/server.py','/api/v1/unknown','/api/wallet/rpc']
        for p in paths:
            with self.subTest(path=p):
                with self.assertRaises(HTTPError) as e: urlopen(self.base()+p)
                self.assertIn(e.exception.code,(400,404))
        with self.assertRaises(HTTPError) as e:
            urlopen(Request(self.base()+'/api/v1/status', data=b'{}', method='POST'))
        self.assertEqual(e.exception.code,405)

    def test_response_headers(self):
        with urlopen(self.base()+'/') as r:
            body=r.read().decode()
            self.assertIn('TRU ATLAS',body)
            self.assertIn("script-src 'self'",r.headers['Content-Security-Policy'])
            self.assertNotIn('TRU_RPC_TOKEN',body)


if __name__ == '__main__':unittest.main()
