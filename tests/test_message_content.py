"""Synthetic cards only: no real article URLs, messages, or payment identifiers."""
import datetime
import html
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from compression import zstd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from message_content import parse_message, article_key, html_text, export_text
from reader import Reader

TEMP = Path(__file__).resolve().parents[1] / 'private' / 'test-temp'
TEMP.mkdir(parents=True, exist_ok=True)
URL = 'https://mp.weixin.qq.com/s?__biz=synthetic&mid=123&idx=1&sn=example&scene=1'


def card(subtype, title='', extra=''):
    return '<msg><appmsg><type>' + str(subtype) + '</type><title>' + html.escape(title) + '</title>' + extra + '</appmsg></msg>'


def article(url=URL, title='摄影大赛 & 征稿'):
    return card(5, title, '<url>' + html.escape(url) + '</url><sourceusername>gh_synthetic</sourceusername><sourcedisplayname>校园宣传部</sourcedisplayname>')


def quote(content, kind=49):
    return card(57, '这篇推文可以参考', '<refermsg><type>' + str(kind) + '</type><displayname>张同学</displayname><content>' + html.escape(content) + '</content></refermsg>')


class ArticleTests(unittest.TestCase):
    def test_local_title_url_and_account_need_no_web_request(self):
        result = parse_message(49, 'wxid_synthetic:\n' + article())
        self.assertEqual(result['messageKind'], 'article')
        self.assertIn('摄影大赛 & 征稿', result['text'])
        self.assertIn('公众号：校园宣传部', result['text'])
        self.assertIn(URL, result['text'])
        self.assertNotIn('<appmsg>', result['text'])
        self.assertEqual(result['links'], [URL])
        self.assertEqual(len(result['articles']), 1)

    def test_identity_keeps_distinct_articles_and_handles_temporary_urls(self):
        shared = URL.replace('scene=1', 'scene=9&sharer_shareinfo=different')
        self.assertEqual(article_key(URL), article_key(shared))
        self.assertNotEqual(article_key(URL), article_key(URL.replace('idx=1', 'idx=2')))
        self.assertNotEqual(article_key(URL), article_key(URL.replace('mid=123', 'mid=124')))
        self.assertNotEqual(article_key(URL), article_key(URL.replace('__biz=synthetic', '__biz=another')))
        temporary = 'https://mp.weixin.qq.com/s?__biz=synthetic&tempkey=one'
        self.assertNotEqual(article_key(temporary), article_key(temporary.replace('one', 'two')))
        self.assertNotEqual(article_key(URL), article_key(URL + '&idx=2'))
        self.assertEqual(article_key('https://mp.weixin.qq.com/s/only-synthetic?scene=1'), article_key('https://mp.weixin.qq.com/s/only-synthetic?scene=9'))
        self.assertEqual(article_key('https://mp.weixin.qq.com.evil.example/s/token'), '')

    def test_missing_fields_and_normal_web_link(self):
        result = parse_message(49, card(5, extra='<url>' + html.escape(URL) + '</url>'))
        self.assertEqual(result['messageKind'], 'article')
        self.assertIn('标题：本地消息未提供', result['text'])
        web = parse_message(49, card(5, '普通网页', '<url>https://example.org/page</url>'))
        self.assertEqual(web['messageKind'], 'link')
        self.assertFalse(web['articles'])
        missing = parse_message(49, card(5, '离线标题', '<sourceusername>gh_synthetic</sourceusername>'))
        self.assertEqual(missing['messageKind'], 'article')
        self.assertIn('离线标题', missing['text'])
        self.assertFalse(missing['links'])
        self.assertFalse(missing['articles'])

    def test_quote_and_pasted_link_share_article_identity(self):
        direct = parse_message(49, article())
        reply = parse_message(49, quote('wxid_synthetic:\n' + article()))
        pasted = parse_message(1, '参考这篇：' + URL + '。')
        self.assertEqual(reply['messageKind'], 'quote')
        self.assertIn('这篇推文可以参考', reply['text'])
        self.assertIn('引用 张同学', reply['text'])
        self.assertEqual(reply['articles'], direct['articles'])
        numbers = {}
        for result in (direct, reply, pasted):
            self.assertIn('文章编号：A001', export_text(result, numbers))
        self.assertEqual(len(numbers), 1)
        self.assertIn('文章编号：A002', export_text(parse_message(49, article(URL.replace('mid=123', 'mid=999'))), numbers))

    def test_plain_and_missing_quoted_content_and_depth_bound(self):
        self.assertIn('请周三前完成', parse_message(49, quote('请周三前完成', 1))['text'])
        self.assertIn('本地消息未提供', parse_message(49, card(57, '回复'))['text'])
        self.assertIn('本地消息未提供', parse_message(49, quote(''))['text'])
        for bad_type in ('²', '9' * 5000):
            malformed = card(57, '回复', '<refermsg><type>' + bad_type + '</type><content>正文</content></refermsg>')
            self.assertEqual(parse_message(49, malformed)['messageKind'], 'quote')
        nested = article()
        for _ in range(6):
            nested = quote(nested)
        self.assertIn('层级过多', parse_message(49, nested)['text'])


