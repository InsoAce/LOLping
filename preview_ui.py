"""Offline UI preview; never connects to the client or sends messages."""
import ctypes
import tkinter as tk
from overlay import Overlay, user32
from hextech import BG, GOLD, MUTED, IVORY, HexButton


class Preview(Overlay):
    def __init__(self):
        try:
            user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            pass
        self.root = tk.Tk()
        self.root.title('LOLping · 设置样式预览')
        self.root.geometry('530x575+550+140')
        self.root.configure(bg=BG)
        self.root.resizable(False, False)
        self.status = tk.StringVar(value='选人中 · 聊天室已连接')
        self.feedback = tk.StringVar(value='1楼 (寒冰射手) - 存活')
        self.calibrating = tk.BooleanVar(value=False)
        self.build_settings()
        sample = tk.Toplevel(self.root)
        sample.title('LOLping · 悬浮按钮预览')
        sample.geometry('310x420+1270+140')
        sample.configure(bg=BG)
        sample.resizable(False, False)
        tk.Label(sample, text='楼 层 悬 浮 按 钮', bg=BG, fg=GOLD, font=('Microsoft YaHei UI', 11, 'bold')).pack(pady=(22, 8))
        tk.Label(sample, text='预览窗口 · 不发送消息', bg=BG, fg=MUTED, font=('Microsoft YaHei UI', 9)).pack(pady=(0, 15))
        self.samples = []
        for i in range(5):
            text = '{}楼 · {}'.format(i+1, '未选择' if i == 2 else '1.2s' if i == 3 else '发送')
            btn = HexButton(sample, text=text, width=202, height=43, command=lambda: self.feedback.set('样式预览 · 不会连接或发送消息'))
            btn.pack(pady=6)
            if i in (2, 3):
                btn.configure(state='disabled', cooldown=1.2 if i == 3 else 0)
            self.samples.append(btn)
        self.samples[1].set_hover(True)

    def connect(self):
        self.feedback.set('样式预览 · 不会连接或发送消息')

    elevate = connect
    reset_positions = connect
    save_positions = connect


if __name__ == '__main__':
    Preview().root.mainloop()
