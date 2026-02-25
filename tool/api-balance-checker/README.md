# API 余额查询工具

查询长风、云驿、Codex 三个 API 平台的 Token 用量和余额。

## 运行

```bash
pip install -r requirements.txt
python main.py
```

Windows 也可以直接双击 `run_windows.bat` 启动（会自动检查 Python 和依赖）。

## 打包为 Windows exe

### 方式1：一键脚本（本机有 Python）
双击 `build_windows.bat`

### 方式2：GitHub 自动打包（本机不用装 Python，推荐）
仓库里已提供工作流：`.github/workflows/build-api-balance-checker.yml`

使用方法：
1. 把项目推送到 GitHub（至少包含 `api-balance-checker/` 和 `.github/workflows/`）
2. 打开 GitHub 仓库 → **Actions**
3. 选择 **Build API Balance Checker (Windows)**
4. 点 **Run workflow**
5. 构建完成后，在该次运行页面下载 Artifact：`api-balance-checker-windows`

下载后解压可得到：`api-balance-checker.exe`（可直接双击运行）

### 方式3：命令行
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "API余额查询" main.py
```

命令行方式生成的 exe 在 `dist/API余额查询.exe`。

## API 端点

| 平台 | 端点 | 认证方式 |
|------|------|---------|
| 长风 | `GET /api/v1/temp-api-keys/query?key=xxx` | API Key 直接查询 |
| 云驿 | `GET /user/api/v1/me` + `/batch-info` | Bearer Token |
| Codex | `POST /api/v1/auth/login` → `GET /auth/me` + `/subscriptions/*` | 邮箱+密码登录 |