class CardClassificationTests(unittest.TestCase):
    def test_files_payment_cards_and_other_known_types(self):
        cases = [(6, 'file', '文件名：宣传安排.docx'), (2000, 'transfer', '[转账]'),
                 (2001, 'red_packet', '[红包]'), (19, 'record', '[合并聊天记录]'),
                 (33, 'miniapp', '[小程序]'), (36, 'miniapp', '[小程序]'),
                 (51, 'channels', '[视频号]')]
        for subtype, kind, expected in cases:
            with self.subTest(subtype=subtype):
                value = card(subtype, '宣传安排.docx', '<wcpayinfo><pay_memo>活动经费</pay_memo><transferid>DO-NOT-EXPORT</transferid><nativeurl>wxpay://DO-NOT-EXPORT</nativeurl></wcpayinfo>')
                result = parse_message(49, value)
                self.assertEqual(result['messageKind'], kind)
                self.assertIn(expected, result['text'])
                self.assertNotIn('DO-NOT-EXPORT', json.dumps(result))
                self.assertFalse(result['links'])
                if subtype in (2000, 2001):
                    self.assertIn('备注：活动经费', result['text'])

    def test_pat_uses_contact_names_and_suffix(self):
        info = '<patinfo><fromusername>wxid_a</fromusername><pattedusername>wxid_b</pattedusername><patsuffix>的肩膀</patsuffix><template>${wxid_a} 拍了拍 ${wxid_b}的肩膀</template></patinfo>'
        result = parse_message(49, card(62, extra=info), {'wxid_a': '张同学', 'wxid_b': '李同学'})
        self.assertEqual(result['messageKind'], 'pat')
        self.assertIn('张同学 拍了拍 李同学的肩膀', result['text'])
        self.assertNotIn('${', result['text'])
        unknown = parse_message(49, card(62, extra=info))
        self.assertIn('未知成员', unknown['text'])

    def test_system_text_revoke_and_template_hide_raw_xml(self):
        system = parse_message(10000, '某同学加入了群聊')
        self.assertIn('某同学加入了群聊', system['text'])
        revoke = parse_message(10000, '<sysmsg type="revokemsg"><revokemsg><content>张同学撤回了一条消息</content></revokemsg></sysmsg>')
        self.assertEqual(revoke['messageKind'], 'revoke')
        self.assertIn('张同学撤回了一条消息', revoke['text'])
        template = '<sysmsg type="sysmsgtemplate"><sysmsgtemplate><content_template><template>$names$加入群聊</template><link_list><link name="names"><memberlist><member><nickname>张同学</nickname></member></memberlist></link></link_list></content_template></sysmsgtemplate></sysmsg>'
        self.assertIn('张同学加入群聊', parse_message(10000, template)['text'])
        self.assertNotIn('<sysmsg', parse_message(10000, '<sysmsg>broken')['text'])

    def test_malformed_unknown_and_entity_payloads_are_bounded(self):
        for value in ('not xml', '<msg><appmsg>', '<!DOCTYPE msg [<!ENTITY x "secret">]><msg><appmsg><title>&x;</title></appmsg></msg>', '<msg>' + 'x' * (1024 * 1024) + '</msg>'):
            result = parse_message(49, value)
            self.assertEqual(result['messageKind'], 'unknown')
            self.assertNotIn('<msg>', result['text'])
            self.assertNotIn('secret', result['text'])
        unknown = parse_message(49, card(98765, '未知卡片'))
        self.assertIn('类型 98765', unknown['text'])
        self.assertIn('未知卡片', unknown['text'])

    def test_only_safe_http_links_are_clickable_and_all_text_is_escaped(self):
        for bad in ('javascript:alert(1)', 'file:///C:/private/data', 'https://name:password@example.org/', 'https://example.org:bad/', 'https://example.org/\nsecret'):
            result = parse_message(49, card(5, '<script>标题</script>', '<url>' + html.escape(bad) + '</url>'))
            self.assertFalse(result['links'])
            rendered = html_text(result['text'], result['links'])
            self.assertNotIn('<script>', rendered)
            self.assertNotIn('href=', rendered)
        result = parse_message(49, article(title='<img src=x onerror=alert(1)>'))
        rendered = html_text(result['text'], result['links'])
        self.assertIn('&lt;img', rendered)
        self.assertNotIn('<img', rendered)
        self.assertIn('href="' + html.escape(URL, quote=True) + '"', rendered)
        self.assertIn('rel="noopener noreferrer"', rendered)


