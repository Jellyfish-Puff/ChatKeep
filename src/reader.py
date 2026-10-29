"""Local-only WeChat reader. Never modifies WeChat files or process memory."""
import ctypes as C
from ctypes import wintypes as W
import hashlib, hmac, json, os, re, struct, sys, time, sqlite3
import base64, io, tempfile, shutil
from compression import zstd
from contextlib import closing
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from pathlib import Path
from message_content import parse_message
from batch_export import export_single, export_batch
from image_codec import WxgfDecoder, serve_codec, MAX_PIXELS
from image_resources import build_image_index, image_hashes, select_image

ROOT = Path(os.environ.get('CHATARCHIVE_DATA_ROOT') or (Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1])).resolve()
K = C.WinDLL('kernel32', use_last_error=True)
K.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]; K.OpenProcess.restype = W.HANDLE
K.CloseHandle.argtypes = [W.HANDLE]
K.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
K.VirtualQueryEx.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t]; K.VirtualQueryEx.restype = C.c_size_t

class MBI(C.Structure):
    _fields_ = [('base', C.c_void_p), ('allocation', C.c_void_p), ('allocation_protect', W.DWORD), ('partition', W.WORD), ('size', C.c_size_t), ('state', W.DWORD), ('protect', W.DWORD), ('type', W.DWORD)]

class PE(C.Structure):
    _fields_ = [('size', W.DWORD), ('usage', W.DWORD), ('pid', W.DWORD), ('heap', C.c_size_t), ('module', W.DWORD), ('threads', W.DWORD), ('parent', W.DWORD), ('priority', W.LONG), ('flags', W.DWORD), ('exe', W.WCHAR * 260)]

def processes():
    K.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD]; K.CreateToolhelp32Snapshot.restype=W.HANDLE
    K.Process32FirstW.argtypes=[W.HANDLE,C.POINTER(PE)]; K.Process32NextW.argtypes=[W.HANDLE,C.POINTER(PE)]
    handle=K.CreateToolhelp32Snapshot(2,0)
    try:
        item=PE(); item.size=C.sizeof(item)
        ok=K.Process32FirstW(handle,C.byref(item))
        while ok:
            if item.exe.lower() in ('weixin.exe','wechat.exe'): yield item.pid
            ok=K.Process32NextW(handle,C.byref(item))
    finally: K.CloseHandle(handle)

def roots():
    choices=[Path.home()/'Documents'/'xwechat_files',Path('D:/Program Files/Tencent/xwechat_files')]
    config=Path(os.environ['APPDATA'])/'Tencent/xwechat/config'
    for file in config.glob('*.ini'):
        for encoding in ('utf-8-sig','utf-16','gbk'):
            try:
                p=Path(file.read_text(encoding=encoding).strip()); choices += [p,p/'xwechat_files',p.parent/'xwechat_files']; break
            except (UnicodeError,OSError,ValueError): pass
    return list(dict.fromkeys(p for p in choices if p.is_dir()))

def accounts():
    return list(dict.fromkeys(p for root in roots() for p in root.iterdir() if (p/'db_storage').is_dir()))

def valid(key,page):
    if len(page)!=4096: return False
    salt=bytes(x^0x3a for x in page[:16])
    mac_key=hashlib.pbkdf2_hmac('sha512',key,salt,2,32)
    return hmac.compare_digest(hmac.digest(mac_key,page[16:4032]+struct.pack('<I',1),'sha512'),page[4032:4096])

