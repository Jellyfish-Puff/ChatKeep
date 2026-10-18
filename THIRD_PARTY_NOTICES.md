# 第三方参考

本项目独立实现 WPF 界面、消息查询和 HTML 导出。

`src/reader.py` 中 WCDB Config.Cipher 对象布局、XOR 掩码与只读查找流程参考并改写自 fanyuantaier/wechatauto-replica 的 `wechatauto/db.py`；图片容器结构参考该项目的 `wechatauto/media.py`。原作者项目采用 Apache License 2.0，完整许可证保存在 `licenses/wechatauto-replica-APACHE-2.0.txt`。本项目改动包括本地快照校验、逐页认证、WAL提交处理、无密钥落盘、单群分页查询及单文件HTML导出。

源代码：https://github.com/fanyuantaier/wechatauto-replica

SQLCipher 4 页面认证布局同时对照 tswawa/WechatVibe 的 `native-reader/wr/crypto.py` 与 `discovery.py`，采用 Apache License 2.0。许可证保存在 `licenses/WechatVibe-APACHE-2.0.txt`。

源代码：https://github.com/tswawa/WechatVibe

未使用 Wemory 的程序文件、界面脚本或辅助程序作为应用运行组件。此前对 Wemory 的静态研究报告仅作为方案研究资料。
