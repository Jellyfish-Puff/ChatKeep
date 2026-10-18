# 独立EXE打包

交付文件：`dist/ChatKeep.exe`，Windows x64，约82.3 MiB。已包含定稿的纯色扁平图标。

## 打包方法

读取模块使用PyInstaller 6.22.3单文件封装，带Python 3.14解释器、cryptography、Pillow和标准库。WPF通过.NET 10 self-contained single-file发布，将读取EXE作为嵌入资源封装在主EXE中。未启用裁剪。

首次连接在EXE旁的private/runtime目录解包读取组件，按SHA-256校验复用；子进程通过标准输入输出交换数据，隐藏控制台。数据缓存与导出目录都按EXE所在目录定位，不再依赖源码位置或启动时工作目录。

## 重建

在工作区安装构建工具，不修改系统Python：

```powershell
python -m pip install -r requirements.txt
python -m pip install --target build/python-tools pyinstaller==6.22.3
./tools/package.ps1
```

仅重建桌面外壳时可使用 `./tools/package.ps1 -SkipReader`，但读取模块源码修改后必须完整重新封装。

## 2026-10-18验证

- 原有3组自动化测试全部通过。
- Release独立发布成功。
- 最终主EXE复制到build/isolated-app，无任何源码；PATH仅保留Windows System32，DOTNET_ROOT指定不存在的目录，DOTNET_MULTILEVEL_LOOKUP设为0。
- 主EXE通过`--package-check`实际连接微信，退出码0。
- 独立读取EXE在PATH无Python环境下成功读取最近消息与图片，并完成单条HTML导出。
- 测试聊天数据只写入build下的隔离目录，未打入发布EXE。

诊断脚本：`tools/check_packaged_reader.py`。主EXE支持`--package-check`诊断参数，输出只含成功状态及群聊数量，不写入消息正文。
