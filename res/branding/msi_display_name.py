# -*- coding: utf-8 -*-
"""MSI 显示名替换：在 res/msi/preprocess.py 之后、msbuild 之前运行（cwd 必须是 res/msi）

覆盖两处显示文字：
1. 语言文件 Package/Language/*.wxl —— 开始菜单/桌面快捷方式名、卸载入口、
   "卸载 RustDesk"等显示串；
2. preprocess.py 生成的 Product / Description / Manufacturer define ——
   控制面板"程序和功能"(ARP) 里的产品名、描述与发布者。

为什么不用 --app-name 直接传品牌名：preprocess.py 的 app_name 同时用于
dist 目录内 {app_name}.exe 的组件匹配（rustdesk.exe），传 TaDesk 会因找不到
tadesk.exe 而丢失主程序组件，故只改显示 define、不动 app-name。

环境变量：
  APP_DISPLAY_NAME  显示名（默认 TaDesk）
  MSI_MANUFACTURER  ARP 发布者（默认 中科天安）
"""
import glob
import os
import sys

# GitHub 英文 Windows runner 的 Python 管道输出编码是 cp1252，
# 含中文的 print 会触发 UnicodeEncodeError 导致步骤失败，这里强制 UTF-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

NAME = os.environ.get('APP_DISPLAY_NAME', 'TaDesk')
MANUFACTURER = os.environ.get('MSI_MANUFACTURER', '中科天安')


def main():
    # 1) 语言文件显示串（wxl 中 "RustDesk" 只出现在显示字符串的 Value 里）
    for f in glob.glob('Package/Language/*.wxl'):
        with open(f, encoding='utf-8') as fp:
            s = fp.read()
        if 'RustDesk' not in s:
            continue
        with open(f, 'w', encoding='utf-8', newline='') as fp:
            fp.write(s.replace('RustDesk', NAME))
        print('wxl 已替换: %s' % f)

    # 2) preprocess 生成的 defines（原位插入在 Package.wxs 中）
    defines = [
        ('<?define Product="RustDesk" ?>', '<?define Product="%s" ?>' % NAME),
        ('<?define Description="RustDesk Installer" ?>',
         '<?define Description="%s Installer" ?>' % NAME),
        ('<?define Manufacturer="Purslane Tech Pte. Ltd." ?>',
         '<?define Manufacturer="%s" ?>' % MANUFACTURER),
    ]
    for f in glob.glob('Package/**/*.wxs', recursive=True):
        with open(f, encoding='utf-8') as fp:
            s = fp.read()
        o = s
        for old, new in defines:
            s = s.replace(old, new)
        if s != o:
            with open(f, 'w', encoding='utf-8', newline='') as fp:
                fp.write(s)
            print('define 已替换: %s' % f)
    print('MSI 显示名替换完成: %s / %s' % (NAME, MANUFACTURER))


if __name__ == '__main__':
    main()