def scan(pages):
    found={}; seen=set(); started=time.monotonic(); total=0
    literal=re.compile(rb"x'([0-9a-fA-F]{96})'")
    for pid in processes():
        process=K.OpenProcess(0x410,False,pid)
        if not process: continue
        try:
            address=0; info=MBI()
            while K.VirtualQueryEx(process,address,C.byref(info),C.sizeof(info)):
                if time.monotonic()-started>150: return found,total
                size=info.size
                if not size: break
                if info.state==0x1000 and info.type==0x20000 and not info.protect&0x101:
                    overlap=b''
                    for offset in range(0,size,4*1024*1024):
                        take=min(4*1024*1024,size-offset); buf=C.create_string_buffer(take); count=C.c_size_t()
                        K.ReadProcessMemory(process,address+offset,buf,take,C.byref(count))
                        chunk=overlap+buf.raw[:count.value]; total+=count.value
                        for match in literal.finditer(chunk):
                            raw=bytes.fromhex(match.group(1).decode()); key,salt=raw[:32],raw[32:]
                            if salt in pages and salt not in found and (key,salt) not in seen:
                                seen.add((key,salt))
                                if valid(key,pages[salt]): found[salt]=key
                        overlap=chunk[-128:]
                        if len(found)==len(pages): return found,total
                address+=size
        finally: K.CloseHandle(process)
    return found,total

def config_keys(pages):
    # WCDB Config.Cipher layout documented by wechatauto-replica (Apache-2.0).
    mask=bytes.fromhex('d2c7442458020000004889442450488b450048844c2448488944254048584c24')
    name=b'com.Tencent.WCDB.Config.Cipher'; found={}; total=0
    for pid in processes():
        process=K.OpenProcess(0x410,False,pid)
        if not process: continue
        def read(address,size):
            if not 0x10000<=address<0x800000000000 or not 0<size<=8*1048576: return b''
            buf=C.create_string_buffer(size); count=C.c_size_t()
            K.ReadProcessMemory(process,address,buf,size,C.byref(count)); return buf.raw[:count.value]
        def chunks():
            nonlocal total
            address=0; info=MBI()
            while K.VirtualQueryEx(process,address,C.byref(info),C.sizeof(info)):
                size=info.size
                if not size: break
                if info.state==0x1000 and not info.protect&0x101:
                    for offset in range(0,size,4*1048576):
                        data=read(address+offset,min(4*1048576,size-offset)); total+=len(data)
                        if data: yield address+offset,data
                address+=size
        try:
            names=[]
            for base,data in chunks():
                pos=data.find(name)
                while pos>=0: names.append(base+pos); pos=data.find(name,pos+1)
            if not names: continue
            patterns=[struct.pack('<QQ',p,len(name)) for p in names]
            for base,data in chunks():
                for pattern in patterns:
                    pos=data.find(pattern)
                    while pos>=0:
                        node=read(base+pos-16,80)
                        if len(node)>=48:
                            pointer=struct.unpack_from('<Q',node,40)[0]
                            obj=read(pointer+0x88,40)
                            if len(obj)>=24:
                                ptr,length=struct.unpack_from('<QQ',obj,8)
                                if 0<length<=1024:
                                    blob=read(ptr,length); decoded=bytes(v^mask[i%32] for i,v in enumerate(blob))
                                    for m in re.finditer(rb"[xX]'([0-9a-fA-F]{64,192})'",decoded):
                                        raw=bytes.fromhex(m.group(1).decode()); key=raw[:32]
                                        for salt,page in pages.items():
                                            if salt not in found and valid(key,page): found[salt]=key
                        pos=data.find(pattern,pos+1)
        finally: K.CloseHandle(process)
    return found,total

