# Building for ARM (Armbian/Raspberry Pi)

PyInstaller **cannot** cross-compile. To get an ARM binary, you must run the build command **on the ARM device itself**.

## 1. Setup on Device
Follow the "Deployment Guide" (`DEPLOY.md`) to pull the code and set up the environment on your Armbian device.

## 2. Install Build Tools
On the Armbian device, ensure you have the necessary tools:
```bash
cd /opt/tg_bot
source .venv/bin/activate
pip install pyinstaller
```

## 3. Build the Binary
Run this command **on the Armbian device**:

```bash
pyinstaller --name tg_bot \
            --onefile \
            --clean \
            --hidden-import "beancount.loader" \
            --hidden-import "beancount.plugins" \
            main.py
```

## 4. Locate and Move Binary
The binary will be created in `dist/tg_bot`.
Move it to your root folder (or wherever you want to run it from):

```bash
mv dist/tg_bot .
```

## 5. Clean Up (Optional)
You can remove the build artifacts:
```bash
rm -rf build dist tg_bot.spec
```

## 6. Run
```bash
# Ensure config/ and data/ are likely strictly next to the binary
./tg_bot
```
