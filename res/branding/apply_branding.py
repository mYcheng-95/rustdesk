# -*- coding: utf-8 -*-
"""CI 品牌文字替换：RustDesk → TaDesk

在 GitHub Actions checkout 之后、构建之前执行（见 flutter-build.yml 中
「Apply TaDesk branding」步骤）。仓库源码文字保持原样，构建期动态替换。

替换范围仅限"用户可见的显示文字"；二进制名（rustdesk.exe / librustdesk.dll）、
服务注册名、MSI 负载名、RustDeskPrinterDriver 等不动——动了会破坏
MSI/WiX/驱动/服务逻辑（MSI 的 app-name 同时用于 dist 内 exe 组件匹配）。

设计约束：
- 任何一处模式未命中即报错退出，避免上游文件变更导致品牌替换静默失效；
- 显示名可用环境变量 APP_DISPLAY_NAME 覆盖（默认 TaDesk）；
- 根目录可用 BRANDING_ROOT 覆盖（默认为仓库根，便于本地干跑测试）。

用法：python res/branding/apply_branding.py
"""
import os
import re
import sys

ROOT = os.environ.get(
    'BRANDING_ROOT',
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
NAME = os.environ.get('APP_DISPLAY_NAME', 'TaDesk')

# (文件, [(旧串, 新串), ...])——全部是显示文字
REPLACES = [
    # 全局应用名：主窗口标题、托盘提示、关于页、URI 前缀(tadesk://)、
    # 配置目录名全部由 hbb_common 的 APP_NAME 默认值派生（此文件在子模块中，
    # 需将子模块指向自己的 fork 才能被 checkout 出来后修改）
    ('libs/hbb_common/src/config.rs',
     [('RwLock::new("RustDesk".to_owned())',
       'RwLock::new("%s".to_owned())' % NAME)]),
    # 连接页 tab 标题的硬编码品牌名
    ('flutter/lib/desktop/widgets/tabbar_widget.dart',
     [('"RustDesk",', '"%s",' % NAME)]),
    # Android 桌面图标下名称与输入法服务标签（先长后短，避免部分匹配）
    ('flutter/android/app/src/main/AndroidManifest.xml',
     [('android:label="RustDesk Input"', 'android:label="%s Input"' % NAME),
      ('android:label="RustDesk"', 'android:label="%s"' % NAME)]),
    # iOS 显示名（CFBundleDisplayName / CFBundleName 两处字面量）
    ('flutter/ios/Runner/Info.plist',
     [('<string>RustDesk</string>', '<string>%s</string>' % NAME)]),
    # Linux 启动器显示名（deb/rpm 安装后菜单里看到的名称）
    ('res/rustdesk.desktop', [('Name=RustDesk', 'Name=%s' % NAME)]),
    ('res/rustdesk-link.desktop', [('Name=RustDesk', 'Name=%s' % NAME)]),
    # systemd 服务描述（服务名 Service= 不动）
    ('res/rustdesk.service',
     [('Description=RustDesk', 'Description=%s' % NAME)]),
]


def replace_in_files():
    """逐文件做字面量替换；任何模式未命中都记录为错误"""
    errors = []
    for rel, pairs in REPLACES:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            errors.append('%s: 文件不存在' % rel)
            continue
        with open(p, encoding='utf-8') as f:
            s = f.read()
        for old, new in pairs:
            if old not in s:
                errors.append('%s: 未找到模式 [%s]' % (rel, old))
                continue
            s = s.replace(old, new)
        # newline='' 避免行尾符被翻译，保持原文件风格
        with open(p, 'w', encoding='utf-8', newline='') as f:
            f.write(s)
    return errors


def patch_macos_plist():
    """macOS 插入 CFBundleDisplayName（Finder 显示名）
    CFBundleName 的值是构建变量 $(PRODUCT_NAME)，不能直接替换字面量，
    所以采用紧随其后插入 CFBundleDisplayName 的方式。"""
    p = os.path.join(ROOT, 'flutter/macos/Runner/Info.plist')
    with open(p, encoding='utf-8') as f:
        s = f.read()
    if 'CFBundleDisplayName' in s:
        return []
    s2 = re.sub(
        r'(<key>CFBundleName</key>\s*<string>[^<]*</string>)',
        r'\1\n\t<key>CFBundleDisplayName</key>\n\t<string>%s</string>' % NAME,
        s, count=1)
    if s2 == s:
        return ['flutter/macos/Runner/Info.plist: CFBundleName 锚点未命中']
    with open(p, 'w', encoding='utf-8', newline='') as f:
        f.write(s2)
    return []


def main():
    errors = replace_in_files() + patch_macos_plist()
    if errors:
        print('品牌替换失败，以下模式未命中（上游文件可能已变更）：')
        print('\n'.join('  ' + e for e in errors))
        sys.exit(1)
    print('品牌文字替换完成: RustDesk -> %s' % NAME)


if __name__ == '__main__':
    main()
