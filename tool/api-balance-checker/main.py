#!/usr/bin/env python3
"""API 余额监控中心（长风 / 云驿 / Codex）"""

from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext


APP_TITLE = "API 余额监控中心"


def _resolve_config_path() -> Path:
    # PyInstaller 单文件模式下 __file__ 在临时目录，不能用于持久化配置。
    if getattr(sys, "frozen", False):
        base = Path(os.getenv("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        cfg_dir = base / "APIBalanceChecker"
    else:
        cfg_dir = Path(__file__).resolve().parent

    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir / "config.json"


CONFIG_PATH = _resolve_config_path()

DEFAULT_CONFIG = {
    "changfeng": {"api_key": ""},
    "yunyi": {"api_key": ""},
    "codex": {"email": "", "password": ""},
    "auto_refresh_on_start": True,
}

STATUS_THEME = {
    "未查询": {"fg": "#6b7280", "bg": "#f3f4f6"},
    "查询中": {"fg": "#1d4ed8", "bg": "#dbeafe"},
    "成功": {"fg": "#166534", "bg": "#dcfce7"},
    "部分成功": {"fg": "#92400e", "bg": "#fef3c7"},
    "未配置": {"fg": "#374151", "bg": "#f3f4f6"},
    "失败": {"fg": "#991b1b", "bg": "#fee2e2"},
}


class APIBalanceDashboard:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1160x420")
        self.root.minsize(980, 360)
        self.root.configure(bg="#f3f6fb")

        self.config_data = self._load_config()
        self._refresh_total = 0
        self._refresh_done = 0

        self._init_style()
        self._build_ui()

        if self.config_data.get("auto_refresh_on_start", True):
            self.refresh_all()

    # ==================== UI ====================

    def _init_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Main.TFrame", background="#f3f6fb")
        style.configure("Header.TFrame", background="#111827")
        style.configure("Toolbar.TFrame", background="#1f2937")
        style.configure("TNotebook", background="#f3f6fb", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 6))

    def _build_ui(self):
        container = ttk.Frame(self.root, style="Main.TFrame")
        container.pack(fill=tk.BOTH, expand=True)

        # 顶部
        header = ttk.Frame(container, style="Header.TFrame", padding=(16, 14))
        header.pack(fill=tk.X)

        title = tk.Label(
            header,
            text=APP_TITLE,
            font=("Microsoft YaHei UI", 18, "bold"),
            fg="#ffffff",
            bg="#111827",
        )
        title.pack(side=tk.LEFT)

        sub = tk.Label(
            header,
            text="三平台余额 / 订阅 / 到期时间一屏总览",
            font=("Microsoft YaHei UI", 10),
            fg="#cbd5e1",
            bg="#111827",
        )
        sub.pack(side=tk.LEFT, padx=(14, 0), pady=(4, 0))

        # 工具条
        toolbar = ttk.Frame(container, style="Toolbar.TFrame", padding=(16, 10))
        toolbar.pack(fill=tk.X)

        self.last_update_var = tk.StringVar(value="上次刷新：-")
        tk.Label(
            toolbar,
            textvariable=self.last_update_var,
            font=("Microsoft YaHei UI", 10),
            fg="#e5e7eb",
            bg="#1f2937",
        ).pack(side=tk.LEFT)

        btn_wrap = ttk.Frame(toolbar, style="Toolbar.TFrame")
        btn_wrap.pack(side=tk.RIGHT)
        ttk.Button(btn_wrap, text="账号/API 配置", command=self.open_settings).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_wrap, text="刷新全部", command=self.refresh_all).pack(side=tk.LEFT)

        # 三张总览卡片
        cards_wrap = ttk.Frame(container, style="Main.TFrame", padding=(12, 12, 12, 6))
        cards_wrap.pack(fill=tk.X)
        for i in range(3):
            cards_wrap.columnconfigure(i, weight=1)

        self.cards = {
            "changfeng": self._build_card(
                cards_wrap,
                0,
                "长风 (Sub2API)",
                ["剩余额度", "今日用量", "到期时间", "总请求"],
            ),
            "yunyi": self._build_card(
                cards_wrap,
                1,
                "云驿",
                ["剩余额度", "今日用量", "到期时间", "Key名称"],
            ),
            "codex": self._build_card(
                cards_wrap,
                2,
                "Codex (vpsairobot)",
                ["账户", "主订阅", "今日用量", "到期时间", "剩余额度"],
            ),
        }

        # 底部状态条（按需保留，不再显示详情栏）
        bottom = tk.Frame(container, bg="#f3f6fb", padx=14, pady=10)
        bottom.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="就绪")
        tk.Label(
            bottom,
            textvariable=self.status_var,
            font=("Microsoft YaHei UI", 10),
            fg="#4b5563",
            bg="#f3f6fb",
            anchor="w",
        ).pack(fill=tk.X, side=tk.BOTTOM)

        self.detail_boxes: dict[str, scrolledtext.ScrolledText] = {}

    def _build_card(self, parent: ttk.Frame, column: int, title: str, fields: list[str]):
        card = tk.LabelFrame(
            parent,
            text=title,
            font=("Microsoft YaHei UI", 12, "bold"),
            fg="#111827",
            bg="#ffffff",
            bd=1,
            relief=tk.SOLID,
            padx=10,
            pady=10,
        )
        card.grid(row=0, column=column, sticky="nsew", padx=6)

        status_label = tk.Label(
            card,
            text="未查询",
            font=("Microsoft YaHei UI", 9, "bold"),
            fg=STATUS_THEME["未查询"]["fg"],
            bg=STATUS_THEME["未查询"]["bg"],
            padx=10,
            pady=2,
        )
        status_label.pack(anchor=tk.W, pady=(0, 8))

        values: dict[str, tk.StringVar] = {}
        for field in fields:
            row = tk.Frame(card, bg="#ffffff")
            row.pack(fill=tk.X, pady=2)
            row.columnconfigure(1, weight=1)

            tk.Label(
                row,
                text=f"{field}:",
                font=("Microsoft YaHei UI", 9),
                fg="#4b5563",
                bg="#ffffff",
            ).grid(row=0, column=0, sticky="w")

            var = tk.StringVar(value="-")
            tk.Label(
                row,
                textvariable=var,
                font=("Consolas", 10, "bold"),
                fg="#111827",
                bg="#ffffff",
                anchor="e",
                justify="right",
                wraplength=240,
            ).grid(row=0, column=1, sticky="e")
            values[field] = var

        update_var = tk.StringVar(value="更新时间：-")
        tk.Label(
            card,
            textvariable=update_var,
            font=("Microsoft YaHei UI", 8),
            fg="#6b7280",
            bg="#ffffff",
        ).pack(anchor=tk.W, pady=(8, 0))

        return {
            "status_label": status_label,
            "values": values,
            "update_var": update_var,
        }

    # ==================== Config ====================

    def _load_config(self) -> dict[str, Any]:
        if not CONFIG_PATH.exists():
            # 兼容旧版本：尝试从旧路径迁移配置
            for old_path in self._legacy_config_candidates():
                if old_path.exists():
                    try:
                        old_data = json.loads(old_path.read_text(encoding="utf-8"))
                        if isinstance(old_data, dict):
                            merged_old = self._merge_with_default(old_data)
                            CONFIG_PATH.write_text(
                                json.dumps(merged_old, ensure_ascii=False, indent=2),
                                encoding="utf-8",
                            )
                            return merged_old
                    except Exception:
                        pass

            CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
            return json.loads(json.dumps(DEFAULT_CONFIG))

        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = json.loads(json.dumps(DEFAULT_CONFIG))

        return self._merge_with_default(data)

    def _save_config(self):
        CONFIG_PATH.write_text(json.dumps(self.config_data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _merge_with_default(data: dict[str, Any]) -> dict[str, Any]:
        merged = json.loads(json.dumps(DEFAULT_CONFIG))
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k].update(v)
                else:
                    merged[k] = v
        return merged

    @staticmethod
    def _legacy_config_candidates() -> list[Path]:
        cands: list[Path] = []
        cands.append(Path(__file__).resolve().with_name("config.json"))
        if getattr(sys, "frozen", False):
            cands.append(Path(sys.executable).resolve().with_name("config.json"))
        # 去重
        uniq: list[Path] = []
        seen: set[str] = set()
        for p in cands:
            k = str(p)
            if k not in seen:
                seen.add(k)
                uniq.append(p)
        return uniq

    def open_settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("账号/API 配置")
        dlg.geometry("620x380")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        frm = ttk.Frame(dlg, padding=14)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="长风 API Key:").grid(row=0, column=0, sticky=tk.W, pady=6)
        cf_key = ttk.Entry(frm, width=60)
        cf_key.grid(row=0, column=1, sticky=tk.EW, pady=6)
        cf_key.insert(0, self.config_data.get("changfeng", {}).get("api_key", ""))

        ttk.Label(frm, text="云驿 API Key:").grid(row=1, column=0, sticky=tk.W, pady=6)
        yy_key = ttk.Entry(frm, width=60)
        yy_key.grid(row=1, column=1, sticky=tk.EW, pady=6)
        yy_key.insert(0, self.config_data.get("yunyi", {}).get("api_key", ""))

        ttk.Label(frm, text="Codex 邮箱:").grid(row=2, column=0, sticky=tk.W, pady=6)
        cx_email = ttk.Entry(frm, width=60)
        cx_email.grid(row=2, column=1, sticky=tk.EW, pady=6)
        cx_email.insert(0, self.config_data.get("codex", {}).get("email", ""))

        ttk.Label(frm, text="Codex 密码:").grid(row=3, column=0, sticky=tk.W, pady=6)
        cx_pwd = ttk.Entry(frm, width=60, show="*")
        cx_pwd.grid(row=3, column=1, sticky=tk.EW, pady=6)
        cx_pwd.insert(0, self.config_data.get("codex", {}).get("password", ""))

        auto_refresh_var = tk.BooleanVar(value=bool(self.config_data.get("auto_refresh_on_start", True)))
        ttk.Checkbutton(frm, text="软件启动后自动刷新三平台", variable=auto_refresh_var).grid(
            row=4, column=1, sticky=tk.W, pady=(10, 4)
        )

        ttk.Label(
            frm,
            text="提示：配置会保存在软件目录下 config.json（明文，建议仅在个人设备使用）",
            foreground="#6b7280",
        ).grid(row=5, column=1, sticky=tk.W, pady=(4, 12))

        frm.columnconfigure(1, weight=1)

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=1, sticky=tk.E)

        def do_save(refresh_after: bool):
            self.config_data["changfeng"]["api_key"] = cf_key.get().strip()
            self.config_data["yunyi"]["api_key"] = yy_key.get().strip()
            self.config_data["codex"]["email"] = cx_email.get().strip()
            self.config_data["codex"]["password"] = cx_pwd.get().strip()
            self.config_data["auto_refresh_on_start"] = bool(auto_refresh_var.get())
            self._save_config()
            messagebox.showinfo("成功", "配置已保存")
            dlg.destroy()
            if refresh_after:
                self.refresh_all()

        ttk.Button(btns, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="保存", command=lambda: do_save(False)).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="保存并刷新", command=lambda: do_save(True)).pack(side=tk.LEFT)

    # ==================== Actions ====================

    def refresh_all(self):
        self._set_status("正在刷新三平台数据...")
        self.last_update_var.set(f"上次刷新：{self._now_str()}")
        self._refresh_total = 3
        self._refresh_done = 0

        threading.Thread(target=self._refresh_changfeng, daemon=True).start()
        threading.Thread(target=self._refresh_yunyi, daemon=True).start()
        threading.Thread(target=self._refresh_codex, daemon=True).start()

    def _refresh_changfeng(self):
        api_key = self.config_data.get("changfeng", {}).get("api_key", "").strip()
        if not api_key:
            self._update_card(
                "changfeng",
                "未配置",
                {"剩余额度": "-", "今日用量": "-", "到期时间": "-", "总请求": "-"},
                "请在“账号/API 配置”中填写长风 API Key。",
            )
            return

        self._set_card_status("changfeng", "查询中")

        try:
            _, data = self._request_json(
                "GET",
                "https://cfjwlpro.com/api/v1/temp-api-keys/query",
                params={"key": api_key, "page": 1, "page_size": 10},
                timeout=20,
            )

            if not isinstance(data, dict):
                raise RuntimeError("返回不是 JSON 对象")
            if data.get("code") not in (0, 200, None):
                raise RuntimeError(data.get("message") or "返回异常")

            d = data.get("data")
            if isinstance(d, list):
                d = d[0] if d else {}
            if not isinstance(d, dict):
                d = {}

            if d.get("key_type") == "quota_only":
                remain = self._fmt_money(d.get("remaining_quota_usd"))
                used_today = self._fmt_money(d.get("total_cost_usd"))
            else:
                remain = self._fmt_maybe_int(d.get("remaining_requests"))
                used_today = f"{self._fmt_maybe_int(d.get('current_period_count'))} / {self._fmt_maybe_int(d.get('daily_limit'))}"

            expire_text = self._fmt_expire(d.get("expires_at"))
            status_text = self._cf_status(d)

            summary = {
                "剩余额度": remain,
                "今日用量": used_today,
                "到期时间": expire_text,
                "总请求": self._fmt_maybe_int(d.get("total_requests")),
            }

            detail = [
                "【长风查询结果】",
                f"状态: {status_text}",
                f"名称: {d.get('name', '-')}",
                f"分组: {d.get('group_name', '-')}",
                f"剩余额度/次数: {remain}",
                f"今日用量: {used_today}",
                f"总请求: {self._fmt_maybe_int(d.get('total_requests'))}",
                f"激活时间: {self._fmt_time(d.get('activated_at'))}",
                f"到期时间: {expire_text}",
                "",
                "原始响应:",
                json.dumps(data, ensure_ascii=False, indent=2),
            ]

            self._update_card("changfeng", "成功", summary, "\n".join(detail))
        except Exception as e:
            self._update_card(
                "changfeng",
                "失败",
                {"剩余额度": "-", "今日用量": "-", "到期时间": "-", "总请求": "-"},
                f"❌ 长风查询失败: {e}",
            )

    def _refresh_yunyi(self):
        api_key = self.config_data.get("yunyi", {}).get("api_key", "").strip()
        if not api_key:
            self._update_card(
                "yunyi",
                "未配置",
                {"剩余额度": "-", "今日用量": "-", "到期时间": "-", "Key名称": "-"},
                "请在“账号/API 配置”中填写云驿 API Key。",
            )
            return

        self._set_card_status("yunyi", "查询中")

        try:
            me_data = None
            attempts: list[str] = []

            header_candidates = [
                {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                {"authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                {"X-API-Key": api_key, "Content-Type": "application/json"},
                {"x-api-key": api_key, "Content-Type": "application/json"},
                {"Authorization": api_key, "Content-Type": "application/json"},
            ]

            for idx, headers in enumerate(header_candidates, 1):
                try:
                    resp, body = self._request_json(
                        "GET",
                        "https://yunyi.cfd/user/api/v1/me",
                        headers=headers,
                        timeout=20,
                    )
                    attempts.append(f"me 尝试#{idx}: HTTP {resp.status_code}, headers={list(headers.keys())}")

                    if resp.status_code < 400 and isinstance(body, dict) and not self._looks_like_error(body):
                        me_data = body
                        break

                    # 有些实现会把 data 放在 code!=0 下，这里只要确实有 data 就接收
                    if isinstance(body, dict) and isinstance(body.get("data"), (dict, list)):
                        me_data = body
                        break
                except Exception as e:
                    attempts.append(f"me 尝试#{idx}: 异常 {e}")

            # batch-info：前端实际是 POST /user/api/v1/batch-info {keys:[...]}。
            batch_data = None
            batch_errors: list[str] = []

            batch_try = [
                ({"Content-Type": "application/json"}, {"keys": [api_key]}),
                ({"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, {"keys": [api_key]}),
            ]
            for headers, payload in batch_try:
                try:
                    resp, body = self._request_json(
                        "POST",
                        "https://yunyi.cfd/user/api/v1/batch-info",
                        headers=headers,
                        json_payload=payload,
                        timeout=20,
                    )
                    if resp.status_code < 500 and isinstance(body, (dict, list)) and not self._looks_like_error(body):
                        batch_data = body
                        break
                    if isinstance(body, dict) and isinstance(body.get("data"), (dict, list)):
                        batch_data = body
                        break
                    batch_errors.append(f"HTTP {resp.status_code}")
                except Exception as e:
                    batch_errors.append(str(e))

            if me_data is None and batch_data is None:
                raise RuntimeError("云驿接口认证失败，请检查 API Key")

            me_obj = self._unwrap_data(me_data)
            batch_obj = self._unwrap_data(batch_data)
            yunyi_item = self._extract_yunyi_item(batch_data, api_key)
            search_objs = [yunyi_item, me_data, me_obj, batch_data, batch_obj]

            key_name = self._format_kv(
                self._pick_kv(
                    [yunyi_item, me_obj, batch_obj],
                    ["name", "key_name", "title", "group_name", "api_key_name", "display_name"],
                    scalar_only=True,
                )
            )
            if key_name in ("-", ""):
                raw_key = self._pick_value([yunyi_item, batch_obj, me_obj], ["key", "api_key", "token", "access_key"]) or api_key
                key_name = self._mask_secret(raw_key)

            usage_kv = self._pick_kv(
                search_objs,
                [
                    "current_period_count",
                    "today_usage",
                    "daily_spent",
                    "used_today",
                    "today_tokens",
                    "used_quota",
                    "total_cost_usd",
                    "spent_today",
                    "quota_pack_used",
                ],
                scalar_only=True,
            )
            limit_kv = self._pick_kv(
                search_objs,
                ["daily_limit", "daily_quota", "quota", "total_quota", "quota_pack"],
                scalar_only=True,
            )
            usage = self._format_usage(usage_kv, limit_kv)

            remain = self._format_kv(
                self._pick_kv(
                    search_objs,
                    [
                        "remaining_requests",
                        "remaining_quota_usd",
                        "remaining_quota",
                        "remaining",
                        "available_balance",
                        "balance",
                        "credit",
                        "quota",
                        "quota_pack_remaining",
                    ],
                    scalar_only=True,
                )
            )
            if remain in ("-", ""):
                remain = self._calc_remaining(
                    self._pick_kv(search_objs, ["quota_pack", "total_quota", "daily_quota"], scalar_only=True),
                    self._pick_kv(search_objs, ["quota_pack_used", "used_quota", "daily_spent"], scalar_only=True),
                )

            expire = self._fmt_expire(
                self._pick_value(
                    search_objs,
                    [
                        "expires_at",
                        "expire_at",
                        "expired_at",
                        "subscription_expires_at",
                        "quota_pack_expires_at",
                        "valid_until",
                        "valid_to",
                    ],
                )
            )

            summary = {
                "剩余额度": remain,
                "今日用量": usage,
                "到期时间": expire,
                "Key名称": key_name,
            }

            detail_lines = [
                "【云驿查询结果】",
                f"Key名称: {key_name}",
                f"剩余额度: {remain}",
                f"今日用量: {usage}",
                f"到期时间: {expire}",
                "",
                "请求尝试:",
                *attempts,
            ]
            if batch_errors:
                detail_lines += ["batch-info 异常:", *batch_errors]

            detail_lines += [
                "",
                "[me]",
                json.dumps(me_data, ensure_ascii=False, indent=2),
                "",
                "[batch-info]",
                json.dumps(batch_data, ensure_ascii=False, indent=2),
            ]

            if me_data is not None and batch_data is not None:
                status = "成功"
            elif batch_data is not None:
                status = "成功"
            else:
                status = "部分成功"

            self._update_card("yunyi", status, summary, "\n".join(detail_lines))

        except Exception as e:
            self._update_card(
                "yunyi",
                "失败",
                {"剩余额度": "-", "今日用量": "-", "到期时间": "-", "Key名称": "-"},
                f"❌ 云驿查询失败: {e}",
            )

    def _refresh_codex(self):
        email = self.config_data.get("codex", {}).get("email", "").strip()
        password = self.config_data.get("codex", {}).get("password", "").strip()
        if not email or not password:
            self._update_card(
                "codex",
                "未配置",
                {"账户": "-", "主订阅": "-", "今日用量": "-", "到期时间": "-", "剩余额度": "-"},
                "请在“账号/API 配置”中填写 Codex 邮箱和密码。",
            )
            return

        self._set_card_status("codex", "查询中")

        try:
            # 1) 登录
            _, login_data = self._request_json(
                "POST",
                "https://vpsairobot.com/api/v1/auth/login",
                json_payload={"email": email, "password": password},
                timeout=20,
            )

            if not isinstance(login_data, dict):
                raise RuntimeError("登录响应异常（非 JSON 对象）")

            login_obj = self._unwrap_data(login_data)
            token = self._pick_value([login_obj, login_data], ["access_token", "token", "jwt", "id_token"])
            if not token:
                msg = login_data.get("message") or login_data.get("error") or "登录失败，未获取到 token"
                raise RuntimeError(msg)

            headers = {"Authorization": f"Bearer {token}"}

            # 2) 拉取多个接口（尽量完整）
            endpoint_map = {
                "me": "https://vpsairobot.com/api/v1/auth/me",
                "subscriptions": "https://vpsairobot.com/api/v1/subscriptions",
                "active": "https://vpsairobot.com/api/v1/subscriptions/active",
                "progress": "https://vpsairobot.com/api/v1/subscriptions/progress",
                "summary": "https://vpsairobot.com/api/v1/subscriptions/summary",
            }

            results: dict[str, dict[str, Any]] = {}
            for name, url in endpoint_map.items():
                try:
                    resp, data = self._request_json("GET", url, headers=headers, timeout=20)
                    results[name] = {"ok": resp.status_code < 400, "status": resp.status_code, "data": data}
                except Exception as e:
                    results[name] = {"ok": False, "status": -1, "data": {"error": str(e)}}

            me = self._unwrap_data(results.get("me", {}).get("data"))
            active = self._unwrap_data(results.get("active", {}).get("data"))
            subs = self._unwrap_data(results.get("subscriptions", {}).get("data"))
            progress = self._unwrap_data(results.get("progress", {}).get("data"))
            summary_raw = self._unwrap_data(results.get("summary", {}).get("data"))

            sub_list = self._collect_subscriptions([active, subs, progress, summary_raw])
            primary = self._select_primary_subscription(sub_list)

            search_objs = [primary, progress, summary_raw, me, active, subs, results]

            account = self._format_kv(self._pick_kv([me], ["name", "email", "username", "account"], scalar_only=True))

            plan = self._format_kv(
                self._pick_kv(
                    [primary, summary_raw, progress, active],
                    ["group_name", "subscription_name", "plan_name", "name", "title", "plan", "package_name"],
                    scalar_only=True,
                )
            )

            usage = self._format_usage(
                self._pick_kv(
                    search_objs,
                    [
                        "current_period_count",
                        "daily_spent",
                        "used_quota",
                        "today_usage",
                        "today_used",
                        "used_today",
                        "spent_today",
                        "used_usd",
                    ],
                    scalar_only=True,
                ),
                self._pick_kv(
                    search_objs,
                    ["daily_limit", "daily_quota", "total_quota", "quota", "limit_usd", "daily_limit_usd"],
                    scalar_only=True,
                ),
            )

            expire = self._fmt_expire(
                self._pick_value(
                    search_objs,
                    [
                        "expires_at",
                        "expire_at",
                        "expired_at",
                        "end_at",
                        "quota_pack_expires_at",
                        "valid_until",
                        "renew_at",
                    ],
                )
            )

            remaining = self._format_kv(
                self._pick_kv(
                    search_objs,
                    [
                        "remaining_requests",
                        "remaining_quota_usd",
                        "remaining_quota",
                        "remaining",
                        "balance",
                        "available_balance",
                        "credit",
                        "balance_usd",
                        "available_credit",
                    ],
                    scalar_only=True,
                )
            )

            summary = {
                "账户": account,
                "主订阅": plan,
                "今日用量": usage,
                "到期时间": expire,
                "剩余额度": remaining,
            }

            ok_count = sum(1 for item in results.values() if item.get("ok"))
            status = "成功" if ok_count >= 4 else "部分成功"

            lines = [
                "【Codex 查询结果】",
                f"账户: {account}",
                f"主订阅: {plan}",
                f"今日用量: {usage}",
                f"到期时间: {expire}",
                f"剩余额度: {remaining}",
                "",
                "接口状态:",
            ]

            for name in ["me", "subscriptions", "active", "progress", "summary"]:
                item = results.get(name, {})
                lines.append(f"- {name}: HTTP {item.get('status', '-')}, ok={item.get('ok', False)}")

            lines += [
                "",
                "[auth/me]",
                json.dumps(results.get("me", {}).get("data"), ensure_ascii=False, indent=2),
                "",
                "[subscriptions/active]",
                json.dumps(results.get("active", {}).get("data"), ensure_ascii=False, indent=2),
                "",
                "[subscriptions/progress]",
                json.dumps(results.get("progress", {}).get("data"), ensure_ascii=False, indent=2),
                "",
                "[subscriptions/summary]",
                json.dumps(results.get("summary", {}).get("data"), ensure_ascii=False, indent=2),
            ]

            self._update_card("codex", status, summary, "\n".join(lines))
        except Exception as e:
            self._update_card(
                "codex",
                "失败",
                {"账户": "-", "主订阅": "-", "今日用量": "-", "到期时间": "-", "剩余额度": "-"},
                f"❌ Codex 查询失败: {e}",
            )

    # ==================== UI updates ====================

    def _set_status(self, text: str):
        self.root.after(0, lambda: self.status_var.set(text))

    def _set_card_status(self, provider: str, status: str):
        theme = STATUS_THEME.get(status, STATUS_THEME["未查询"])

        def _run():
            card = self.cards[provider]
            card["status_label"].config(text=status, fg=theme["fg"], bg=theme["bg"])
            card["update_var"].set(f"更新时间：{self._now_str()}")

        self.root.after(0, _run)

    def _set_detail(self, provider: str, text: str):
        # 用户要求隐藏详情栏，保留接口但不渲染。
        return

    def _update_card(self, provider: str, status: str, values: dict[str, str], detail: str):
        theme = STATUS_THEME.get(status, STATUS_THEME["未查询"])

        def _run():
            card = self.cards[provider]
            card["status_label"].config(text=status, fg=theme["fg"], bg=theme["bg"])
            for k, v in values.items():
                if k in card["values"]:
                    card["values"][k].set(str(v))
            card["update_var"].set(f"更新时间：{self._now_str()}")

        self.root.after(0, _run)
        self._set_detail(provider, detail)

        self._refresh_done += 1
        if self._refresh_done >= self._refresh_total:
            self._set_status("刷新完成")
        else:
            self._set_status(f"刷新中...（{self._refresh_done}/{self._refresh_total}）")

    # ==================== HTTP / parse helpers ====================

    @staticmethod
    def _request_json(
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
        timeout: int = 20,
    ) -> tuple[requests.Response, Any]:
        resp = requests.request(method, url, headers=headers, params=params, json=json_payload, timeout=timeout)
        try:
            return resp, resp.json()
        except Exception:
            return resp, {"raw": resp.text[:1000], "status_code": resp.status_code}

    @staticmethod
    def _unwrap_data(data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
            return data.get("data")
        return data

    @staticmethod
    def _looks_like_error(data: Any) -> bool:
        if not isinstance(data, dict):
            return False
        if data.get("error"):
            return True
        if data.get("success") is False:
            return True
        code = data.get("code")
        if isinstance(code, int) and code >= 400:
            return True
        msg = str(data.get("message") or data.get("detail") or "").lower()
        err_words = ["invalid", "unauthorized", "forbidden", "token", "apikey", "api key", "error"]
        return bool(msg and any(w in msg for w in err_words) and not data.get("data"))

    def _pick_value(self, objs: list[Any], keys: list[str]) -> Any:
        kv = self._pick_kv(objs, keys)
        return kv[1] if kv else None

    def _pick_kv(self, objs: list[Any], keys: list[str], *, scalar_only: bool = False) -> tuple[str, Any] | None:
        keyset = set(keys)
        for obj in objs:
            result = self._deep_find_kv(obj, keyset, scalar_only=scalar_only)
            if result is not None:
                return result
        return None

    def _deep_find_kv(self, obj: Any, keyset: set[str], *, scalar_only: bool = False) -> tuple[str, Any] | None:
        stack = [obj]
        visited: set[int] = set()

        while stack:
            cur = stack.pop()
            obj_id = id(cur)
            if obj_id in visited:
                continue
            visited.add(obj_id)

            if isinstance(cur, dict):
                for k, v in cur.items():
                    if k in keyset and v not in (None, "", []):
                        if scalar_only and isinstance(v, (dict, list)):
                            pass
                        else:
                            return k, v
                for v in cur.values():
                    if isinstance(v, (dict, list)):
                        stack.append(v)
            elif isinstance(cur, list):
                for v in cur:
                    if isinstance(v, (dict, list)):
                        stack.append(v)

        return None

    def _extract_yunyi_item(self, batch_data: Any, api_key: str) -> dict[str, Any]:
        root = self._unwrap_data(batch_data)

        items: list[dict[str, Any]] = []
        if isinstance(root, list):
            items.extend([x for x in root if isinstance(x, dict)])
        elif isinstance(root, dict):
            for k in ["results", "items", "list", "records", "data"]:
                arr = root.get(k)
                if isinstance(arr, list):
                    items.extend([x for x in arr if isinstance(x, dict)])
            if any(k in root for k in ["billing_type", "daily_quota", "quota_pack", "quota_pack_used"]):
                items.insert(0, root)

        if not items:
            return {}

        for it in items:
            key_v = str(it.get("key") or it.get("api_key") or "").strip()
            if key_v and key_v == api_key:
                return it

        return items[0]

    @staticmethod
    def _normalize_subscriptions(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]

        if isinstance(data, dict):
            for k in ["items", "subscriptions", "rows", "list", "data", "records"]:
                if isinstance(data.get(k), list):
                    return [x for x in data[k] if isinstance(x, dict)]
            for k in ["subscription", "active_subscription", "current_subscription", "plan", "current_plan"]:
                if isinstance(data.get(k), dict):
                    return [data[k]]
            if any(k in data for k in ["name", "group_name", "expires_at", "id", "subscription_name", "plan_name"]):
                return [data]

        return []

    def _collect_subscriptions(self, objs: list[Any]) -> list[dict[str, Any]]:
        all_subs: list[dict[str, Any]] = []
        for obj in objs:
            all_subs.extend(self._normalize_subscriptions(obj))

        seen: set[str] = set()
        uniq: list[dict[str, Any]] = []
        for item in all_subs:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(item)
        return uniq

    def _select_primary_subscription(self, subs: list[dict[str, Any]]) -> dict[str, Any]:
        if not subs:
            return {}

        def score(item: dict[str, Any]) -> tuple[int, float]:
            st = str(item.get("status", "")).lower()
            is_active = 0 if st in ("active", "enabled", "normal", "") else 1
            exp = self._parse_dt(
                item.get("expires_at")
                or item.get("expire_at")
                or item.get("end_at")
                or item.get("quota_pack_expires_at")
            )
            if exp is None:
                ts = float("inf")
            else:
                ts = exp.timestamp()
            return is_active, ts

        return sorted(subs, key=score)[0]

    def _format_usage(self, usage_kv: tuple[str, Any] | None, limit_kv: tuple[str, Any] | None) -> str:
        if usage_kv is None:
            return "-"

        usage_text = self._format_kv(usage_kv)
        if limit_kv is None:
            return usage_text

        u = self._to_float(usage_kv[1])
        l = self._to_float(limit_kv[1])
        if u is not None and l is not None:
            return f"{self._fmt_maybe_int(u)} / {self._fmt_maybe_int(l)}"

        return f"{usage_text} / {self._format_kv(limit_kv)}"

    def _calc_remaining(self, total_kv: tuple[str, Any] | None, used_kv: tuple[str, Any] | None) -> str:
        if total_kv is None or used_kv is None:
            return "-"

        total = self._to_float(total_kv[1])
        used = self._to_float(used_kv[1])
        if total is None or used is None:
            return "-"

        remain = max(0.0, total - used)
        return self._fmt_maybe_int(remain)

    @staticmethod
    def _mask_secret(v: Any) -> str:
        if v in (None, ""):
            return "-"
        s = str(v).strip()
        if len(s) <= 8:
            return s
        return f"{s[:4]}...{s[-4:]}"

    def _format_kv(self, kv: tuple[str, Any] | None) -> str:
        if kv is None:
            return "-"

        key, value = kv
        if value in (None, "", []):
            return "-"

        key_l = key.lower()

        if any(x in key_l for x in ["expire", "expires", "date", "time", "at"]):
            return self._fmt_expire(value)

        if any(x in key_l for x in ["balance", "credit", "usd", "cost"]):
            return self._fmt_maybe_money(value)

        if any(x in key_l for x in ["count", "limit", "quota", "requests", "usage", "tokens", "remaining"]):
            n = self._to_float(value)
            if n is not None:
                if any(x in key_l for x in ["usd", "balance", "credit", "cost"]):
                    return self._fmt_maybe_money(n)
                return self._fmt_maybe_int(n)

        if isinstance(value, (dict, list)):
            return self._short_text(json.dumps(value, ensure_ascii=False), 72)

        return self._short_text(str(value), 72)

    @staticmethod
    def _to_float(v: Any) -> float | None:
        if v is None:
            return None
        try:
            if isinstance(v, str):
                v = v.replace(",", "").strip()
                if v == "":
                    return None
            return float(v)
        except Exception:
            return None

    @staticmethod
    def _short_text(text: str, max_len: int = 72) -> str:
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    @staticmethod
    def _fmt_maybe_int(v: Any) -> str:
        n = APIBalanceDashboard._to_float(v)
        if n is None:
            return "-" if v in (None, "") else str(v)
        return f"{int(n):,}"

    @staticmethod
    def _fmt_money(v: Any) -> str:
        n = APIBalanceDashboard._to_float(v)
        if n is None:
            return "-"
        return f"${n:.4f}"

    def _fmt_maybe_money(self, v: Any) -> str:
        n = self._to_float(v)
        if n is None:
            return "-" if v in (None, "") else str(v)
        return f"${n:.4f}"

    def _parse_dt(self, ts: Any) -> datetime | None:
        if ts in (None, ""):
            return None
        try:
            if isinstance(ts, str):
                s = ts.strip()
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                return datetime.fromisoformat(s)
            if isinstance(ts, (int, float)):
                t = float(ts)
                if t > 1e12:
                    t = t / 1000.0
                return datetime.fromtimestamp(t)
            return None
        except Exception:
            return None

    def _fmt_expire(self, ts: Any) -> str:
        if ts in (None, ""):
            return "-"
        dt = self._parse_dt(ts)
        if dt is None:
            return str(ts)

        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        delta = dt - now

        if delta.total_seconds() < 0:
            past = -delta
            if past >= timedelta(days=1):
                suffix = f"(已过期{past.days}天)"
            else:
                hours = max(1, int(past.total_seconds() // 3600))
                suffix = f"(已过期{hours}小时)"
        else:
            if delta >= timedelta(days=1):
                suffix = f"(剩{delta.days}天)"
            else:
                hours = max(1, int(delta.total_seconds() // 3600))
                suffix = f"(剩{hours}小时)"

        return f"{dt.strftime('%Y-%m-%d %H:%M:%S')} {suffix}"

    def _cf_status(self, d: dict[str, Any]) -> str:
        if d.get("status") == "disabled":
            return "已禁用"
        if d.get("status") == "exhausted" or d.get("is_exhausted"):
            return "已耗尽"
        if d.get("is_expired"):
            return "已过期"
        if d.get("is_activated") or d.get("status") == "active":
            return "活跃"
        return "待激活"

    def _fmt_time(self, ts: Any) -> str:
        dt = self._parse_dt(ts)
        if dt is None:
            return "-" if ts in (None, "") else str(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _now_str() -> str:
        return datetime.now().strftime("%H:%M:%S")


if __name__ == "__main__":
    root = tk.Tk()
    app = APIBalanceDashboard(root)
    root.mainloop()
