"""TRU Atlas v1.1 media and read-only public API regression tests."""
import json, os, sys, unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from test_explorer import DemoHttpTests

class HybridDataTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'TRU_MODE':'rpc','TRU_API_URL':'http://127.0.0.1:8001',
                                      'TRU_RPC_URL':'http://127.0.0.1:21832/rpc',
                                      'TRU_RPC_TOKEN':'X'*64,'TRU_RPC_TOKEN_FILE':''})
        self.env.start();self.node=server.Node()
    def tearDown(self): self.env.stop()

    def test_addresses_params_and_response(self):
        calls=[]
        def public(path, params=None):
            calls.append((path,params))
            return {'addresses':[{'address':'T'+'1'*33,'balance':7.2,'transactionCount':2}], 'total':1074}
        with patch.object(self.node,'public',side_effect=public):
            r=self.node.addresses(5,10,'txCount_desc','T')
        self.assertTrue(r['available']);self.assertEqual(r['total'],1074)
        self.assertEqual(calls,[('/api/addresses',{'start':5,'limit':10,'sort':'txCount_desc','search':'T'})])
        for sort,term in [('balance_desc','a/b'),('xx','')]:
            with self.assertRaises(server.ExplorerError):self.node.addresses(0,10,sort,term)

    def test_contracts_and_activity_are_get_only(self):
        calls=[]
        def public(path,params=None):
            calls.append(path)
            return {'contracts':[{'address':'T'+'1'*33}]}
        with patch.object(self.node,'public',side_effect=public):
            self.assertEqual(self.node.contracts()['totalReported'],1)
            a='T'+'1'*33
            self.assertTrue(self.node.contract_activity(a)['available'])
        self.assertEqual(calls,['/api/contracts','/api/contracts/'+a+'/txs'])

    def test_network_projection_never_returns_peer_ips_or_unfiltered_health(self):
        def public(path,params=None):
            return {'/api/peers':{'peers':[{'ip':'192.168.1.10','port':8333}], 'localCoreVersion':'1.2'},
                    '/api/supply':{'circulatingSupply':123,'rpcCookie':'never'},
                    '/api/chain':{'network':'mainnet','localWallet':'never'},
                    '/api/health':{'status':'ok','peerAddresses':['192.168.1.10']},
                    '/api/token-burn':{'burnAddress':'T'+'1'*33,'credentials':'never'},
                    '/api/uptime':{'uptimeSeconds':1000}}[path]
        with patch.object(self.node,'public',side_effect=public):r=self.node.network()
        raw=json.dumps(r)
        self.assertNotIn('192.168.1.10',raw)
        self.assertNotIn('never',raw)
        self.assertEqual(r['peers']['count'],1)
        self.assertEqual(r['supply']['circulatingSupply'],123)

class MediaRouteTests(DemoHttpTests):
    def test_v11_routes_exist(self):
        for path in ('/api/v1/addresses','/api/v1/contracts','/api/v1/network','/api/v1/contract-activity/'+'T'+'1'*33):
            data=self.get(path)
            self.assertFalse(data['available'])
        with self.assertRaises(HTTPError) as e:
            urlopen(self.base()+'/api/v1/contract-activity/../../.env')
        self.assertIn(e.exception.code,(400,404))

    def test_asset_files_and_range_support(self):
        for path, content_type in [('/assets/tru-atlas-logo.webp','image/webp'),('/assets/tru-hero-poster.webp','image/webp')]:
            with urlopen(self.base()+path) as resp:
                self.assertEqual(resp.status,200)
                self.assertEqual(resp.headers.get_content_type(),content_type)
                self.assertTrue(len(resp.read())>1000)
        req=Request(self.base()+'/assets/tru-hero-once.mp4',headers={'Range':'bytes=0-127'})
        with urlopen(req) as resp:
            self.assertEqual(resp.status,206)
            self.assertEqual(len(resp.read()),128)
            self.assertEqual(resp.headers.get('Accept-Ranges'),'bytes')
            self.assertTrue(resp.headers.get('Content-Range').startswith('bytes 0-127/'))
        req=Request(self.base()+'/assets/tru-hero-once.mp4',headers={'Range':'bytes=9999999-'})
        with self.assertRaises(HTTPError) as e:urlopen(req)
        self.assertEqual(e.exception.code,416)

if __name__ == '__main__': unittest.main()
