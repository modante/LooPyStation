# LooPyStation

10 Tracks Looper for Raspberry Pi with Mute, Solo, Undo, Clear and Volume functions and FluidSynth (a soundfont sample player) running at the same time, connected into looper and controlled with the footswitches.
To be used with any USB Sound Card and USB MIDI Keyboard (I use it with a Zoom H5 handy recorder and Evolution MK-461 MIDI Keyboard).

Inspired on the great Raspi Looper from RandomVertebrate https://github.com/RandomVertebrate/raspi-looper

### Features:
  - **10 Tracks** that can be selected with the Prev and Next buttons
  - 8-Segments display to show track number and bank/preset of Fluidsynth
  - **Mute/UnMute** & **Solo/Unsolo** per track synced with the starting of loop
  - **Undo** to the last recording (no overdubbing)
  - **Clear** of the selected track or all the tracks (when clear is applied on track 0)
  - Button to change **Mode** from Looper (without dot) to FluidSynth control
  - **Volume** per track. Starts on 0.7 (from 0.0 to 1.0)
  - The tracks can be **x times larger** than the master track (track 0)
  - Works with any **USB soundcard / MIDI Keyboard**
  - Setup of some **settings.py** like selecting soundcard, buffers size, or overshooting
  - **Latency compensation** using latency.py
  - Sampler FluidSynth loads at boot with the first (alphabetically) soundfont file (.sf2) on ./sf2 dir
  - FluidSynth L+R outputs connected to Looper Input
  - Works with **Jack** which allows easy and powerfull configuration

### How to play with LooPyStation?
- Design for 6 Buttons:
  - **Mode Button:** Switches from "Looper Mode" to "FluidSynth Mode".
  - **Rec Button:**
    - Press to Record. Press again to Stop Recording (Looper Mode)
    - If you want to stop and discard recording: Press Mute Button
  - **Mute/Solo Button:**
    - When Pressed: Mute selected Track. Press again to UnMute (Looper Mode)
    - When Held: Solo selected Track. Hold again to UnSolo (Looper Mode)
  - **Undo/Clear Button:**
    - When Pressed: If playing, Undo selected Track. If recording: Stops recording and reset Track
    - When Held: Clear selected Track, even if it is Recording. If track 0 is selected, Erase and Reset all the Tracks of the Looper  (Looper Mode)
  - **Prev Button:**
    - When Pressed: Jumps to the prev track (Looper Mode) / Decrease 1 preset number (Looper Mode)
    - When Held: Decrease 1 bank numbers (FluidSynth Mode) / Decrease Volume of selected Track (Looper Mode)
  - **Next Button:**
    - When Pressed: Jumps to the next track (Looper Mode) / Increase 1 preset number (Looper Mode)
    - When Held: Increase 1 bank numbers (FluidSynth Mode) / Increase Volume of selected Track (Looper Mode)
- **7 segments Display**
  - Looper Mode: Displays the Track number (0-9) or the volume of the selected Track (0-9)
  - FluidSynth Mode: Displays the last digit of selected Preset or the selected Bank
- **4 Leds**, 1 Red + 1 Green Leds on Rec and Mute/Solo Buttons:
  - Rec Button:
    - Yellow (Red+Green): When the Track is waiting to Record instantaneously (in case of Master Track 0) or when restarting the Loop
    - Red: When recording
  - Mute/Solo Button:
    - Green: When Track is Playing (not Muted)
    - Yellow: When Track is waiting the restarting of the Loop to Mute/UnMute or Solo/UnSolo
    - Red: Flashes when Loop is restarting
- If a MIDI Capture Port is detected on Jack, launches **FluidSynth**
  - Loads the default FluidR3_GM.sf2 (can be changed)
  - Pressing MODEBUTTON changes to FluidSynth Mode and the Prev/Next Buttons changes the Preset Number of GM SoundFont.
  - Pressing again MODEBUTTON changes to Looper Mode and the output L+R of FluidSynth is connected to Input port of Looper in order to be recorded on selected Track.

Works with **Jack** which allows an easy and powerfull configuration
  - All the physical inputs of soundcard (Jack capture ports) are connected to Input port of Looper
  - The Output Port of the Looper is connected with all the physical outputs of soundcard (Jack Playback ports)

Video: Fist sesions of Ephemeral Songs https://video.anartist.org/w/d7WA2y3ncZWzXvwGi6GirG

![imagen](https://github.com/user-attachments/assets/7e4a752f-1773-4dce-8de1-60d16994fe0f)

![imagen](https://github.com/user-attachments/assets/c0264a8e-3662-4eb9-855b-bd9bf15feecf)

ToDo:
- Document switches, connections and wiring
- Make a video to explain how it works

pd: Sorry for the code but I am newby like programmer (1st time using python). Any advice will be welcome :-D
Thank you for your understanding.
