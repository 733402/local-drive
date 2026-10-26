#!/data/data/com.termux/files/usr/bin/bash
set -e

pkg update -y
pkg install python -y
termux-setup-storage

python -m pip install -r requirements.txt

mkdir -p "$HOME/storage/external-1/SDDrive"

echo "SDDrive installed"
echo "Run it with: python sddrive.py"
