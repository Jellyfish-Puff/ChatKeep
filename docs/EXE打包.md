# 独立EXE打包

默认输出：`dist/ChatKeep.exe`，Windows x64。v0.1.1约82.3 MiB；含新增解码组件的0.1.2开发版约134.1 MiB。已包含定稿的纯色扁平图标。

## 打包方法

读取模块使用PyInstaller 6.22.3单文件封装，带Python 3.14解释器、cryptography、Pillow和标准库。0.1.2本地开发版另包含PyAV 19.0.1及随附FFmpeg动态库，无需用户安装FFmpeg或更改PATH。WPF通过.NET 10 self-contained single-file发布，将读取EXE作为嵌入资源封装在主EXE中。未启用裁剪。

首次连接在EXE旁的private/runtime目录解包读取组件，按SHA-256校验复用；子进程通过标准输入输出交换数据，隐藏控制台。数据缓存与导出目录都按EXE所在目录定位，不再依赖源码位置或启动时工作目录。

## 重建

在工作区安装构建工具，不修改系统Python：

```powershell
python -m pip install -r requirements.txt
python -m pip install --target build/python-tools pyinstaller==6.22.3
./tools/package.ps1
```

仅重建桌面外壳时可使用 `./tools/package.ps1 -SkipReader`，但读取模块源码修改后必须完整重新封装。

可用 `./tools/package.ps1 -OutputDirectory dist/preview-0.1.1` 将本地测试版放在独立目录，保留旧版 EXE 和数据。打包会在目标目录同时生成依赖许可证压缩包和对应的 `SHA256SUMS.txt`。测试版首次使用会在其自己的目录生成缓存与导出文件，不会自动复用旧版数据。

0.1.2本地开发版位于 `dist/preview-0.1.2/ChatKeep.exe`，约134.1 MiB；公开v0.1.1及其本地发布副本保留。新增依赖可按 `requirements.txt` 安装，或使用 `python -m pip install --target build/python-tools av==19.0.1` 安装在工作区。源码读取组件也支持此工作区依赖位置。PyInstaller自带av hook负责收集Python扩展和av.libs动态库，不能只复制av的Python文件。

`python tools/check_image_package.py` 对封装读取EXE进行离线合成图片解码验证。`--render-preview --image-preview` 生成带合成大图与查看按钮的桌面预览，不读取真实消息。

0.1.3修复版位于 `dist/preview-0.1.3/ChatKeep.exe`，保留0.1.2的大图功能；本次只修改桌面显示，可复用已完整封装的0.1.2读取组件：`./tools/package.ps1 -SkipReader -OutputDirectory dist/preview-0.1.3`。全新工作区仍需先完整打包，不可省略读取模块。

0.1.4图片查看改进版位于 `dist/preview-0.1.4/ChatKeep.exe`，同样只修改桌面界面，可用 `./tools/package.ps1 -SkipReader -OutputDirectory dist/preview-0.1.4` 复用已有读取组件。缩放使用WPF现有控件和变换，不增加依赖，不需要默认图片查看器或临时图片文件。

本机最终0.1.4 EXE为140669815字节，比0.1.3增加9216字节（9 KiB）。独立目录、无外部Python/.NET路径下的合成图片界面启动检查通过；旧版本EXE保留。

## v0.1.5 批量导出

v0.1.5 批量导出版使用 `./tools/package.ps1 -OutputDirectory dist/preview-0.1.5` 完整重封装。此次读取代码和 HTML 渲染代码有变动，不能使用 `-SkipReader`。正式成品副本位于 `dist/release-v0.1.5/ChatKeep.exe`，与用户确认的测试版字节一致，140692343 字节。旧成品及其缓存均保留；不要将根目录 `dist/ChatKeep.exe` 误当作新版。

## 2026-10-18验证

- 原有3组自动化测试全部通过。
- Release独立发布成功。
- 最终主EXE复制到build/isolated-app，无任何源码；PATH仅保留Windows System32，DOTNET_ROOT指定不存在的目录，DOTNET_MULTILEVEL_LOOKUP设为0。
- 主EXE通过`--package-check`实际连接微信，退出码0。
- 独立读取EXE在PATH无Python环境下成功读取最近消息与图片，并完成单条HTML导出。
- 测试聊天数据只写入build下的隔离目录，未打入发布EXE。

诊断脚本：`tools/check_packaged_reader.py`。主EXE支持`--package-check`诊断参数，输出只含成功状态及群聊数量，不写入消息正文。
