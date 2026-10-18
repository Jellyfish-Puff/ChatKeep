import datetime, hashlib, hmac, json, sqlite3, struct, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from reader import Reader, decrypt_page, page_mac, valid
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
TEST_TEMP=Path(__file__).resolve().parents[1]/'private'/'test-temp'
TEST_TEMP.mkdir(parents=True,exist_ok=True)

class CryptoTests(unittest.TestCase):
    def test_authenticated_page_roundtrip_and_tamper(self):
        key=bytes(range(32)); salt=bytes(range(16)); iv=bytes(reversed(range(16)))
        plain=b'SQLite format 3\0'+bytes((i%251 for i in range(4000)))
        cipher=Cipher(algorithms.AES(key),modes.CBC(iv)).encryptor()
        encrypted=cipher.update(plain[16:])+cipher.finalize()
        mac_key=hashlib.pbkdf2_hmac('sha512',key,bytes(b^0x3a for b in salt),2,32)
        page=salt+encrypted+iv+hmac.digest(mac_key,encrypted+iv+struct.pack('<I',1),'sha512')
        self.assertTrue(valid(key,page)); self.assertEqual(decrypt_page(page,key,1),plain+bytes(80))
        corrupt=bytearray(page);corrupt[100]^=1
        self.assertFalse(page_mac(bytes(corrupt),key,salt,1));self.assertFalse(valid(bytes(32),page))

class PaginationTests(unittest.TestCase):
    def test_timestamp_ties_are_never_dropped(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as directory:
            path=Path(directory)/'test.db'; user='synthetic@chatroom'; table='Msg_'+hashlib.md5(user.encode()).hexdigest()
            db=sqlite3.connect(path)
            db.execute('CREATE TABLE Name2Id(user_name TEXT)');db.execute("INSERT INTO Name2Id VALUES ('wxid_synthetic')")
            db.execute(f'CREATE TABLE "{table}"(local_id INTEGER,local_type INTEGER,sort_seq INTEGER,real_sender_id INTEGER,create_time INTEGER,message_content TEXT)')
            db.executemany(f'INSERT INTO "{table}" VALUES (?,1,?,1,1000,?)',[(i,i,str(i)) for i in range(1,351)])
            db.execute(f'INSERT INTO "{table}" VALUES (0,1,0,1,999,\'older\')');db.commit();db.close()
            reader=Reader();reader.user=Path('wxid_synthetic_abcd');reader.databases=lambda:[(Path('message_0.db'),path)]
            first=reader.messages(user,limit=100)
            self.assertEqual(len(first),350);self.assertEqual([m['text'] for m in first],[str(i) for i in range(1,351)])
            second=reader.messages(user,before=1000,limit=100)
            self.assertEqual(len(second),1);self.assertTrue(first[0]['self'])

class ExportTests(unittest.TestCase):
    def test_inclusive_end_date_selection_and_safe_embedded_html(self):
        reader=Reader();reader.names={'room':'<测试群>'}
        day=datetime.datetime(2026,10,17)
        stamp=lambda h:int((day+datetime.timedelta(hours=h)).timestamp())
        rows=[{'id':str(i),'time':t,'sender':'<发送者>','self':False,'type':3 if i==2 else 1,'text':'<script>alert(1)</script>\n原文','image':'data:image/png;base64,YQ==' if i==2 else None} for i,t in enumerate([stamp(0),stamp(23)+3599,stamp(12),stamp(24)])]
        def messages(chat,start,end,limit,selected):
            return [m for m in rows if start<=m['time']<end and (selected is None or m['id'] in selected)]
        reader.messages=messages
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as directory:
            path=Path(directory)/'chat.html'; req={'chat':'room','start':'2026-10-17','end':'2026-10-17','path':str(path)}
            result=reader.export(req);self.assertEqual(result['count'],3)
            html=path.read_text(encoding='utf-8');self.assertIn('&lt;script&gt;',html);self.assertNotIn('<script>',html);self.assertIn('data:image/png;base64,YQ==',html);self.assertIn('23:59:59',html);self.assertIn('&lt;测试群&gt;',html)
            req['selected']=['2'];self.assertEqual(reader.export(req)['count'],1)
            req['selected']=[];before=path.read_bytes()
            with self.assertRaises(ValueError):reader.export(req)
            self.assertEqual(path.read_bytes(),before)
            req['start']='2026-10-18'
            with self.assertRaises(ValueError):reader.export(req)

if __name__=='__main__':unittest.main()