class ReaderCardIntegrationTests(unittest.TestCase):
    def test_compressed_high_word_types_quote_and_export_selection(self):
        import hashlib
        room = 'synthetic@chatroom'
        table = 'Msg_' + hashlib.md5(room.encode()).hexdigest()
        day = datetime.datetime(2026, 10, 20)
        stamp = int(day.timestamp())
        with tempfile.TemporaryDirectory(dir=TEMP) as directory:
            database = Path(directory) / 'synthetic.db'
            with closing(sqlite3.connect(database)) as db:
                db.execute('CREATE TABLE Name2Id(user_name TEXT)')
                db.execute("INSERT INTO Name2Id VALUES ('wxid_a')")
                db.execute(f'CREATE TABLE "{table}"(local_id INTEGER, local_type INTEGER,sort_seq INTEGER,real_sender_id INTEGER,create_time INTEGER,message_content,compress_content)')
                rows = [(1, (5 << 32) | 49, 1, 1, stamp, zstd.compress(article().encode()), None),
                        (2, 49, 2, 1, stamp + 1, None, zstd.compress(quote(article()).encode())),
                        (3, 49, 3, 1, stamp + 2, '<broken>', None),
                        (4, 1, 4, 1, stamp + 3, '讨论继续', None),
                        (5, 49, 5, 1, stamp + 4, b'\x28\xb5\x2f\xfdINVALID', None)]
                db.executemany(f'INSERT INTO "{table}" VALUES (?,?,?,?,?,?,?)', rows)
                db.commit()
            reader = Reader()
            reader.user = Path('wxid_a_1234')
            reader.names = {'wxid_a': '张同学', room: '合成示例群'}
            reader.databases = lambda: [(Path('message_0.db'), database)]
            messages = reader.messages(room, limit=None)
            self.assertEqual(len(messages), 5)
            self.assertEqual(messages[0]['messageKind'], 'article')
            self.assertEqual(messages[1]['messageKind'], 'quote')
            self.assertEqual(messages[2]['messageKind'], 'unknown')
            self.assertEqual(messages[3]['text'], '讨论继续')
            self.assertEqual(messages[4]['messageKind'], 'unknown')
            self.assertIn('暂无法解码', messages[4]['text'])
            path = Path(directory) / 'messages.html'
            req = {'chat': room, 'start': '2026-10-20', 'end': '2026-10-20', 'path': str(path)}
            self.assertEqual(reader.export(req)['count'], 5)
            doc = path.read_text(encoding='utf-8')
            self.assertEqual(doc.count('文章编号：A001'), 2)
            self.assertIn('校园宣传部', doc)
            self.assertIn('这篇推文可以参考', doc)
            self.assertIn('讨论继续', doc)
            self.assertNotIn('<appmsg>', doc)
            self.assertIn("default-src 'none'", doc)
            req['selected'] = ['message_0.db:2']
            self.assertEqual(reader.export(req)['count'], 1)
            selected = path.read_text(encoding='utf-8')
            self.assertIn('文章编号：A001', selected)
            self.assertIn(URL.replace('&', '&amp;'), selected)
            self.assertNotIn('讨论继续', selected)


if __name__ == '__main__':
    unittest.main()
