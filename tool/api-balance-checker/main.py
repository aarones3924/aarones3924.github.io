#!/usr/bin/env python3
"""API Balance Checker - 查询长风/云驿/Codex的Token用量和余额"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import json
import requests
from datetime import datetime


class APIBalanceChecker:
    def __init__(self, root):
        self.root = root
        self.root.title("API 余额查询工具")
        self.root.geometry("700x600")
        self.root.resizable(True, True)

        style = ttk.Style()
        style.configure("Header.TLabel", font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("Result.TLabel", font=("Microsoft YaHei UI", 10))
        style.configure("Big.TLabel", font=("Microsoft YaHei UI", 14, "bold"))

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self._build_changfeng_tab()
        self._build_yunyi_tab()
        self._build_codex_tab()

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(
            fill=tk.X, padx=10, pady=(0, 10)
        )

    def _build_changfeng_tab(self):
        tab = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(tab, text="长风 (Sub2API)")

        ttk.Label(tab, text="长风 API 余额查询", style="Header.TLabel").pack(anchor=tk.W)
        ttk.Separator(tab, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        frm = ttk.Frame(tab)
        frm.pack(fill=tk.X)
        ttk.Label(frm, text="API Key:").pack(side=tk.LEFT)
        self.cf_key = ttk.Entry(frm, width=50, show="*")
        self.cf_key.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(frm, text="查询", command=self._query_changfeng).pack(side=tk.LEFT, padx=5)

        self.cf_result = scrolledtext.ScrolledText(tab, height=18, state=tk.DISABLED, font=("Consolas", 10))
        self.cf_result.pack(fill=tk.BOTH, expand=True, pady=10)

    def _build_yunyi_tab(self):
        tab = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(tab, text="云驿")

        ttk.Label(tab, text="云驿 API 余额查询", style="Header.TLabel").pack(anchor=tk.W)
        ttk.Separator(tab, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        frm = ttk.Frame(tab)
        frm.pack(fill=tk.X)
        ttk.Label(frm, text="API Key:").pack(side=tk.LEFT)
        self.yy_key = ttk.Entry(frm, width=50, show="*")
        self.yy_key.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(frm, text="查询", command=self._query_yunyi).pack(side=tk.LEFT, padx=5)

        self.yy_result = scrolledtext.ScrolledText(tab, height=18, state=tk.DISABLED, font=("Consolas", 10))
        self.yy_result.pack(fill=tk.BOTH, expand=True, pady=10)

    def _build_codex_tab(self):
        tab = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(tab, text="Codex")

        ttk.Label(tab, text="Codex (vpsairobot) 余额查询", style="Header.TLabel").pack(anchor=tk.W)
        ttk.Separator(tab, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        frm = ttk.Frame(tab)
        frm.pack(fill=tk.X)
        ttk.Label(frm, text="邮箱:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.cx_email = ttk.Entry(frm, width=40)
        self.cx_email.grid(row=0, column=1, padx=5, sticky=tk.EW, pady=2)

        ttk.Label(frm, text="密码:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.cx_pass = ttk.Entry(frm, width=40, show="*")
        self.cx_pass.grid(row=1, column=1, padx=5, sticky=tk.EW, pady=2)

        ttk.Button(frm, text="查询", command=self._query_codex).grid(row=0, column=2, rowspan=2, padx=5, sticky=tk.NS)
        frm.columnconfigure(1, weight=1)

        self.cx_result = scrolledtext.ScrolledText(tab, height=16, state=tk.DISABLED, font=("Consolas", 10))
        self.cx_result.pack(fill=tk.BOTH, expand=True, pady=10)

    def _set_result(self, widget, text):
        widget.config(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.config(state=tk.DISABLED)

    def _set_status(self, text):
        self.status_var.set(text)

    def _query_changfeng(self):
        key = self.cf_key.get().strip()
        if not key:
            messagebox.showwarning("提示", "请输入 API Key")
            return
        self._set_result(self.cf_result, "查询中...")
        self._set_status("正在查询长风...")
        threading.Thread(target=self._do_changfeng, args=(key,), daemon=True).start()

    def _do_changfeng(self, key):
        try:
            resp = requests.get(
                "https://cfjwlpro.com/api/v1/temp-api-keys/query",
                params={"key": key, "page": 1, "page_size": 10},
                timeout=15,
            )
            data = resp.json()
            if data.get("code") != 0:
                text = f"❌ 查询失败: {data.get('message', '未知错误')}"
            else:
                d = data["data"]
                lines = [
                    "═══════════════════════════════════",
                    f"  名称: {d.get('name', '-')}",
                    f"  分组: {d.get('group_name', '-')}",
                    f"  状态: {self._cf_status(d)}",
                    "───────────────────────────────────",
                ]
                if d.get("key_type") == "quota_only":
                    lines += [
                        f"  总额度: ${d.get('total_quota_usd', 0):.2f}",
                        f"  已用:   ${d.get('total_cost_usd', 0):.4f}",
                        f"  剩余:   ${d.get('remaining_quota_usd', 0):.4f}",
                    ]
                else:
                    lines += [
                        f"  有效天数: {d.get('valid_days', '-')}",
                        f"  今日用量: {d.get('current_period_count', 0)} / {d.get('daily_limit', 0)}",
                        f"  剩余次数: {d.get('remaining_requests', 0)}",
                    ]
                lines += [
                    f"  总请求数: {d.get('total_requests', 0):,}",
                    f"  激活时间: {self._fmt_time(d.get('activated_at'))}",
                    f"  过期时间: {self._fmt_time(d.get('expires_at'))}",
                    "═══════════════════════════════════",
                ]
                # 使用日志
                logs = d.get("usage_logs", [])
                if logs:
                    lines.append(f"\n最近使用记录 ({len(logs)} 条):")
                    lines.append(f"{'时间':<20} {'模型':<25} {'Tokens':>10} {'费用':>10}")
                    lines.append("─" * 70)
                    for log in logs:
                        t = self._fmt_time_short(log.get("created_at"))
                        model = log.get("model", "-")
                        tokens = f"{log.get('total_tokens', 0):,}"
                        cost = f"${log.get('actual_cost', 0):.4f}"
                        lines.append(f"{t:<20} {model:<25} {tokens:>10} {cost:>10}")
                text = "\n".join(lines)
        except Exception as e:
            text = f"❌ 请求失败: {e}"
        self.root.after(0, self._set_result, self.cf_result, text)
        self.root.after(0, self._set_status, "查询完成")

    def _cf_status(self, d):
        if d.get("status") == "disabled":
            return "🔴 已禁用"
        if d.get("status") == "exhausted" or d.get("is_exhausted"):
            return "🔴 已耗尽"
        if d.get("is_expired"):
            return "🟡 已过期"
        if d.get("is_activated"):
            return "🟢 活跃"
        return "🔵 待激活"

    def _query_yunyi(self):
        key = self.yy_key.get().strip()
        if not key:
            messagebox.showwarning("提示", "请输入 API Key")
            return
        self._set_result(self.yy_result, "查询中...")
        self._set_status("正在查询云驿...")
        threading.Thread(target=self._do_yunyi, args=(key,), daemon=True).start()

    def _do_yunyi(self, key):
        headers = {"Authorization": f"Bearer {key}"}
        try:
            # 查询用户信息
            resp_me = requests.get(
                "https://yunyi.cfd/user/api/v1/me", headers=headers, timeout=15
            )
            me_data = resp_me.json()

            # 查询批量信息
            resp_batch = requests.get(
                "https://yunyi.cfd/user/api/v1/batch-info", headers=headers, timeout=15
            )
            batch_data = resp_batch.json()

            if "error" in me_data:
                text = f"❌ 查询失败: {me_data.get('message', me_data.get('error', '未知错误'))}"
            else:
                lines = [
                    "═══════════════════════════════════",
                    "  云驿 API 使用信息",
                    "───────────────────────────────────",
                ]
                # me 接口数据
                if isinstance(me_data, dict):
                    for k, v in me_data.items():
                        if k not in ("error", "message"):
                            lines.append(f"  {k}: {v}")
                lines.append("───────────────────────────────────")
                # batch-info 数据
                if isinstance(batch_data, dict) and "error" not in batch_data:
                    lines.append("  批量信息:")
                    for k, v in batch_data.items():
                        if k not in ("error", "message"):
                            lines.append(f"    {k}: {v}")
                lines.append("═══════════════════════════════════")
                text = "\n".join(lines)
        except Exception as e:
            text = f"❌ 请求失败: {e}"
        self.root.after(0, self._set_result, self.yy_result, text)
        self.root.after(0, self._set_status, "查询完成")

    def _query_codex(self):
        email = self.cx_email.get().strip()
        pwd = self.cx_pass.get().strip()
        if not email or not pwd:
            messagebox.showwarning("提示", "请输入邮箱和密码")
            return
        self._set_result(self.cx_result, "登录中...")
        self._set_status("正在登录 Codex...")
        threading.Thread(target=self._do_codex, args=(email, pwd), daemon=True).start()

    def _do_codex(self, email, pwd):
        try:
            # 登录
            login_resp = requests.post(
                "https://vpsairobot.com/api/v1/auth/login",
                json={"email": email, "password": pwd},
                timeout=15,
            )
            login_data = login_resp.json()
            if login_data.get("code") and login_data["code"] != 0:
                text = f"❌ 登录失败: {login_data.get('message', '未知错误')}"
                self.root.after(0, self._set_result, self.cx_result, text)
                self.root.after(0, self._set_status, "登录失败")
                return

            token = login_data.get("token") or login_data.get("data", {}).get("token", "")
            if not token:
                text = f"❌ 登录失败: 未获取到token\n响应: {json.dumps(login_data, indent=2, ensure_ascii=False)}"
                self.root.after(0, self._set_result, self.cx_result, text)
                self.root.after(0, self._set_status, "登录失败")
                return

            headers = {"Authorization": f"Bearer {token}"}

            # 获取用户信息
            me_resp = requests.get(
                "https://vpsairobot.com/api/v1/auth/me", headers=headers, timeout=15
            )
            me_data = me_resp.json()

            # 获取活跃订阅
            sub_resp = requests.get(
                "https://vpsairobot.com/api/v1/subscriptions/active", headers=headers, timeout=15
            )
            sub_data = sub_resp.json()

            # 获取订阅摘要
            summary_resp = requests.get(
                "https://vpsairobot.com/api/v1/subscriptions/summary", headers=headers, timeout=15
            )
            summary_data = summary_resp.json()

            lines = [
                "═══════════════════════════════════",
                "  Codex (vpsairobot) 账户信息",
                "───────────────────────────────────",
            ]

            # 用户信息
            if isinstance(me_data, dict):
                user = me_data.get("data", me_data)
                lines.append(f"  用户: {user.get('name', user.get('email', '-'))}")
                if user.get("balance") is not None:
                    lines.append(f"  余额: ${user['balance']:.4f}")

            lines.append("───────────────────────────────────")

            # 活跃订阅
            if isinstance(sub_data, dict):
                subs = sub_data.get("data", sub_data)
                if isinstance(subs, list):
                    lines.append(f"  活跃订阅 ({len(subs)} 个):")
                    for s in subs:
                        lines.append(f"    - {s.get('group_name', s.get('name', '-'))}")
                        if s.get("daily_limit"):
                            lines.append(f"      日限额: {s['daily_limit']}")
                        if s.get("current_period_count") is not None:
                            lines.append(f"      今日用量: {s['current_period_count']}")
                        if s.get("expires_at"):
                            lines.append(f"      过期: {self._fmt_time(s['expires_at'])}")
                elif isinstance(subs, dict):
                    for k, v in subs.items():
                        lines.append(f"    {k}: {v}")

            lines.append("───────────────────────────────────")

            # 订阅摘要
            if isinstance(summary_data, dict):
                summary = summary_data.get("data", summary_data)
                lines.append("  订阅摘要:")
                if isinstance(summary, dict):
                    for k, v in summary.items():
                        lines.append(f"    {k}: {v}")
                elif isinstance(summary, list):
                    for item in summary:
                        if isinstance(item, dict):
                            lines.append(f"    - {json.dumps(item, ensure_ascii=False)}")

            lines.append("═══════════════════════════════════")
            text = "\n".join(lines)
        except Exception as e:
            text = f"❌ 请求失败: {e}"
        self.root.after(0, self._set_result, self.cx_result, text)
        self.root.after(0, self._set_status, "查询完成")

    @staticmethod
    def _fmt_time(ts):
        if not ts:
            return "-"
        try:
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            elif isinstance(ts, (int, float)):
                dt = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts)
            else:
                return str(ts)
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return str(ts)

    @staticmethod
    def _fmt_time_short(ts):
        if not ts:
            return "-"
        try:
            if isinstance(ts, str):
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            elif isinstance(ts, (int, float)):
                dt = datetime.fromtimestamp(ts / 1000 if ts > 1e12 else ts)
            else:
                return str(ts)
            return dt.strftime("%m-%d %H:%M:%S")
        except Exception:
            return str(ts)


if __name__ == "__main__":
    root = tk.Tk()
    app = APIBalanceChecker(root)
    root.mainloop()
