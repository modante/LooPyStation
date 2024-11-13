# Raspi-Loop-Station

Inspired on the great Raspi Looper from RandomVertebrate https://github.com/RandomVertebrate/raspi-looper

Main changes:
- New design for 6 Buttons:
  - **Mode Button:** Switches from "Looper Mode" to "FluidSynth Mode".
  - **Rec Button:**
    - Press to Record. Press again to Stop Recording (Looper Mode)
  - **Mute/Solo Button:**
    - When Pressed: Mute selected Track. Press again to UnMute (Looper Mode)
    - When Held: Solo selected Track. Hold again to UnSolo (Looper Mode)
  - **Undo/Clear Button:**
    - When Presses: Undo selected Track  (Looper Mode)
    - When Held: Clear selected Track, even if it is Recording. If track 0 is selected, Erase and Reset all the Tracks of the Looper  (Looper Mode)
  - **Prev Button:**
    - When Pressed: Jumps to the prev track (Looper Mode) / Decrease 1 preset number (Looper Mode)
    - When Held: Decrease 10 preset numbers (FluidSynth Mode)
  - **Next Button:**
    - When Pressed: Jumps to the next track (Looper Mode) / Increase 1 preset number (Looper Mode)
    - When Held: Increase 10 preset numbers (FluidSynth Mode)
- Added a 7 segments Display
  - Displays the Track number (0-9) (Looper Mode)
  - Displays the last digit of GM selected preset (FluidSynth Mode)
- Added 4 Leds, 1 Red + 1 Green Leds on Rec and Mute/Solo Buttons:
  - Rec Button:
    - Yellow (Red+Green): When the Track is waiting to Record instantaneously (in case of Master Track 0) or when restarting the Loop
    - Red: When recording
  - Mute/Solo Button:
    - Green: When Track is Playing (not Muted)
    - Yellow: When Track is waiting the restarting of the Loop to Mute/UnMute or Solo/UnSolo
    - Red: Flashes when Loop is restarting
- Support for 10 tracks (originally only 4) and could be increased till the limits of resources/latency.
- Mute/Solo waits till the starting of the Master Track to execute it
- If a MIDI Capture Port is detected on Jack, launches FluidSynth
  - Loads the default FluidR3_GM.sf2 (can be changed)
  - Pressing MODEBUTTON changes to FluidSynth Mode and the Prev/Next Buttons changes the Preset Number of GM SoundFont.
  - Pressing again MODEBUTTON changes to Looper Mode and the output L+R of FluidSynth can be recorded on selected Track.

![imagen](https://github.com/user-attachments/assets/7e4a752f-1773-4dce-8de1-60d16994fe0f)

![imagen](https://github.com/user-attachments/assets/c0264a8e-3662-4eb9-855b-bd9bf15feecf)


