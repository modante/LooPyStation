#!/bin/bash
killall fluidsynth
jack_control stop
killall jackd
cd ~/shared/LooPyStation/
until python ./LooPyStation.py
do
#jack_control stop
#killall jackd
read -t 2 -p "I am going to wait for 2 seconds only ..."
done
