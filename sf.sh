#!/bin/bash
killall fluidsynth
sleep 2
cd /home/raspi/shared/RaspiLoopStation/
fluidsynth -isj -a jack -r 48000 -g 0.9 -o "midi.driver=jack" -o "audio.jack.autoconnect=True" -o "shell.port=9988" -f ./sf.conf /usr/share/sounds/sf2/FluidR3_GM.sf2 &
exit


