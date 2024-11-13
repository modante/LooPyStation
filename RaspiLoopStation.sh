#!/bin/bash
killall fluidsynth
jack_control stop
killall jackd
cd ~/shared/RaspiLoopStation/
until python ./RaspiLoopStation.py
do
read -t 2 -p "I am going to wait for 2 seconds only ..."
done