def probe():
    users=accounts(); pages={}; files=[]
    for user in users:
        for file in (user/'db_storage').rglob('*.db'):
            with file.open('rb') as f: page=f.read(4096)
            if len(page)==4096 and not page.startswith(b'SQLite format 3'):
                pages[page[:16]]=page; files.append(file)
    keys,scanned=config_keys(pages)
    return {'accounts':len(users),'databases':len(files),'validatedKeys':len(keys),'scannedMiB':scanned//1048576,'processes':len(list(processes()))},keys,users

def stamp(path):
    try:
        s=path.stat(); return s.st_size,s.st_mtime_ns
    except FileNotFoundError: return None

def decrypt_page(page,key,number):
    offset=16 if number==1 else 0
    decoder=Cipher(algorithms.AES(key),modes.CBC(page[4016:4032])).decryptor()
    return (b'SQLite format 3\0' if number==1 else b'')+decoder.update(page[offset:4016])+decoder.finalize()+bytes(80)

def page_mac(page,key,salt,number):
    mac_key=hashlib.pbkdf2_hmac('sha512',key,bytes(x^0x3a for x in salt),2,32)
    start=16 if number==1 else 0
    return hmac.compare_digest(hmac.digest(mac_key,page[start:4032]+struct.pack('<I',number),'sha512'),page[4032:])

def snapshot(path,keys):
    cache=ROOT/'private'/'cache'; cache.mkdir(parents=True,exist_ok=True)
    target=cache/(hashlib.sha256(str(path).encode()).hexdigest()[:20]+'.db')
    wal=Path(str(path)+'-wal'); marks=(stamp(path),stamp(wal))
    marker=target.with_suffix('.stamp')
    if target.exists() and marker.exists() and marker.read_text()==repr(marks): return target
    with path.open('rb') as f: salt=f.read(16)
    key=keys.get(salt)
    if key is None: raise RuntimeError('该数据库当前未取得有效读取密钥，请保持微信登录后重新连接。')
    for attempt in range(3):
        before=(stamp(path),stamp(wal)); temporary=target.with_suffix('.partial')
        capture=tempfile.TemporaryDirectory(prefix='capture-',dir=cache)
        try:
            captured=Path(capture.name)/'source.db'; captured_wal=Path(capture.name)/'source.db-wal'
            shutil.copyfile(path,captured)
            if wal.exists(): shutil.copyfile(wal,captured_wal)
            if before!=(stamp(path),stamp(wal)): raise RuntimeError('微信正在更新数据库，请稍后重试')
            with captured.open('rb') as source,temporary.open('w+b') as output:
                number=1
                while page:=source.read(4096):
                    if len(page)!=4096 or not page_mac(page,key,salt,number): raise RuntimeError('数据库页校验失败')
                    output.write(decrypt_page(page,key,number)); number+=1
                if captured_wal.exists() and captured_wal.stat().st_size>=32:
                    # Only complete committed WAL transactions with the current header salts.
                    with captured_wal.open('rb') as wf:
                        header=wf.read(32); frames=[]; committed=0; dbsize=0
                        magic,version,psize=struct.unpack('>III',header[:12])
                        if magic not in (0x377f0682,0x377f0683) or psize!=4096: raise RuntimeError('不支持的WAL格式')
                        endian='<' if magic==0x377f0682 else '>'
                        def checksum(data,s1=0,s2=0):
                            words=struct.unpack(endian+str(len(data)//4)+'I',data)
                            for i in range(0,len(words),2):
                                s1=(s1+words[i]+s2)&0xffffffff; s2=(s2+words[i+1]+s1)&0xffffffff
                            return s1,s2
                        sums=checksum(header[:24])
                        if sums!=struct.unpack('>II',header[24:]): raise RuntimeError('WAL头校验失败')
                        while frame:=wf.read(4120):
                            if len(frame)!=4120 or frame[8:16]!=header[16:24]: break
                            sums=checksum(frame[:8]+frame[24:],*sums)
                            if sums!=struct.unpack('>II',frame[16:24]): break
                            pg,commit=struct.unpack('>II',frame[:8])
                            if pg<1: break
                            frames.append((pg,frame[24:]))
                            if commit: committed=len(frames); dbsize=commit
                        for pg,page in frames[:committed]:
                            if not page_mac(page,key,salt,pg): raise RuntimeError('WAL消息页校验失败')
                            output.seek((pg-1)*4096); output.write(decrypt_page(page,key,pg))
                        if dbsize: output.truncate(dbsize*4096)
            with closing(sqlite3.connect(temporary)) as db:
                if db.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise RuntimeError('数据副本完整性检查失败')
            temporary.replace(target); marker.write_text(repr(before)); return target
        except (OSError,RuntimeError,sqlite3.Error):
            temporary.unlink(missing_ok=True)
            if attempt==2: raise
        finally: capture.cleanup()
    raise RuntimeError('无法取得一致数据副本')

def inspect_schema():
    stats,keys,users=probe(); out=[]
    for user in users:
        for rel in ['session/session.db','contact/contact.db']:
            path=user/'db_storage'/rel
            try:
                target=snapshot(path,keys)
                with closing(sqlite3.connect(target)) as db:
                    tables=db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'").fetchall()
                out.append({'database':rel,'tables':tables})
            except RuntimeError: pass
    return {'stats':stats,'schemas':out}

def text(value):
    if value is None: return ''
    if isinstance(value,str): return value
    raw=bytes(value)
    if raw.startswith(b'\x28\xb5\x2f\xfd'): raw=zstd.decompress(raw)
    return raw.decode('utf-8',errors='replace')

class Reader:
    def __init__(self):
        self.keys={}; self.user=None; self.names={}; self.shards=[]; self.image_key=None; self.image_index={}; self.image_key_attempted=False
        self.image_decoder=WxgfDecoder()

    def close(self):
        self.image_decoder.close()

    def connect(self):
        stats,keys,users=probe()
        candidates=[]
        for user in users:
            session=user/'db_storage/session/session.db'
            if session.exists():
                with session.open('rb') as f: salt=f.read(16)
                if salt in keys: candidates.append(user)
        if len(candidates)!=1: raise RuntimeError('未能唯一识别已登录账号，请确保只有一个微信账号处于登录状态。')
        self.user=candidates[0]; self.keys=keys; self.shards=[]; self.image_index={}; self.image_key=None; self.image_key_attempted=False
        if hasattr(self,'image_xor'): del self.image_xor
        contact=snapshot(self.user/'db_storage/contact/contact.db',keys)
        with closing(sqlite3.connect(contact)) as db:
            self.names={row[0]:row[2] or row[1] or row[0] for row in db.execute('SELECT username,nick_name,remark FROM contact')}
        session=snapshot(self.user/'db_storage/session/session.db',keys)
        with closing(sqlite3.connect(session)) as db:
            chats=[{'id':r[0],'name':self.names.get(r[0],r[0]),'summary':text(r[1]),'time':r[2]} for r in db.execute("SELECT username,summary,last_timestamp FROM SessionTable WHERE is_hidden=0 AND username LIKE '%@chatroom' ORDER BY sort_timestamp DESC")]
        return {'chats':chats,'status':f'已连接 · {len(chats)} 个群聊','stats':stats}

    def databases(self):
        if not self.user: raise RuntimeError('请先连接微信')
        if not self.shards:
            for path in sorted((self.user/'db_storage/message').glob('message_*.db')):
                if re.fullmatch(r'message_\d+\.db',path.name):
                    self.shards.append((path,snapshot(path,self.keys)))
        return self.shards

    def messages(self,chat,start=None,end=None,before=None,limit=100,selected=None):
        table='Msg_'+hashlib.md5(chat.encode()).hexdigest(); output=[]
        # Newly downloaded local images must be visible on the next load/export.
        self.image_index.pop(chat,None)
        for source,cached in self.databases():
            with closing(sqlite3.connect(cached)) as db:
                db.row_factory=sqlite3.Row
                if not db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(table,)).fetchone(): continue
                names={r[0]:r[1] for r in db.execute('SELECT rowid,user_name FROM Name2Id')}
                clauses=[]; params=[]
                if start is not None: clauses.append('create_time>=?'); params.append(start)
                if end is not None: clauses.append('create_time<?'); params.append(end)
                if before is not None: clauses.append('create_time<?'); params.append(before)
                where=' WHERE '+' AND '.join(clauses) if clauses else ''
                sql=f'SELECT * FROM "{table}"'+where+' ORDER BY create_time DESC,sort_seq DESC,local_id DESC'
                if limit:
                    boundary=db.execute(sql+' LIMIT ?',params+[limit]).fetchall()
                    if not boundary: continue
                    cutoff=int(boundary[-1]['create_time'])
                    where2=(where+' AND ' if where else ' WHERE ')+'create_time>=?'
                    sql=f'SELECT * FROM "{table}"'+where2+' ORDER BY create_time DESC,sort_seq DESC,local_id DESC'; params.append(cutoff)
                for row in db.execute(sql,params):
                    r=dict(row); identity=source.name+':'+str(r['local_id'])
                    if selected is not None and identity not in selected: continue
                    kind=int(r.get('local_type',0))&0xffffffff
                    decode_error=False
                    try:
                        body=text(r.get('message_content') or r.get('compress_content'))
                    except (ValueError, TypeError, zstd.ZstdError):
                        body=''; decode_error=True
                    sender=names.get(r.get('real_sender_id'),'未知发送者')
                    # Some group text records retain a sender prefix.
                    if body.startswith(sender+':\n'): body=body[len(sender)+2:]
                    msg={'id':identity,'time':int(r['create_time']),'sort':int(r.get('sort_seq') or 0),'sender':self.names.get(sender,sender),'self':sender==self.user.name.rsplit('_',1)[0],'type':kind,'text':body,'image':None}
                    if kind==3:
                        msg['text']='[图片]'; msg['image']=self.image(chat,body,r.get('packed_info_data'))
                        info=self.last_image_info
                        msg.update(imageNote=info['note'],imageWidth=info['width'],imageHeight=info['height'],imageQuality=info['quality'],imageConverted=info['converted'],imageUnavailableAlternatives=info['unavailableAlternatives'])
                        if not msg['image']: msg['text']='[图片：'+info['note']+']'
                    else:
                        msg.update(parse_message(kind,body,self.names))
                        if decode_error: msg['text']='[消息正文暂无法解码]'
                    output.append(msg)
        output.sort(key=lambda m:(m['time'],m['sort'],int(m['id'].split(':')[-1]),m['id']))
        if limit and len(output)>limit:
            # Keep timestamp ties so previous-page boundary cannot drop messages.
            cutoff=output[-limit]['time']; output=[m for m in output if m['time']>=cutoff]
        return output

    def find_image_key(self,probe):
        seen=set(); started=time.monotonic()
        settings=Path(os.environ['APPDATA'])/'Tencent/xwechat'
        for file in settings.glob('net*/kvcomm/*.statistic'):
            match=re.match(r'(?:key_)?(\d+)_',file.name)
            if not match: continue
            code=match.group(1); wxid=self.user.name.rsplit('_',1)[0]
            key=hashlib.md5((code+wxid).encode()).hexdigest()[:16].encode()
            dec=Cipher(algorithms.AES(key),modes.ECB()).decryptor(); magic=dec.update(probe)
            if magic.startswith((b'\xff\xd8\xff',b'\x89PNG',b'GIF8',b'RIFF',b'wxgf')):
                self.image_xor=int(code)&255
                return key
        for pid in processes():
            handle=K.OpenProcess(0x410,False,pid)
            if not handle: continue
            try:
                address=0; info=MBI()
                while K.VirtualQueryEx(handle,address,C.byref(info),C.sizeof(info)):
                    if time.monotonic()-started>20: return None
                    size=info.size
                    if not size: break
                    if info.state==0x1000 and info.type==0x20000 and not info.protect&0x101:
                        for offset in range(0,size,4*1048576):
                            if time.monotonic()-started>20: return None
                            take=min(4*1048576,size-offset); buf=C.create_string_buffer(take); count=C.c_size_t()
                            K.ReadProcessMemory(handle,address+offset,buf,take,C.byref(count)); data=buf.raw[:count.value]
                            candidates=[m.group(1)[:16] for m in re.finditer(rb'(?<![a-zA-Z0-9])([a-zA-Z0-9]{32}|[a-zA-Z0-9]{16})(?![a-zA-Z0-9])',data)]
                            candidates += [m.group()[::2][:16] for m in re.finditer(rb'(?:[a-zA-Z0-9]\x00){32}',data)]
                            for key in candidates:
                                if key in seen: continue
                                seen.add(key); dec=Cipher(algorithms.AES(key),modes.ECB()).decryptor(); magic=dec.update(probe)
                                if magic.startswith((b'\xff\xd8\xff',b'\x89PNG',b'GIF8',b'RIFF',b'wxgf')): return key
                    address+=size
            finally: K.CloseHandle(handle)
        return None

    def image(self,chat,body,packed=None):
        hashes=image_hashes(body,packed)
        folder=self.user/'msg/attach'/hashlib.md5(chat.encode()).hexdigest()
        if hashes and chat not in self.image_index:
            self.image_index[chat]=build_image_index(folder)
        self.last_image_info=select_image(hashes,self.image_index.get(chat,{}),self.decode_image,self.image_decoder.decode)
        self.last_image_note=self.last_image_info['note']
        return self.last_image_info['uri']

    def decode_image(self,data):
        if data.startswith(b'wxgf'): return data
        if data.startswith(b'\x07\x08V2\x08\x07'):
            if len(data)<15: raise ValueError('图片不完整')
            aes_size,xor_size=struct.unpack_from('<II',data,6); block=(aes_size//16+1)*16
            if len(data)<15+block+xor_size: raise ValueError('图片不完整')
            if self.image_key is None and not self.image_key_attempted:
                self.image_key_attempted=True; self.image_key=self.find_image_key(data[15:31])
            if self.image_key is None: raise ValueError('图片密钥暂不可用')
            dec=Cipher(algorithms.AES(self.image_key),modes.ECB()).decryptor(); prefix=dec.update(data[15:15+block])+dec.finalize()
            pad=prefix[-1]
            if not 1<=pad<=16 or prefix[-pad:]!=bytes([pad])*pad: raise ValueError('图片校验失败')
            prefix=prefix[:-pad]; middle=data[15+block:len(data)-xor_size] if xor_size else data[15+block:]
            if xor_size:
                # JPEG end marker supplies the per-account XOR byte.
                if hasattr(self,'image_xor'): xor=self.image_xor
                elif prefix.startswith(b'\xff\xd8\xff'): xor=data[-1]^0xd9
                else: raise ValueError('尚未适配这种图片尾部格式')
                tail=bytes(v^xor for v in data[-xor_size:])
            else: tail=b''
            plain=prefix+middle+tail
            if xor_size and not hasattr(self,'image_xor') and prefix.startswith(b'\xff\xd8\xff') and plain.endswith(b'\xff\xd9'):
                from PIL import Image
                with Image.open(io.BytesIO(plain)) as image:
                    if not 0<image.width*image.height<=MAX_PIXELS: raise ValueError('图片超过本地像素限制')
                    image.load()
                self.image_xor=xor
            return plain
        for signature in (b'\xff\xd8\xff',b'\x89PNG',b'GIF8',b'RIFF'):
            key=data[0]^signature[0]
            if bytes(v^key for v in data[:len(signature)])==signature: return bytes(v^key for v in data)
        raise ValueError('不支持的图片格式')

    def export(self,request):
        return export_single(self,request)

    def export_batch(self,request,progress=None):
        return export_batch(self,request,progress)


def serve():
    reader=Reader()
    for line in sys.stdin:
        try:
            request=json.loads(line); action=request['action']
            if action=='connect': result=reader.connect()
            elif action=='messages': result=reader.messages(request['chat'],before=request.get('before'))
            elif action=='export': result=reader.export(request)
            elif action=='export_batch': result=reader.export_batch(request,lambda data: print(json.dumps({'event':'progress','data':data},ensure_ascii=False),flush=True))
            else: raise ValueError('未知操作')
            print(json.dumps({'ok':True,'data':result},ensure_ascii=False),flush=True)
        except Exception as exc:
            print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False),flush=True)
    reader.close()

if __name__=='__main__':
    if '--image-codec' in sys.argv: serve_codec()
    elif '--serve' in sys.argv: serve()
    elif '--schema' in sys.argv: print(json.dumps(inspect_schema(),ensure_ascii=False))
    else:
        result,_,_=probe(); print(json.dumps(result))
