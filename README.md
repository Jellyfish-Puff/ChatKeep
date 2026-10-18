# 聊存 ChatKeep

<img src="src/ChatArchive/Assets/chat-archive.png" width="96" alt="ChatKeep 图标">

本地聊天，轻松保存。面向 Windows 的微信本地群聊记录浏览与 HTML 导出工具。

[下载 Windows EXE](https://github.com/Jellyfish-Puff/ChatKeep/releases/latest) · [版本记录](https://github.com/Jellyfish-Puff/ChatKeep/releases)

## 使用

从 Release 下载 `ChatKeep.exe` 后双击即可，无需CMD、Python或.NET安装。可以将这个EXE单独复制到其他可写文件夹运行。自行打包的文件位于 `dist/ChatKeep.exe`。

点击“连接微信”，选择群聊。可以勾选消息，或直接点击“导出聊天记录”，选择日期、HTML 格式和保存位置。

结束日期包含当天全天。勾选导出同时应用日期条件。图片嵌入 HTML，文件可以单独保存；缺失或无法解码的本地资源保留说明，不会请求网络下载。语音、视频、表情和卡片暂以类型占位。

本版仅展示群聊，支持搜索群名、加载更早消息。连接生成本地快照；需要更新记录时再次点击“连接微信”。不做后台自动同步。

## 独立EXE版本

Windows x64单文件版已包含.NET桌面运行时、Python解释器和读取依赖。首次连接时自动将内置读取组件解包到EXE旁的 `private/runtime`；数据缓存位于 `private/cache`，默认导出位于 `exports`。这些文件夹会在使用时自动创建，不需要从源码目录复制。

已验证：将EXE复制到无源码文件夹、移除Python PATH并指定无外部.NET目录后，仍能连接微信、读取消息与图片、导出 HTML。

![ChatKeep 界面示例](docs/interface-preview.png)

界面示例使用合成消息。

## 源码开发依赖

- Windows 11，微信 4.1.15.13 登录运行。
- .NET 10 SDK。
- 64 位 Python 3.14，依赖见 `requirements.txt`。

源码开发版通过 Python 子进程读取数据；独立EXE使用内置读取组件。无需安装或启动 Wemory，无需重启微信。读取进程权限不足时可用管理员方式启动本应用。

## 数据存放

`private/cache` 是已解密数据库副本，`exports` 是默认导出目录，两者均不纳入版本管理。密钥仅存在于读取进程内存，关闭应用后释放，不写入日志或配置。应用不修改微信数据库或微信进程内存。

图片优先读取本地原件，再使用本地普通图片或缩略图。没有原件时无法生成原件。部分特殊图片容器尚未支持，会保留占位说明。

## 构建与检查

```powershell
python -m pip install -r requirements.txt
dotnet build src/ChatArchive/ChatArchive.csproj -c Release
python -m unittest discover -s tests -v
```

独立版本的可复现打包步骤见 `docs/EXE打包.md`。

技术验证与当前限制见 `docs/开发与验证.md`，第三方算法参考与许可证见 `THIRD_PARTY_NOTICES.md`。

## 使用范围

当前版本以 Windows 11、微信 4.1.15.13 为验证环境，其他版本需要进一步适配。请仅处理自己拥有或已获授权的本地聊天数据。
