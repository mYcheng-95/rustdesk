# -*- coding: utf-8 -*-
"""中科天安品牌图标一键生成脚本

设计定稿：方案 R2「水面倒影」——天安鸟（原色渐变、含投影）居上，
下方为水面倒影（垂直翻转 + 压缩 + 自上而下渐隐），
下半区极淡蓝灰渐变模拟水面；底板为白色圆角方块（圆角 14.5%，与 RustDesk 原版一致）。

素材源（本目录）：
  bird.png           完整鸟形（含灰色投影层），透明底
  lockup-wide.png    官方横版锁版 -02（鸟形 + 中科天安黑字），透明底

运行：python res/branding/gen_branding.py（在仓库根目录执行）
依赖：Pillow、numpy（仅本地重新生成时需要；生成产物已提交，CI 无需运行本脚本）
"""
from PIL import Image, ImageDraw, ImageFilter
import numpy as np
import os
import io
import struct
import base64

# 仓库根目录（脚本位于 res/branding/ 下，向上两级）
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SRC = os.path.join(ROOT, 'res', 'branding')

S = 1024          # 主画布尺寸
RADIUS = 148      # 圆角半径（RustDesk 原版 icon.png 实测 14.5%）
BIRD_W = 0.54     # 主鸟宽度占画布比例
BIRD_CY = 0.385   # 主鸟中心 y 占画布比例（偏上，给倒影留空间）
GAP = 26          # 水线间隙（px @1024）
REF_COMPRESS = 0.8    # 倒影高度压缩比
REF_ALPHA = 0.42      # 倒影起始不透明度
WATER_TINT = (232, 240, 246)   # 水面极淡蓝灰 #E8F0F6
WATER_START = 0.52    # 水面渐变起始（占画布高度比例）
WATER_MAX = 0.55      # 水色最大混合强度


def load_bird():
    """载入完整鸟形素材（含投影）并裁剪到内容边界"""
    im = Image.open(os.path.join(SRC, 'bird.png')).convert('RGBA')
    return im.crop(im.getbbox())


def bird_pure(bird):
    """剔除灰色投影层，仅保留橙色鸟形主体（用于剪影类图标）"""
    arr = np.array(bird).astype(np.int16)
    mx = arr[:, :, 0:3].max(axis=2)          # RGB 最大通道
    mn = arr[:, :, 0:3].min(axis=2)          # RGB 最小通道
    gray = ((mx - mn) < 40) & (mx < 200)     # 低饱和且不明亮 → 判定为投影
    arr[:, :, 3] = np.where(gray, 0, arr[:, :, 3])   # 投影像素透明化
    out = Image.fromarray(arr.astype('uint8'))
    return out.crop(out.getbbox())


def make_reflection(bird, w):
    """生成倒影：垂直翻转 → 高度压缩 → 自上而下线性渐隐"""
    h = round(bird.height * w / bird.width)                       # 等比高度
    ref = bird.resize((w, h), Image.LANCZOS).transpose(Image.FLIP_TOP_BOTTOM)  # 翻转
    rh = round(h * REF_COMPRESS)                                  # 压缩倒影高度
    ref = ref.resize((w, rh), Image.LANCZOS)
    a = np.array(ref).astype(np.float32)
    fade = np.linspace(REF_ALPHA, 0.0, rh).reshape(rh, 1)         # 上实下虚渐隐
    a[:, :, 3] = a[:, :, 3] * fade
    return Image.fromarray(a.astype('uint8'))


