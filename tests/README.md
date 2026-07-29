# 测试说明

测试按两层组织：

- `tests/test_*.py`：单模块行为、边界条件与前端静态契约，运行快，不启动系统级监听器。
- `tests/integration/`：跨模块业务链路。当前覆盖从选择预设、进入就绪、接收落点、执行绘制到写入历史记录。

统一运行入口：

```powershell
python -m tests.run unit
python -m tests.run integration
python -m tests.run
```

最后一个命令运行全部测试，适合提交或发布前回归。仍可使用标准库发现命令：

```powershell
python -m unittest discover -s tests -t .
```

## 编写新测试

优先复用 `tests.support`：

- `RegistryTestCase`：每个测试获得独立、自动清理的预设目录。
- `make_app_service`：隔离全局输入监听器、悬浮窗和真实鼠标注入。
- `make_preset`：生成使用真实数据模型的最小预设。
- `RecordingMouse`：记录鼠标操作，支持注入移动失败。
- `write_preset`、`png_data_url`：生成常用文件与预览数据。

测试具体业务结果，不依赖私有实现细节；只有输入路由、线程结束和静态前端契约等无法从公共接口触发的行为，才直接调用内部入口。新增跨模块链路时放入 `tests/integration/`，并确保不启动真实系统钩子、不移动真实鼠标、不弹出窗口。
