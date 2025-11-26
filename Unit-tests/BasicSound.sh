#!/bin/bash
aplay /usr/share/sounds/alsa/Front_Center.wav 2&>1 >/dev/null &
echo "you should hear 'front center'"
