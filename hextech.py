"""Resolution-independent Hextech-inspired UI primitives."""
import math
import tkinter as tk
from PIL import Image, ImageDraw

BG = '#070f18'
SURFACE = '#0c1a26'
GOLD = '#c5a566'
GOLD_DIM = '#645434'
IVORY = '#eee4ce'
CYAN = '#59d4df'
MUTED = '#879994'
TRANSPARENT = '#ff00ff'


def chamfer(x, y, width, height, cut):
    return [x+cut, y, x+width-cut, y, x+width, y+cut,
            x+width, y+height-cut, x+width-cut, y+height,
            x+cut, y+height, x, y+height-cut, x, y+cut]


def emblem(canvas, cx, cy, radius):
    vertices = []
    for i in range(6):
        angle = math.radians(60*i-90)
        vertices.extend([cx+radius*math.cos(angle), cy+radius*math.sin(angle)])
    canvas.create_polygon(vertices, fill=SURFACE, outline=GOLD, width=1)
    r = radius * .64
    canvas.create_polygon(cx, cy-r, cx+r*.6, cy, cx, cy+r,
                          cx-r*.6, cy, fill='#0d4552', outline=CYAN, width=1)
    canvas.create_line(cx, cy-r, cx, cy+r, fill=CYAN, width=1)
    canvas.create_line(cx-r*.6, cy, cx+r*.6, cy, fill='#2d8793', width=1)
    for dx in (-1, 1):
        canvas.create_line(cx+dx*(radius+5), cy, cx+dx*(radius+14), cy, fill=GOLD_DIM)


class HexButton(tk.Canvas):
    def __init__(self, parent, text='', command=None, width=138, height=40, transparent=False):
        self.label = text
        self.command = command
        self.enabled = True
        self.hovered = False
        self.pressed = False
        self.cooldown = 0
        self.transparent = transparent
        super().__init__(parent, width=width, height=height, bg=TRANSPARENT if transparent else BG,
                         highlightthickness=0, bd=0, cursor='hand2', takefocus=1)
        self.bind('<Configure>', lambda e: self.paint())
        self.bind('<Enter>', lambda e: self.set_hover(True))
        self.bind('<Leave>', lambda e: self.set_hover(False))
        self.bind('<ButtonPress-1>', self.press)
        self.bind('<ButtonRelease-1>', self.release)
        self.bind('<Return>', lambda e: self.invoke())
        self.bind('<space>', lambda e: self.invoke())
        self.bind('<FocusIn>', lambda e: self.paint())
        self.bind('<FocusOut>', lambda e: self.paint())

    def configure(self, cnf=None, **kwargs):
        options = dict(cnf or {}, **kwargs)
        changed = False
        for key, attr in [('text', 'label'), ('state', 'enabled'), ('cooldown', 'cooldown')]:
            if key in options:
                value = options.pop(key)
                if key == 'state':
                    value = value != 'disabled'
                if getattr(self, attr) != value:
                    setattr(self, attr, value)
                    changed = True
        if options:
            super().configure(**options)
        if changed:
            self.paint()

    config = configure

    def set_hover(self, hovered):
        self.hovered = hovered
        self.pressed = False
        self.paint()

    def press(self, event):
        if self.enabled:
            self.pressed = True
            self.paint()

    def release(self, event):
        pressed = self.pressed
        self.pressed = False
        self.paint()
        if pressed and 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.invoke()

    def invoke(self):
        if self.enabled and self.command:
            self.command()

    def paint(self):
        self.delete('all')
        w, h = self.winfo_width(), self.winfo_height()
        if w < 10 or h < 10:
            return
        active = self.enabled and self.hovered
        border = CYAN if active else GOLD if self.enabled else GOLD_DIM
        fill = '#123644' if self.pressed else '#102b38' if active else SURFACE
        cut = max(5, round(h*.17))
        self.create_polygon(chamfer(1, 1, w-3, h-3, cut), fill=fill, outline=border, width=1)
        self.create_polygon(chamfer(4, 4, w-9, h-9, max(2, cut-2)), fill='', outline='#25424b' if active else '#28302a')
        self.create_line(cut+4, 2, w-cut-5, 2, fill='#d9c18e' if self.enabled and not active else border)
        fg = IVORY if self.enabled else '#788482'
        size = max(9, round(h*.24))
        parts = self.label.split(' · ', 1)
        badge = len(parts) == 2 and parts[0].endswith('楼')
        if badge:
            cx = h*.58
            cy = h*.5
            r = h*.28
            self.create_polygon(cx, cy-r, cx+r, cy, cx, cy+r, cx-r, cy,
                                fill='#102632', outline=border)
            self.create_text(cx, cy, text=parts[0][:-1], fill=GOLD if self.enabled else MUTED,
                             font=('Georgia', -max(12, round(h*.36)), 'bold'))
            self.create_line(h*1.13, h*.25, h*1.13, h*.75, fill=GOLD_DIM)
            self.create_text(w*.60, h*.50, text=parts[1], fill=fg,
                             font=('Microsoft YaHei UI', -max(12, round(h*.30)), 'bold'))
            x, y, r = w-14, h*.50, 3
            self.create_polygon(x, y-r, x+r, y, x, y+r, x-r, y,
                                fill=CYAN if self.enabled else GOLD_DIM, outline='')
        else:
            self.create_text(w/2, h/2, text=self.label, fill=fg,
                             font=('Microsoft YaHei UI', -max(12, round(h*.28)), 'bold'))
        if self.cooldown > 0:
            start, end = cut+5, w-cut-6
            self.create_line(start, h-5, end, h-5, fill='#253638')
            self.create_line(start, h-5, start+(end-start)*max(0, 1-self.cooldown/2), h-5, fill=CYAN, width=2)


def make_icon(size=256):
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(image)
    def points(values):
        return [(int(x*size/100), int(y*size/100)) for x, y in values]
    outer = points([(50, 3), (91, 26), (91, 74), (50, 97), (9, 74), (9, 26)])
    d.polygon(outer, fill=BG)
    d.line(outer+[outer[0]], fill=GOLD, width=max(1, size//32))
    inner = points([(50, 12), (83, 31), (83, 69), (50, 88), (17, 69), (17, 31)])
    d.line(inner+[inner[0]], fill=GOLD_DIM, width=max(1, size//100))
    crystal = points([(50, 23), (68, 49), (50, 77), (32, 49)])
    d.polygon(crystal, fill='#135365')
    d.line(crystal+[crystal[0]], fill=CYAN, width=max(1, size//55))
    d.line(points([(50, 23), (50, 77)]), fill='#b5f4f0', width=max(1, size//80))
    d.line(points([(32, 49), (68, 49)]), fill=CYAN, width=max(1, size//90))
    return image
