#!/bin/sh

ps | grep -v grep | grep -q access > /dev/null
if [ $? -eq 1 ]; then
  /mnt/sda1/ac/bin/access.py < /dev/null > /dev/null 2>&1 &
fi
