#!/bin/bash
set -e
SDK="${ANDROID_SDK:-$HOME/Android/Sdk}"
BT=$SDK/build-tools/34.0.0
JAR=$SDK/platforms/android-34/android.jar
cd "$(dirname "$0")/android"

rm -rf build && mkdir -p build/gen build/classes build/dex

echo "[1/7] 编译资源"
$BT/aapt2 compile --dir res -o build/res.zip

echo "[2/7] 链接资源 + 打包 assets"
$BT/aapt2 link -o build/base.apk \
  -I "$JAR" \
  --manifest AndroidManifest.xml \
  -R build/res.zip \
  --java build/gen \
  -A assets \
  --min-sdk-version 24 \
  --target-sdk-version 34 \
  --auto-add-overlay

echo "[3/7] 编译 Java"
javac -source 8 -target 8 -nowarn -encoding UTF-8 \
  -cp "$JAR" -d build/classes \
  build/gen/com/stepx/neopilot/R.java \
  src/com/stepx/neopilot/*.java 2>&1 | grep -v "^警告\|warning: \[options\]" || true

echo "[4/7] 转 dex"
$BT/d8 --lib "$JAR" --min-api 24 --output build/dex \
  $(find build/classes -name '*.class')

echo "[5/7] 组装 APK"
cp build/base.apk build/assembled.apk
(cd build/dex && zip -q -u ../assembled.apk classes.dex)

echo "[6/7] 对齐"
$BT/zipalign -f -p 4 build/assembled.apk build/aligned.apk

echo "[7/7] 签名"
if [ ! -f ../neopilot.keystore ]; then
  keytool -genkeypair -keystore ../neopilot.keystore -alias neopilot \
    -keyalg RSA -keysize 2048 -validity 10000 \
    -storepass neopilot -keypass neopilot \
    -dname "CN=NeoPilot, OU=STEPX, O=Zach, L=Shenzhen, C=CN" >/dev/null 2>&1
fi
$BT/apksigner sign --ks ../neopilot.keystore \
  --ks-pass pass:neopilot --key-pass pass:neopilot \
  --out ../NeoPilot.apk build/aligned.apk

$BT/apksigner verify --print-certs ../NeoPilot.apk | head -4
echo
echo "产物：$(cd .. && pwd)/NeoPilot.apk"
ls -lh ../NeoPilot.apk
