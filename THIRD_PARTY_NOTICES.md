# 第三方参考

本项目独立实现 WPF 界面、消息查询和 HTML 导出。

`src/reader.py` 中 WCDB Config.Cipher 对象布局、XOR 掩码与只读查找流程参考并改写自 fanyuantaier/wechatauto-replica 的 `wechatauto/db.py`；图片容器结构参考该项目的 `wechatauto/media.py`。原作者项目采用 Apache License 2.0，完整许可证保存在 `licenses/wechatauto-replica-APACHE-2.0.txt`。本项目改动包括本地快照校验、逐页认证、WAL提交处理、无密钥落盘、单群分页查询及单文件HTML导出。

源代码：https://github.com/fanyuantaier/wechatauto-replica

SQLCipher 4 页面认证布局同时对照 tswawa/WechatVibe 的 `native-reader/wr/crypto.py` 与 `discovery.py`，采用 Apache License 2.0。许可证保存在 `licenses/WechatVibe-APACHE-2.0.txt`。

源代码：https://github.com/tswawa/WechatVibe

未使用 Wemory 的程序文件、界面脚本或辅助程序作为应用运行组件。此前对 Wemory 的静态研究报告仅作为方案研究资料。

本地图片兼容使用 PyAV 19.0.1（BSD-3-Clause）及其 Windows wheel 随附的 FFmpeg 动态库。当前 avcodec 运行时报告 LGPL version 3 or later；PyAV、LGPLv3 和其引用的 GPLv3 许可证文本保存在 `licenses/`，打包时同时收集 PyAV wheel 的许可证文件。新增组件用于本地 HEVC 解码，不调用网络协议或外部 FFmpeg 命令。

上游源码及对应构建来源：

- PyAV：https://github.com/PyAV-Org/PyAV/tree/v19.0.1
- PyAV FFmpeg 构建：https://github.com/PyAV-Org/pyav-ffmpeg/releases/tag/9.0.2-1
- FFmpeg：https://github.com/FFmpeg/FFmpeg/tree/n9.0.2

本项目未修改这些解码库。源码版可安装接口兼容的 PyAV/FFmpeg 动态库后重新打包；应用不为这些第三方库新增修改或调试限制。WXGF 预览仅转换可识别的 HEVC 图像流，复杂透明或动画内容明确标为首帧预览，不宣称完整还原。
