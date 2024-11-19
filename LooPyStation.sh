#!/bin/bash
killall fluidsynth
cd ~/shared/LooPyStation/
if pgrep -x "python" > /dev/null; then
    echo "Python is running."
else
    echo "Python is NOT running."
    until python ./LooPyStation.py
        do
        read -t 1 -p "I am going to wait for 1 second ..."
    done
fi
