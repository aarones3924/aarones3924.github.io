#!/usr/bin/env python3
"""API 余额监控中心（长风 / 云驿 / Codex）"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext


APP_TITLE = "API 余额监控中心"
CONFIG_PATH = Path(__file__).with_name("config.json")

DEFAULT_CONFIG = {
    "changfeng": {"api_key": ""},
    "yunyi": {"api_key": ""},
    "codex": {"email": "", "password": ""},
    "auto_refresh_on_start": True,
}


class APIBalanceDashboard:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1060x760")
        self.root.minsize(980, 700)

        self.config_data = self._load_config()

        self._init_style()
        self._build_ui()

        if self.config_data.get("auto_refresh_on_start", True):
            self.refresh_all()

    # ==================== UI ====================

    def _init_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Main.TFrame", background="#f6f8fb")
        style.configure("Header.TFrame", background="#1f2937")
        style.configure("Card.TLabelframe", background="#ffffff", borderwidth=1)
        style.configure("Card.TLabelframe.Label", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Name.TLabel", font=("Microsoft YaHei UI", 10), background="#ffffff")
        style.configure("Value.TLabel", font=("Consolas", 10, "bold"), background="#ffffff")

    def _build_ui(self):
        container = ttk.Frame(self.root, style="Main.TFrame")
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(container, style="Header.TFrame", padding=14)
        header.pack(fill=tk.X)

        title = tk.Label(
            header,
            text=APP_TITLE,
            font=("Microsoft YaHei UI", 16, "bold"),
            fg="#ffffff",
            bg="#1f2937",
        )
        title.pack(side=tk.LEFT)

        self.last_update_var = tk.StringVar(value="上次刷新：-")
        last_update = tk.Label(
            header,
            textvariable=self.last_update_var,
            font=("Microsoft YaHei UI", 9),
            fg="#d1d5db",
            bg="#1f2937",
        )
        last_update.pack(side=tk.LEFT, padx=(16, 0))

        btn_wrap = ttk.Frame(header, style="Header.TFrame")
        btn_wrap.pack(side=tk.RIGHT)

        ttk.Button(btn_wrap, text="账号/API 配置", command=self.open_settings).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_wrap, text="刷新全部", command=self.refresh_all).pack(side=tk.LEFT)

        cards_wrap = ttk.Frame(container, style="Main.TFrame", padding=(12, 12, 12, 4))
        cards_wrap.pack(fill=tk.X)

        cards_wrap.columnconfigure(0, weight=1)
        cards_wrap.columnconfigure(1, weight=1)
        cards_wrap.columnconfigure(2, weight=1)

        self.cards = {
            "changfeng": self._build_card(
                cards_wrap,
                0,
                "长风 (Sub2API)",
                ["状态", "剩余额度", "今日用量", "总请求"],
            ),
            "yunyi": self._build_card(
                cards_wrap,
                1,
                "云驿",
                ["状态", "余额", "今日用量", "总请求"],
            ),
            "codex": self._build_card(
                cards_wrap,
                2,
                "Codex (vpsairobot)",
                ["状态", "账户", "余额", "活跃订阅"],
            ),
        }

        notebook = ttk.Notebook(container)
        notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=(4, 12))

        self.detail_boxes: dict[str, scrolledtext.ScrolledText] = {}
        for key, title in [
            ("changfeng", "长风详情"),
            ("yunyi", "云驿详情"),
            ("codex", "Codex详情"),
        ]:
            tab = ttk.Frame(notebook, padding=10)
            notebook.add(tab, text=title)
            box = scrolledtext.ScrolledText(tab, font=("Consolas", 10))
            box.pack(fill=tk.BOTH, expand=True)
            box.insert("1.0", "等待查询...\n")
            box.config(state=tk.DISABLED)
            self.detail_boxes[key] = box

        bottom = ttk.Frame(container, padding=(12, 0, 12, 10), style="Main.TFrame")
        bottom.pack(fill=tk.X)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(bottom, textvariable=self.status_var).pack(anchor=tk.W)

    def _build_card(self, parent: ttk.Frame, column: int, title: str, fields: list[str]):
        card = ttk.LabelFrame(parent, text=title, style="Card.TLabelframe", padding=10)
        card.grid(row=0, column=column, sticky="nsew", padx=6)

        status_label = tk.Label(
            card,
            text="未查询",
            font=("Microsoft YaHei UI", 10, "bold"),
            fg="#9ca3af",
            bg="#ffffff",
        )
        status_label.pack(anchor=tk.W, pady=(0, 8))

        values: dict[str, tk.StringVar] = {}
        for f in fields:
            if f == "状态":
                continue
            row = ttk.Frame(card, style="Main.TFrame")
            row.pack(fill=tk.X, pady=2)
            name = tk.Label(row, text=f"{f}:", font=("Microsoft YaHei UI", 9), fg="#4b5563", bg="#ffffff")
            name.pack(side=tk.LEFT)

            value_var = tk.StringVar(value="-")
            value = tk.Label(row, textvariable=value_var, font=("Consolas", 10, "bold"), fg="#111827", bg="#ffffff")
            value.pack(side=tk.RIGHT)
            values[f] = value_var

        update_var = tk.StringVar(value="更新时间：-")
        update = tk.Label(card, textvariable=update_var, font=("Microsoft YaHei UI", 8), fg="#6b7280", bg="#ffffff")
        update.pack(anchor=tk.W, pady=(8, 0))

        return {
            "status_label": status_label,
            "values": values,
            "update_var": update_var,
        }

    # ==================== Config ====================

    def _load_config(self) -> dict[str, Any]:
        if not CONFIG_PATH.exists():
            CONFIG_PATH.write_text(
                json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return json.loads(json.dumps(DEFAULT_CONFIG))

        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = json.loads(json.dumps(DEFAULT_CONFIG))

        # 合并缺失字段
        merged = json.loads(json.dumps(DEFAULT_CONFIG))
        for k, v in data.items() if isinstance(data, dict) else []:
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k].update(v)
            else:
                merged[k] = v
        return merged

    def _save_config(self):
        CONFIG_PATH.write_text(json.dumps(self.config_data, ensure_ascii=False, indent=2), encoding="utf-8")

    def open_settings(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("账号/API 配置")
        dlg.geometry("560x340")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()

        frm = ttk.Frame(dlg, padding=14)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frm, text="长风 API Key:").grid(row=0, column=0, sticky=tk.W, pady=6)
        cf_key = ttk.Entry(frm, width=52)
        cf_key.grid(row=0, column=1, sticky=tk.EW, pady=6)
        cf_key.insert(0, self.config_data.get("changfeng", {}).get("api_key", ""))

        ttk.Label(frm, text="云驿 API Key:").grid(row=1, column=0, sticky=tk.W, pady=6)
        yy_key = ttk.Entry(frm, width=52)
        yy_key.grid(row=1, column=1, sticky=tk.EW, pady=6)
        yy_key.insert(0, self.config_data.get("yunyi", {}).get("api_key", ""))

        ttk.Label(frm, text="Codex 邮箱:").grid(row=2, column=0, sticky=tk.W, pady=6)
        cx_email = ttk.Entry(frm, width=52)
        cx_email.grid(row=2, column=1, sticky=tk.EW, pady=6)
        cx_email.insert(0, self.config_data.get("codex", {}).get("email", ""))

        ttk.Label(frm, text="Codex 密码:").grid(row=3, column=0, sticky=tk.W, pady=6)
        cx_pwd = ttk.Entry(frm, width=52, show="*")
        cx_pwd.grid(row=3, column=1, sticky=tk.EW, pady=6)
        cx_pwd.insert(0, self.config_data.get("codex", {}).get("password", ""))

        auto_refresh_var = tk.BooleanVar(value=bool(self.config_data.get("auto_refresh_on_start", True)))
        ttk.Checkbutton(frm, text="软件启动后自动刷新三平台", variable=auto_refresh_var).grid(
            row=4, column=1, sticky=tk.W, pady=(10, 4)
        )

        note = "提示：配置会保存在软件目录下 config.json（明文）。"
        ttk.Label(frm, text=note, foreground="#6b7280").grid(row=5, column=1, sticky=tk.W, pady=(4, 12))

        frm.columnconfigure(1, weight=1)

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=1, sticky=tk.E)

        def do_save():
            self.config_data["changfeng"]["api_key"] = cf_key.get().strip()
            self.config_data["yunyi"]["api_key"] = yy_key.get().strip()
            self.config_data["codex"]["email"] = cx_email.get().strip()
            self.config_data["codex"]["password"] = cx_pwd.get().strip()
            self.config_data["auto_refresh_on_start"] = bool(auto_refresh_var.get())
            self._save_config()
            messagebox.showinfo("成功", "配置已保存")
            dlg.destroy()

        ttk.Button(btns, text="取消", command=dlg.destroy).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="保存并立即刷新", command=lambda: [do_save(), self.refresh_all()]).pack(side=tk.LEFT)

    # ==================== Actions ====================

    def refresh_all(self):
        self._set_status("正在刷新三平台数据...")
        self.last_update_var.set(f"上次刷新：{self._now_str()}")

        threading.Thread(target=self._refresh_changfeng, daemon=True).start()
        threading.Thread(target=self._refresh_yunyi, daemon=True).start()
        threading.Thread(target=self._refresh_codex, daemon=True).start()

    def _refresh_changfeng(self):
        api_key = self.config_data.get("changfeng", {}).get("api_key", "").strip()
        if not api_key:
            self._update_card("changfeng", "未配置", {"剩余额度": "-", "今日用量": "-", "总请求": "-"}, "请在“账号/API 配置”中填写长风 API Key。")
            return

        self._set_card_status("changfeng", "查询中", "#2563eb")
        try:
            resp = requests.get(
                "https://cfjwlpro.com/api/v1/temp-api-keys/query",
                params={"key": api_key, "page": 1, "page_size": 10},
                timeout=20,
            )
            data = self._safe_json(resp)
            if data.get("code") != 0:
                raise RuntimeError(data.get("message") or "返回异常")

            d = data.get("data")
            if isinstance(d, list):
                d = d[0] if d else {}
            if not isinstance(d, dict):
                d = {}

            if d.get("key_type") == "quota_only":
                remain = self._fmt_money(d.get("remaining_quota_usd"))
                today = self._fmt_money(d.get("total_cost_usd"))
            else:
                remain = str(d.get("remaining_requests", "-"))
                today = f"{d.get('current_period_count', 0)} / {d.get('daily_limit', 0)}"

            summary = {
                "剩余额度": remain,
                "今日用量": today,
                "总请求": self._fmt_int(d.get("total_requests")),
            }

            lines = [
                "【长风查询结果】",
                f"状态: {self._cf_status(d)}",
                f"名称: {d.get('name', '-')}",
                f"分组: {d.get('group_name', '-')}",
                f"剩余额度/次数: {remain}",
                f"今日用量: {today}",
                f"总请求: {self._fmt_int(d.get('total_requests'))}",
                f"激活时间: {self._fmt_time(d.get('activated_at'))}",
                f"过期时间: {self._fmt_time(d.get('expires_at'))}",
                "",
                "原始响应:",
                json.dumps(data, ensure_ascii=False, indent=2),
            ]
            self._update_card("changfeng", "成功", summary, "\n".join(lines), "#16a34a")
        except Exception as e:
            self._update_card("changfeng", "失败", {"剩余额度": "-", "今日用量": "-", "总请求": "-"}, f"❌ 长风查询失败: {e}", "#dc2626")

    def _refresh_yunyi(self):
        api_key = self.config_data.get("yunyi", {}).get("api_key", "").strip()
        if not api_key:
            self._update_card("yunyi", "未配置", {"余额": "-", "今日用量": "-", "总请求": "-"}, "请在“账号/API 配置”中填写云驿 API Key。")
            return

        self._set_card_status("yunyi", "查询中", "#2563eb")
        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            me_resp = requests.get("https://yunyi.cfd/user/api/v1/me", headers=headers, timeout=20)
            batch_resp = requests.get("https://yunyi.cfd/user/api/v1/batch-info", headers=headers, timeout=20)

            me = self._safe_json(me_resp)
            batch = self._safe_json(batch_resp)

            if self._has_error(me):
                raise RuntimeError(me.get("message") or me.get("error") or "返回异常")

            balance = self._pick_any([me, batch], [
                "balance",
                "remaining_balance",
                "remaining_quota",
                "quota",
                "credit",
                "available_balance",
            ])
            today_usage = self._pick_any([me, batch], [
                "today_usage",
                "current_period_count",
                "daily_usage",
                "used_today",
                "today_tokens",
            ])
            total_req = self._pick_any([me, batch], [
                "total_requests",
                "request_count",
                "total_count",
                "total_usage",
            ])

            summary = {
                "余额": self._fmt_maybe_money(balance),
                "今日用量": self._fmt_maybe_int(today_usage),
                "总请求": self._fmt_maybe_int(total_req),
            }

            lines = [
                "【云驿查询结果】",
                f"余额: {summary['余额']}",
                f"今日用量: {summary['今日用量']}",
                f"总请求: {summary['总请求']}",
                "",
                "[me]",
                json.dumps(me, ensure_ascii=False, indent=2),
                "",
                "[batch-info]",
                json.dumps(batch, ensure_ascii=False, indent=2),
            ]
            self._update_card("yunyi", "成功", summary, "\n".join(lines), "#16a34a")
        except Exception as e:
            self._update_card("yunyi", "失败", {"余额": "-", "今日用量": "-", "总请求": "-"}, f"❌ 云驿查询失败: {e}", "#dc2626")

    def _refresh_codex(self):
        email = self.config_data.get("codex", {}).get("email", "").strip()
        password = self.config_data.get("codex", {}).get("password", "").strip()
        if not email or not password:
            self._update_card("codex", "未配置", {"账户": "-", "余额": "-", "活跃订阅": "-"}, "请在“账号/API 配置”中填写 Codex 邮箱和密码。")
            return

        self._set_card_status("codex", "查询中", "#2563eb")
        try:
            login_resp = requests.post(
                "https://vpsairobot.com/api/v1/auth/login",
                json={"email": email, "password": password},
                timeout=20,
            )
            login = self._safe_json(login_resp)

            token = (
                login.get("token")
                or (login.get("data") or {}).get("token")
                or (login.get("data") or {}).get("access_token")
            )
            if not token:
                raise RuntimeError(login.get("message") or "登录失败，未拿到 token")

            headers = {"Authorization": f"Bearer {token}"}
            me = self._safe_json(requests.get("https://vpsairobot.com/api/v1/auth/me", headers=headers, timeout=20))
            active = self._safe_json(requests.get("https://vpsairobot.com/api/v1/subscriptions/active", headers=headers, timeout=20))
            summary_raw = self._safe_json(requests.get("https://vpsairobot.com/api/v1/subscriptions/summary", headers=headers, timeout=20))

            me_data = me.get("data") if isinstance(me, dict) and isinstance(me.get("data"), dict) else me
            active_data = active.get("data") if isinstance(active, dict) and "data" in active else active
            summary_data = summary_raw.get("data") if isinstance(summary_raw, dict) and "data" in summary_raw else summary_raw

            account = "-"
            if isinstance(me_data, dict):
                account = me_data.get("name") or me_data.get("email") or "-"

            balance = self._pick_any([me_data, summary_data], ["balance", "remaining_balance", "quota", "credit"])

            active_count = 0
            if isinstance(active_data, list):
                active_count = len(active_data)
            elif isinstance(active_data, dict):
                active_count = int(active_data.get("count", 1))

            summary = {
                "账户": account,
                "余额": self._fmt_maybe_money(balance),
                "活跃订阅": str(active_count),
            }

            lines = [
                "【Codex 查询结果】",
                f"账户: {summary['账户']}",
                f"余额: {summary['余额']}",
                f"活跃订阅: {summary['活跃订阅']}",
                "",
                "[auth/me]",
                json.dumps(me, ensure_ascii=False, indent=2),
                "",
                "[subscriptions/active]",
                json.dumps(active, ensure_ascii=False, indent=2),
                "",
                "[subscriptions/summary]",
                json.dumps(summary_raw, ensure_ascii=False, indent=2),
            ]
            self._update_card("codex", "成功", summary, "\n".join(lines), "#16a34a")
        except Exception as e:
            self._update_card("codex", "失败", {"账户": "-", "余额": "-", "活跃订阅": "-"}, f"❌ Codex 查询失败: {e}", "#dc2626")

    # ==================== UI updates ====================

    def _set_status(self, text: str):
        self.root.after(0, lambda: self.status_var.set(text))

    def _set_card_status(self, provider: str, text: str, color: str):
        def _run():
            card = self.cards[provider]
            card["status_label"].config(text=text, fg=color)
            card["update_var"].set(f"更新时间：{self._now_str()}")

        self.root.after(0, _run)

    def _set_detail(self, provider: str, text: str):
        def _run():
            box = self.detail_boxes[provider]
            box.config(state=tk.NORMAL)
            box.delete("1.0", tk.END)
            box.insert("1.0", text)
            box.config(state=tk.DISABLED)

        self.root.after(0, _run)

    def _update_card(self, provider: str, status: str, values: dict[str, str], detail: str, color: str = "#d97706"):
        def _run():
            card = self.cards[provider]
            card["status_label"].config(text=status, fg=color)
            for k, v in values.items():
                if k in card["values"]:
                    card["values"][k].set(str(v))
            card["update_var"].set(f"更新时间：{self._now_str()}")

        self.root.after(0, _run)
        self._set_detail(provider, detail)
        self._set_status("刷新完成")

    # ==================== helpers ====================

    @staticmethod
    def _safe_json(resp: requests.Response) -> dict[str, Any]:
        try:
            return resp.json()
        except Exception:
            raise RuntimeError(f"HTTP {resp.status_code} 非 JSON 响应: {resp.text[:200]}")

    @staticmethod
    def _has_error(data: Any) -> bool:
        return isinstance(data, dict) and (
            data.get("error") is not None
            or (isinstance(data.get("code"), int) and data.get("code") not in (0, 200))
        )

    @staticmethod
    def _pick_any(objs: list[Any], keys: list[str]) -> Any:
        for obj in objs:
            if isinstance(obj, dict):
                for k in keys:
                    if k in obj and obj[k] not in (None, ""):
                        return obj[k]
        return None

    @staticmethod
    def _fmt_int(v: Any) -> str:
        try:
            return f"{int(float(v)):,}"
        except Exception:
            return "-"

    @staticmethod
    def _fmt_money(v: Any) -> str:
        try:
            return f"${float(v):.4f}"
        except Exception:
            return "-"

    def _fmt_maybe_money(self, v: Any) -> str:
        if v is None:
            return "-"
        try:
            return f"${float(v):.4f}"
        except Exception:
            return str(v)

    def _fmt_maybe_int(self, v: Any) -> str:
        if v is None:
            return "-"
        try:
            return f"{int(float(v)):,}"
        except Exception:
            return str(v)

    @staticmethod
    def _cf_status(d: dict[str, Any]) -> str:
        if d.get("status") == "disabled":
            return "已禁用"
        if d.get("status") == "exhausted" or d.get("is_exhausted"):
            return "已耗尽"
        if d.get("is_expired"):
            return "已过期"
        if d.get("is_activated"):
            return "活跃"
        return "待激活"

    @staticmethod
    def _fmt_time(ts: Any) -> str:
        if not ts:
            return "-"
        try:
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            elif isinstance(ts, (int, float)):
                dt = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts)
            else:
                return str(ts)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(ts)

    @staticmethod
    def _now_str() -> str:
        return datetime.now().strftime("%H:%M:%S")


if __name__ == "__main__":
    root = tk.Tk()
    app = APIBalanceDashboard(root)
    root.mainloop()
