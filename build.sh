#!/bin/bash
# 一条命令完成全部构建：自检 → 单测 → 驾驶舱 → 站点 → APK → 快照
set -e
cd "$(dirname "$0")"

echo "[1/5] 引擎自检"
python3 neopilot.py doctor

echo "[2/5] 单元测试"
python3 -m unittest -q test_neopilot

echo "[3/5] 生成驾驶舱与站点"
python3 neopilot.py dashboard
python3 build_site.py >/dev/null

echo "[4/5] 打包 APK"
cp -r site/* android/assets/
./build_apk.sh 2>&1 | tail -2

echo "[5/5] 生成 App 快照"
python3 neopilot.py snapshot

echo
echo "完成：$(ls -lh NeoPilot.apk | awk '{print $5}')  NeoPilot.apk"
