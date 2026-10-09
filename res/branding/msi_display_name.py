# -*- coding: utf-8 -*-
"""MSI 品牌调整：在 res/msi/preprocess.py 之后、msbuild 之前运行（cwd 必须是 res/msi）

覆盖四件事：
1. 语言文件 Package/Language/*.wxl —— 开始菜单/桌面快捷方式名、卸载入口等显示串；
2. preprocess.py 生成的 Product / Description / Manufacturer define ——
   控制面板"程序和功能"(ARP) 里的产品名、描述与发布者；
3. UpgradeCode 换为按品牌名派生 —— 官方与本产品原本共用 uuid5("RustDesk.exe")，
   同码 MSI 会互相视作"相关产品"：已装官方版时装不进来（MajorUpgrade 拦截）、
   升级时互相卸载。同一产品的 UpgradeCode 必须跨版本稳定，故按品牌名确定性派生；
4. wxs 中 $(var.Product).exe 的注册表引用改回 $(var.ProductLower).exe ——
   Product 改为品牌名后，这些引用会指向不存在的 TaDesk.exe（实际负载是
   rustdesk.exe，即 ProductLower），导致文件关联与默认图标断链。
   注意：Software\$(var.Product)\InstallState\$(var.Product) 等键保持品牌名
   不动——客户端运行时按 APP_NAME（TaDesk）构造同一路径读取安装状态。

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
import uuid

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
    old_upgrade = str(uuid.uuid5(uuid.NAMESPACE_OID, 'RustDesk.exe'))
    new_upgrade = str(uuid.uuid5(uuid.NAMESPACE_OID, NAME + '.exe'))
    defines = [
        ('<?define Product="RustDesk" ?>', '<?define Product="%s" ?>' % NAME),
        ('<?define Description="RustDesk Installer" ?>',
         '<?define Description="%s Installer" ?>' % NAME),
        ('<?define Manufacturer="Purslane Tech Pte. Ltd." ?>',
         '<?define Manufacturer="%s" ?>' % MANUFACTURER),
        # 3) UpgradeCode 分离（preprocess 按 app-name=RustDesk 生成，替换为品牌派生值）
        ('<?define UpgradeCode = "%s" ?>' % old_upgrade,
         '<?define UpgradeCode = "%s" ?>' % new_upgrade),
    ]
    for f in glob.glob('Package/**/*.wxs', recursive=True):
        with open(f, encoding='utf-8') as fp:
            s = fp.read()
        o = s
        for old, new in defines:
            s = s.replace(old, new)
        # 4) exe 引用断链修复：注册表里的可执行文件路径指向实际负载 rustdesk.exe
        s = s.replace('$(var.Product).exe', '$(var.ProductLower).exe')
        if s != o:
            with open(f, 'w', encoding='utf-8', newline='') as fp:
                fp.write(s)
            print('define/引用 已替换: %s' % f)
    print('MSI 品牌调整完成: %s / %s / UpgradeCode=%s' % (NAME, MANUFACTURER, new_upgrade))


if __name__ == '__main__':
    main()
