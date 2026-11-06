"""Movable buttons for the client's actual team slots, clipped to visible monitors."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import queue
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog
import threading
import pystray
from PIL import ImageTk

from app import Worker, CONFIG, BG, CARD, FG, MUTED, BLUE
from lcu import format_message
from hextech import HexButton, emblem, make_icon, BG, SURFACE, GOLD, GOLD_DIM, IVORY, CYAN, MUTED, TRANSPARENT
from layout import default_positions, load_layouts, button_size, place_button

POSITION_FILE = CONFIG.with_name('positions.json')
user32 = ctypes.windll.user32
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL


def monitor_workareas():
    class MonitorInfo(ctypes.Structure):
        _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                    ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]
    result = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                      ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    get_info = user32.GetMonitorInfoW
    get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
    def visit(handle, dc, rect, data):
        info = MonitorInfo()
        info.cbSize = ctypes.sizeof(info)
        if get_info(handle, ctypes.byref(info)):
            r = info.rcWork
            result.append((r.left, r.top, r.right, r.bottom))
        return True
    user32.EnumDisplayMonitors(None, None, callback_type(visit), 0)
    return result


def client_window():
    found = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd, _):
        if user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            text = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, text, 256)
            if text.value == 'League of Legends':
                rect = wintypes.RECT()
                origin = wintypes.POINT(0, 0)
                user32.GetClientRect(hwnd, ctypes.byref(rect))
                user32.ClientToScreen(hwnd, ctypes.byref(origin))
                if rect.right >= 600 and rect.bottom >= 400:
                    found.append((hwnd, origin.x, origin.y, rect.right, rect.bottom))
        return True

    user32.EnumWindows(callback_type(visit), 0)
    return found[0] if len(found) == 1 else None


class Overlay:
    def __init__(self, demo=False):
        try:
            user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            pass
        self.root = tk.Tk()
        self.root.title('海克斯传讯 · LOLping' + (' · 演示' if demo else ''))
        self.root.geometry('530x575+850+100')
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)
        self.root.withdraw()
        self.demo = demo
        self.events, self.commands = queue.Queue(), queue.Queue()
        self.worker = Worker(self.events, self.commands, demo)
        self.players = []
        self.pending = False
        self.layouts = {}
        self.layout_slots = 5
        try:
            saved = json.loads(POSITION_FILE.read_text(encoding='utf-8'))
            self.layouts = load_layouts(saved)
        except (OSError, ValueError, TypeError):
            pass
        self.positions = self.layouts.setdefault('5', default_positions(5))
        self.calibrating = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='正在连接客户端…')
        self.feedback = tk.StringVar(value='将鼠标移到楼层按钮，查看发送内容')
        self.build_settings()
        self.buttons = []
        self.drag = None
        self.anchor = None
        self.worker.start()
        self.root.protocol('WM_DELETE_WINDOW', self.hide_settings)
        icon_image = make_icon(64)
        self.tray = pystray.Icon('LOLping', icon_image, 'LOLping · 正在连接', pystray.Menu(
            pystray.MenuItem('设置 / 连接状态', lambda: self.events.put(('show_settings', None)), default=True),
            pystray.MenuItem('退出', lambda: self.events.put(('exit', None)))))
        threading.Thread(target=self.tray.run, daemon=True).start()
        self.root.after(100, self.tick)

    def sync_buttons(self):
        slots = max(5, max((p['floor'] for p in self.players), default=0))
        if slots != self.layout_slots:
            self.layout_slots = slots
            self.positions = self.layouts.setdefault(str(slots), default_positions(slots))
            self.drag = None
        while len(self.buttons) > len(self.players):
            win, _ = self.buttons.pop()
            win.destroy()
            self.drag = None
        while len(self.buttons) < len(self.players):
            i = len(self.buttons)
            win = tk.Toplevel(self.root)
            win.withdraw()
            win.overrideredirect(True)
            win.attributes('-topmost', True)
            win.configure(bg=TRANSPARENT)
            win.attributes('-transparentcolor', TRANSPARENT)
            btn = HexButton(win, text='{}楼 · 等待'.format(i+1), transparent=True, command=lambda index=i: self.send(index))
            btn.pack(fill='both', expand=True)
            btn.bind('<ButtonPress-1>', lambda e, index=i: self.drag_start(e, index), add='+')
            btn.bind('<B1-Motion>', self.drag_move, add='+')
            btn.bind('<ButtonRelease-1>', self.drag_end, add='+')
            btn.bind('<Enter>', lambda e, index=i: self.preview(index), add='+')
            self.buttons.append((win, btn))

    def build_settings(self):
        self._window_icon = ImageTk.PhotoImage(make_icon(64), master=self.root)
        self.root.iconphoto(True, self._window_icon)
        # Native Windows title bar uses the same dark navy as the panel.
        self.root.update_idletasks()
        try:
            hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            dark = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)
        except (AttributeError, OSError):
            pass
        frame = tk.Frame(self.root, bg=BG, highlightbackground=GOLD_DIM, highlightthickness=1)
        frame.pack(fill='both', expand=True, padx=9, pady=9)
        content = tk.Frame(frame, bg=BG)
        content.pack(fill='both', expand=True, padx=23, pady=20)
        header = tk.Frame(content, bg=BG)
        header.pack(fill='x')
        titles = tk.Frame(header, bg=BG)
        titles.pack(side='left', anchor='n')
        tk.Label(titles, text='L O L p i n g   /   C O M M S', bg=BG, fg=GOLD,
                 font=('Segoe UI', 8)).pack(anchor='w')
        tk.Label(titles, text='海克斯传讯', bg=BG, fg=IVORY,
                 font=('Microsoft YaHei UI', 20, 'bold')).pack(anchor='w', pady=(6, 4))
        tk.Label(titles, text='选人阶段 · 楼层快捷消息', bg=BG, fg=MUTED,
                 font=('Microsoft YaHei UI', 9)).pack(anchor='w')
        seal = tk.Canvas(header, width=82, height=85, bg=BG, highlightthickness=0)
        seal.pack(side='right', anchor='n')
        emblem(seal, 41, 41, 24)
        divider = tk.Canvas(content, height=22, bg=BG, highlightthickness=0)
        divider.pack(fill='x', pady=(9, 4))
        divider.bind('<Configure>', lambda e: self.draw_divider(divider, e.width))
        status_card = tk.Frame(content, bg=SURFACE, highlightbackground='#263a40', highlightthickness=1)
        status_card.pack(fill='x', pady=(0, 16))
        tk.Label(status_card, text='◆  连 接 状 态', bg=SURFACE, fg=GOLD, font=('Microsoft YaHei UI', 9)).pack(anchor='w', padx=15, pady=(12, 5))
        tk.Label(status_card, textvariable=self.status, bg=SURFACE, fg=CYAN, wraplength=395,
                 justify='left', anchor='w', font=('Microsoft YaHei UI', 10)).pack(fill='x', padx=15, pady=(0, 14))
        tk.Label(content, text='消 息 预 览', bg=BG, fg=GOLD, font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=(0, 7))
        preview = tk.Frame(content, bg=SURFACE)
        preview.pack(fill='x')
        tk.Frame(preview, bg=GOLD_DIM, width=2).pack(side='left', fill='y')
        tk.Label(preview, textvariable=self.feedback, bg=SURFACE, fg=IVORY,
                 font=('Microsoft YaHei UI', 10), wraplength=385, justify='left', anchor='w',
                 padx=14, pady=13).pack(fill='x')
        tk.Label(content, text='每次发送一条 · 连续 4 条后冷却 2 秒', bg=BG, fg=MUTED,
                 font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=(7, 17))
        tk.Checkbutton(content, text='校准悬浮按钮位置', variable=self.calibrating, command=self.save_positions,
                       bg=BG, fg=IVORY, selectcolor=SURFACE, activebackground=BG, activeforeground=CYAN,
                       font=('Microsoft YaHei UI', 10), highlightthickness=0, bd=0).pack(anchor='w')
        tk.Label(content, text='选人时拖动各楼层按钮，关闭校准后保存', bg=BG, fg=MUTED,
                 font=('Microsoft YaHei UI', 9)).pack(anchor='w', padx=22, pady=(3, 16))
        footer = tk.Frame(content, bg=BG)
        footer.pack(fill='x')
        for i, (text, callback) in enumerate([('手动连接', self.connect), ('管理员重连', self.elevate), ('重置位置', self.reset_positions)]):
            footer.columnconfigure(i, weight=1, uniform='action')
            HexButton(footer, text=text, command=callback, height=42).grid(row=0, column=i, sticky='ew', padx=(0 if i == 0 else 7, 0))
        tk.Label(content, text='仅选人阶段显示  /  关闭设置收起至托盘', bg=BG, fg='#657974',
                 font=('Microsoft YaHei UI', 8)).pack(side='bottom', pady=(16, 0))
        # Fit the actual font metrics at the current Windows display scale.
        self.root.update_idletasks()
        self.root.geometry('{}x{}'.format(max(530, self.root.winfo_reqwidth()),
                                         max(575, self.root.winfo_reqheight())))

    def draw_divider(self, canvas, width):
        canvas.delete('all')
        center = width/2
        canvas.create_line(0, 11, center-9, 11, fill=GOLD_DIM)
        canvas.create_line(center+9, 11, width, 11, fill=GOLD_DIM)
        canvas.create_polygon(center, 7, center+4, 11, center, 15, center-4, 11, fill=GOLD, outline='')

    def hide_settings(self):
        self.calibrating.set(False)
        self.save_positions()
        self.root.withdraw()

    def save_positions(self):
        if not self.calibrating.get():
            try:
                POSITION_FILE.parent.mkdir(parents=True, exist_ok=True)
                POSITION_FILE.write_text(json.dumps({'version': 2, 'layouts': self.layouts}), encoding='utf-8')
                self.feedback.set('位置已保存；点击对应楼层按钮即可发送')
            except OSError:
                self.feedback.set('位置暂未保存，请检查目录权限')

    def reset_positions(self):
        self.positions = default_positions(self.layout_slots)
        self.layouts[str(self.layout_slots)] = self.positions
        self.save_positions()

    def drag_start(self, event, index):
        if self.calibrating.get():
            win = self.buttons[index][0]
            self.drag = (self.players[index]['floor'] - 1, event.x_root - win.winfo_x(), event.y_root - win.winfo_y())
            return 'break'

    def drag_move(self, event):
        if self.drag and self.anchor:
            i, dx, dy = self.drag
            _, x, y, width, height = self.anchor
            self.positions[i] = [max(0, min(1, (event.x_root-dx-x)/width)),
                                 max(0, min(1, (event.y_root-dy-y)/height))]
            return 'break'

    def drag_end(self, event):
        if self.calibrating.get():
            self.drag = None
            return 'break'

    def preview(self, index):
        if index < len(self.players):
            p = self.players[index]
            if p.get('name'):
                self.feedback.set(format_message(p['floor'], p['name']))

    def send(self, index):
        if self.calibrating.get() or self.pending or index >= len(self.players) or self.worker.limiter.remaining() > 0:
            return
        p = self.players[index]
        if p.get('name') and p.get('champion_id') and p.get('conversation'):
            self.pending = True
            self.commands.put(('send', dict(p)))
            self.feedback.set('正在发送：' + format_message(p['floor'], p['name']))

    def connect(self):
        path = filedialog.askopenfilename(parent=self.root, title='选择 LeagueClient/lockfile', filetypes=[('客户端连接文件','lockfile'),('所有文件','*')])
        if path:
            self.commands.put(('connect', path))

    def elevate(self):
        if ctypes.windll.shell32.IsUserAnAdmin():
            self.commands.put(('connect', self.worker.manual_path))
            return
        if getattr(sys, 'frozen', False):
            args = ['--demo'] if self.demo else []
        else:
            args = [str(Path(__file__).resolve())] + (['--demo'] if self.demo else [])
        result = ctypes.windll.shell32.ShellExecuteW(None, 'runas', sys.executable,
                    subprocess.list2cmdline(args), str(Path(sys.executable).parent), 0)
        if result > 32:
            self.close()
        else:
            self.feedback.set('未获得管理员权限，可以稍后重试')

    def tick(self):
        try:
            while True:
                event, data = self.events.get_nowait()
                if event == 'snapshot':
                    self.status.set(data['status'])
                    self.players = data['players']
                    self.tray.title = 'LOLping · ' + data['status']
                elif event in ('sent', 'send_error'):
                    self.pending = False
                    self.feedback.set(data)
                elif event == 'show_settings':
                    self.root.deiconify()
                    self.root.lift()
                elif event == 'exit':
                    self.close()
                    return
        except queue.Empty:
            pass
        self.sync_buttons()
        self.anchor = client_window()
        # Demo also works without a running client, inside a fixed preview rectangle.
        if self.demo and not self.anchor:
            self.anchor = (0, 60, 120, 1280, 720)
        foreground = user32.GetForegroundWindow()
        own_ids = [user32.GetParent(w.winfo_id()) or w.winfo_id() for w, _ in self.buttons]
        own_ids.append(user32.GetParent(self.root.winfo_id()) or self.root.winfo_id())
        visible = self.anchor and (self.demo or foreground == self.anchor[0] or foreground in own_ids)
        visible = visible and bool(self.players)
        remaining = self.worker.limiter.remaining()
        monitors = monitor_workareas()
        for i, (win, btn) in enumerate(self.buttons):
            if not visible:
                win.withdraw()
                continue
            _, x, y, width, height = self.anchor
            p = self.players[i]
            pos = self.positions[p['floor'] - 1]
            placed = place_button((x, y, width, height), pos,
                                  button_size(width, height, self.layout_slots), monitors)
            if placed is None:
                win.withdraw()
                continue
            px, py, bw, bh = placed
            ready = p and p.get('name') and p.get('champion_id') and p.get('conversation')
            text = '{}楼 · {}'.format(p['floor'], '拖动定位' if self.calibrating.get() else
                                     '{:.1f}s'.format(remaining) if remaining > 0 else '发送' if ready else '未选择')
            btn.configure(text=text, cooldown=remaining, state='normal' if self.calibrating.get() or (ready and not self.pending and remaining <= 0) else 'disabled')
            if win.state() == 'withdrawn':
                win.geometry('{}x{}'.format(bw, bh))
                win.deiconify()
            # Set physical desktop coordinates directly. Tk's negative geometry offsets
            # mean "from the right/bottom", which is incorrect on negative-coordinate monitors.
            hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
            user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), px, py, bw, bh, 0x0010)
        self.root.after(100, self.tick)

    def close(self):
        self.commands.put(('stop', None))
        self.tray.stop()
        self.root.destroy()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true')
    Overlay(parser.parse_args().demo).root.mainloop()