def compose_on(canvas, bird, waterline_only=False):
    """在给定底板上构图：水面渐变（可选）→ 主鸟 → 倒影"""
    im = canvas
    if not waterline_only:
        # 下半区水面渐变：白色 → 极淡蓝灰，自 52% 高度起线性加深
        a = np.array(im).astype(np.float32)
        yy = np.arange(im.height).reshape(im.height, 1)   # (H,1) 与 (H,W) 通道切片对齐
        t = np.clip((yy - im.height * WATER_START) / (im.height * (1 - WATER_START)), 0, 1)
        for ch in range(3):
            a[:, :, ch] = a[:, :, ch] * (1 - t * WATER_MAX) + WATER_TINT[ch] * (t * WATER_MAX)
        im = Image.fromarray(a.astype('uint8'))
    w = int(im.width * BIRD_W)
    h = round(bird.height * w / bird.width)
    bs = bird.resize((w, h), Image.LANCZOS)
    by = int(im.height * BIRD_CY - h / 2)
    im.alpha_composite(bs, ((im.width - w) // 2, by))
    im.alpha_composite(make_reflection(bird, w), ((im.width - w) // 2, by + h + GAP))
    return im


def tile_master(bird):
    """定稿主图标：白色圆角方块 + 水面 + 鸟 + 倒影（1024 RGBA，四角透明）"""
    base = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(base).rounded_rectangle(
        [0, 0, S - 1, S - 1], radius=RADIUS, fill=(255, 255, 255, 255))
    return compose_on(base, bird)


def fullbleed_master(bird):
    """全出血方形版（iOS / macOS 系统自行裁圆角）：白底不透明"""
    base = Image.new('RGBA', (S, S), (255, 255, 255, 255))
    return compose_on(base, bird)


def adaptive_fg_master(bird):
    """Android 自适应图标前景层：透明底，内容控制在中央 66% 安全区内
    （不含水面渐变——渐变的半透明矩形会污染单色主题层的剪影）"""
    base = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    return compose_on(base, bird, waterline_only=True)


def silhouette(bird_p, color):
    """按 alpha 通道生成单色剪影（安卓通知图标 / macOS 托盘模板图）"""
    a = np.array(bird_p)
    out = np.zeros_like(a)
    out[:, :, 0:3] = color
    out[:, :, 3] = a[:, :, 3]
    return Image.fromarray(out)


def fit_box(im, box):
    """等比缩放到边长 box 的包围盒内（保持比例，居中留白）"""
    w, h = im.size
    scale = box / max(w, h)
    return im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)


def save_png(im, rel, mode=None):
    """保存 PNG 到仓库相对路径（可指定转换色彩模式）"""
    p = os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if mode:
        im = im.convert(mode)
    im.save(p)
    print(f'  {rel}  {im.size} {im.mode}')


def save_ico(im, rel, sizes):
    """保存多尺寸 ICO（Pillow 自动从源图缩放生成各档位）"""
    p = os.path.join(ROOT, rel)
    im.save(p, sizes=sizes)
    print(f'  {rel}  档位={[s[0] for s in sizes]}')


def save_icns(fb, rel):
    """用 Pillow 原生 ICNS 写入（带 TOC 结构，含 ic07~ic14 共 32~1024 档位）"""
    sizes = [32, 64, 128, 256, 512]     # 1024 由主图自身承担
    appends = [fb.resize((s, s), Image.LANCZOS) for s in sizes]
    p = os.path.join(ROOT, rel)
    fb.save(p, append_images=appends)
    print(f'  {rel}  档位=1024/512/256/128/64/32 {os.path.getsize(p) // 1024}KB')


def save_svg_with_png(fb, rel, px):
    """生成内嵌 PNG 的 SVG（Linux hicolor 矢量位、Flutter UI 兜底图标）"""
    buf = io.BytesIO()
    fb.resize((px, px), Image.LANCZOS).save(buf, 'PNG')
    b64s = base64.b64encode(buf.getvalue()).decode()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{px}" height="{px}" '
           f'viewBox="0 0 {px} {px}">'
           f'<image width="{px}" height="{px}" href="data:image/png;base64,{b64s}"/></svg>')
    p = os.path.join(ROOT, rel)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(svg)
    print(f'  {rel}  内嵌{px}px {os.path.getsize(p) // 1024}KB')


def make_logo_dark(light):
    """横版锁版深色主题变体：黑字 → 白字（鸟形橙色保留）"""
    a = np.array(light.convert('RGBA')).astype(np.int16)
    lum = a[:, :, 0:3].mean(axis=2)          # 亮度
    dark = lum < 70                          # 深色文字像素掩码
    a[:, :, 0:3][dark] = 255                 # 翻白
    out = Image.fromarray(a.astype('uint8'))
    return out.crop(out.getbbox())


def main():
    bird = load_bird()
    pure = bird_pure(bird)

    print('== 主设计母版 ==')
    tile = tile_master(bird)          # 圆角版（exe/托盘/Linux/安卓 legacy/UI）
    fb = fullbleed_master(bird)       # 全出血版（iOS/macOS，系统裁形）
    fg = adaptive_fg_master(bird)     # 安卓自适应前景

    print('== res/ 核心图标 ==')
    save_png(tile, 'res/icon.png')
    save_ico(tile, 'res/icon.ico', [(16, 16), (24, 24), (32, 32), (48, 48),
                                    (64, 64), (128, 128), (256, 256)])
    save_ico(tile, 'res/tray-icon.ico', [(16, 16), (24, 24), (32, 32), (48, 48)])
    save_png(tile.resize((32, 32), Image.LANCZOS), 'res/32x32.png', mode='P')
    save_png(tile.resize((128, 128), Image.LANCZOS), 'res/128x128.png', mode='P')
    save_png(tile.resize((256, 256), Image.LANCZOS), 'res/128x128@2x.png')
    save_png(fb, 'res/mac-icon.png')
    save_png(silhouette(pure, (0, 0, 0)).resize((60, 60), Image.LANCZOS),
             'res/mac-tray-dark-x2.png')     # macOS 托盘模板图（黑色剪影，按 alpha 渲染）
    save_png(silhouette(pure, (255, 255, 255)).resize((48, 48), Image.LANCZOS),
             'res/mac-tray-light-x2.png')
    save_svg_with_png(fb, 'res/scalable.svg', 512)   # Linux hicolor 矢量位

    print('== flutter/assets/ 界面资源 ==')
    save_png(tile.resize((256, 256), Image.LANCZOS), 'flutter/assets/icon.png')
    save_ico(tile, 'flutter/assets/icon.ico', [(16, 16), (24, 24), (32, 32), (48, 48),
                                               (64, 64), (128, 128), (256, 256)])
    save_svg_with_png(tile, 'flutter/assets/icon.svg', 256)   # UI 兜底图标
    lockup = Image.open(os.path.join(SRC, 'lockup-wide.png')).convert('RGBA')
    lockup = lockup.crop(lockup.getbbox())
    logo = lockup.resize((1200, round(lockup.height * 1200 / lockup.width)), Image.LANCZOS)
    save_png(logo, 'flutter/assets/logo.png')            # 默认（浅色）
    save_png(logo, 'flutter/assets/logo_light.png')      # 浅色主题：黑字原版
    save_png(make_logo_dark(logo), 'flutter/assets/logo_dark.png')   # 深色主题：白字

    print('== Windows / macOS ==')
    save_ico(tile, 'flutter/windows/runner/resources/app_icon.ico',
             [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    save_icns(fb, 'flutter/macos/Runner/AppIcon.icns')

    print('== Android mipmap ==')
    dens = {'mdpi': 1, 'hdpi': 1.5, 'xhdpi': 2, 'xxhdpi': 3, 'xxxhdpi': 4}
    for d, k in dens.items():
        p = f'flutter/android/app/src/main/res/mipmap-{d}'
        # legacy 启动图标 = 圆角定稿版（48dp 基准）
        sz = round(48 * k)
        save_png(tile.resize((sz, sz), Image.LANCZOS), f'{p}/ic_launcher.png')
        save_png(tile.resize((sz, sz), Image.LANCZOS), f'{p}/ic_launcher_round.png')
        # 自适应前景 = 透明底构图（108dp 基准）
        szf = round(108 * k)
        save_png(fg.resize((szf, szf), Image.LANCZOS), f'{p}/ic_launcher_foreground.png')
        # 通知图标 = 纯白剪影（24dp 基准，状态栏要求单色透明）
        szn = round(24 * k)
        sil24 = silhouette(pure, (255, 255, 255))
        sil24 = sil24.resize((szn, round(sil24.height * szn / sil24.width)), Image.LANCZOS)
        canvas = Image.new('RGBA', (szn, szn), (0, 0, 0, 0))
        canvas.alpha_composite(sil24, (0, (szn - sil24.height) // 2))
        save_png(canvas, f'{p}/ic_stat_logo.png')

    print('== iOS AppIcon ==')
    ios = [('Icon-App-20x20@1x.png', 20), ('Icon-App-20x20@2x.png', 40),
           ('Icon-App-20x20@3x.png', 60), ('Icon-App-29x29@1x.png', 29),
           ('Icon-App-29x29@2x.png', 58), ('Icon-App-29x29@3x.png', 87),
           ('Icon-App-40x40@1x.png', 40), ('Icon-App-40x40@2x.png', 80),
           ('Icon-App-40x40@3x.png', 120), ('Icon-App-60x60@2x.png', 120),
           ('Icon-App-60x60@3x.png', 180), ('Icon-App-76x76@1x.png', 76),
           ('Icon-App-76x76@2x.png', 152), ('Icon-App-83.5x83.5@2x.png', 167),
           ('Icon-App-1024x1024@1x.png', 1024)]
    base = 'flutter/ios/Runner/Assets.xcassets/AppIcon.appiconset'
    for name, sz in ios:
        save_png(fb.resize((sz, sz), Image.LANCZOS), f'{base}/{name}', mode='RGB')

    print('全部生成完成。')


if __name__ == '__main__':
    main()
