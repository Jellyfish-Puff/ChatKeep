"""Exercise the sealed reader with no Python available on PATH. Prints counts only."""
import datetime, json, os, pathlib, queue, subprocess, sys, threading

workspace=pathlib.Path(__file__).resolve().parents[1]
executable=pathlib.Path(sys.argv[1]).resolve() if len(sys.argv)>1 else workspace/'build/reader/ChatReader.exe'
data=workspace/'build/isolated-reader';data.mkdir(parents=True,exist_ok=True)
env=os.environ.copy()
for name in list(env):
    if name.startswith('PYTHON'):env.pop(name)
env['PATH']=str(pathlib.Path(os.environ['SystemRoot'])/'System32')
env['CHATARCHIVE_DATA_ROOT']=str(data)
worker=subprocess.Popen([str(executable),'--serve'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',env=env,cwd=data,creationflags=subprocess.CREATE_NO_WINDOW)
lines=queue.Queue()
threading.Thread(target=lambda:[lines.put(line) for line in worker.stdout],daemon=True).start()
def request(value):
    worker.stdin.write(json.dumps(value,ensure_ascii=False)+'\n');worker.stdin.flush()
    result=json.loads(lines.get(timeout=120))
    if not result['ok']:raise RuntimeError(result['error'])
    return result['data']
try:
    result=request({'action':'connect'});chats=result['chats']
    report={'connected':True,'groups':len(chats),'pythonRemovedFromPath':True}
    if chats:
        chat=chats[0]['id'];messages=request({'action':'messages','chat':chat})
        report.update(messages=len(messages),images=sum(m['type']==3 for m in messages),decodedImages=sum(bool(m['image']) for m in messages))
        if messages:
            message=next((m for m in messages if m['image']),messages[-1]);day=datetime.datetime.fromtimestamp(message['time']).strftime('%Y-%m-%d')
            dest=data/'selected-message.html'
            exported=request({'action':'export','chat':chat,'start':day,'end':day,'selected':[message['id']],'path':str(dest)})
            report.update(exported=exported['count'],missingImages=exported['missingImages'])
    print(json.dumps(report))
finally:
    worker.stdin.close()
    try:worker.wait(timeout=10)
    except subprocess.TimeoutExpired:worker.kill();worker.wait()
