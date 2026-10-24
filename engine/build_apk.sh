#!/bin/sh
# cwd = job dir, after package.py. Builds build/<slug>.apk (resource-only), signs it, runs the
# Play memory-footprint check. usage: sh build_apk.sh <slug>
set -e
SLUG="$1"
J=/opt/android/platforms/android-34/android.jar
KEYS=/app/data/keys
mkdir -p "$KEYS" build/apk
rm -rf build/apk/*
aapt2 compile --dir build/wff/res -o build/apk/res.zip
aapt2 link -o build/apk/unsigned.apk -I $J --manifest build/wff/AndroidManifest.xml build/apk/res.zip --auto-add-overlay
zipalign -f -p 4 build/apk/unsigned.apk build/apk/aligned.apk
[ -f $KEYS/debug.jks ] || keytool -genkeypair -keystore $KEYS/debug.jks -storepass android -keypass android \
    -alias wff -keyalg RSA -keysize 2048 -validity 10000 -dname CN=watchface-studio >/dev/null 2>&1
apksigner sign --ks $KEYS/debug.jks --ks-pass pass:android --key-pass pass:android --out "build/$SLUG.apk" build/apk/aligned.apk
apksigner verify "build/$SLUG.apk"
java -jar /opt/tools/memory-footprint.jar --watch-face "build/$SLUG.apk" --schema-version 2 \
    --ambient-limit-mb 10 --active-limit-mb 100 --apply-v1-offload-limitations --estimate-optimization | tee build/memory.txt
grep -q PASS build/memory.txt
