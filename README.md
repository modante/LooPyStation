# LooPyStation

16 Tracks Looper for Raspberry Pi with Infinite Overdubs, Mute, Solo, Undo, Clear, Volume functions and FluidSynth (a soundfont sample player) running at the same time, connected into looper and controlled with the footswitches.
To be used with any USB Sound Card and USB MIDI Keyboard (I use it with a Zoom H5 handy recorder and Evolution MK-461 MIDI Keyboard).

Inspired on the great Raspi Looper from RandomVertebrate https://github.com/RandomVertebrate/raspi-looper

![imagen](https://github.com/user-attachments/assets/7e4a752f-1773-4dce-8de1-60d16994fe0f)

### Features:
  - **16 Tracks** (configurable) that can be selected with the Prev and Next Buttons
  - 8-Segments display to show Track number, Bank/Preset of Fluidsynth and Session to import
  - Infinite **Overdubs** with **Undo**
  - 3 Modes for Undo
  - **Mute/UnMute** & **Solo/Unsolo** per track synced with the starting of loop
  - **Clear** of the selected track or all the tracks (when Clear is applied on track 0)
  - Button to change **Mode** from Looper (without dot) to FluidSynth control
  - **Volume** per track pressing long Prev / Next Buttons
  - The tracks can be **x times larger** than the Master Track (Loop 0)
  - Works with any **USB soundcard / MIDI Keyboard**
  - Export of **Audio Session** to 320kb mp3 file on ./recordings dir
  - Setup of some **settings.py** like selecting soundcard, buffers size, or overshooting
  - **Latency compensation** using latency.py
  - Sampler FluidSynth loads at boot with the first (alphabetically) soundfont file (.sf2) on ./sf2 dir. FluidSynth L+R outputs connected to Looper Input
  - Works with **Jack** which allows easy and powerfull configuration
  - NEW: Import / Export of the Initialized Tracks from / to wav files on ./sessions dir

### How to play with LooPyStation?
- Design for 6 Buttons:
  - **Mode Button:** Switches from "Looper Mode" to "FluidSynth Mode".
    - (0) Looper Mode: Prev / Next Buttons changes Track Number (press) or Volume (hold). Rec, Undo/Clear and Mute/Solo do the same functions in Modes 0 and 1
    - (1) FluidSynth Mode: Prev / Next Buttons changes Preset Number (press) or Bank Number (hold)
    - (2) Audio Session Recording / Session Export / Session Import:
      - Pressing Rec Button to start (synced with Master Track start) and again to end the recording
      - Holding Mute Button Exports all the initialized tracks to wav files on ./sessions
      - Holding Undo Button Imports the selected session (changes with Prev / Next Buttons)
  - **Rec Button:** (Modes 0 and 1)
    - Press to Record. Press again to Stop Recording (Looper and FluidSynth Mode)
    - If you want to stop and discard recording: Press Undo/Clear Button while recording
  - **Undo/Clear Button:** (Modes 0 and 1)
    - When Pressed:
      - When Recording: Stops recording and resets Track.
      - When Playing:
        - First Click: Undo the last recorded Overdub
        - Second Click: Undo the first recorded Overdub
        - Third Click: No Undo. Overdubs first and last recordings
    - When Held:
      - Clear selected Track, even if it is Recording.
      - If track 0 is selected, Erase and Reset all the Tracks of the Looper
  - **Mute/Solo Button:** (Modes 0 and 1)
    - When Pressed: Mute selected Track. Press again to UnMute (Looper Mode)
    - When Held: Solo selected Track. Hold again to UnSolo (Looper Mode)
  - **Prev Button:**
    - When Pressed: Jumps to the prev track (Looper Mode) / Decrease 1 preset number (Looper Mode)
    - When Held: Decrease 1 bank numbers (FluidSynth Mode) / Decrease Volume of selected Track (Looper Mode)
  - **Next Button:**
    - When Pressed: Jumps to the next track (Looper Mode) / Increase 1 preset number (Looper Mode)
    - When Held: Increase 1 bank numbers (FluidSynth Mode) / Increase Volume of selected Track (Looper Mode)
- **7 segments Display**
  - Looper Mode: Displays the Track number (0-9) or the volume of the selected Track (0-9)
  - FluidSynth Mode: Displays the last digit of selected Preset or the selected Bank. Always a "." (decimal point) is on.
- **4 Leds**, 1 Red + 1 Green Leds on Rec and Mute/Solo Buttons:
  - Rec Button:
    - Yellow (Red+Green): When the Track is waiting to Record instantaneously (in case of Master Track 0) or when restarting the Loop
    - Red: When recording
  - Mute/Solo Button:
    - Green: When Track is Playing (not Muted)
    - Yellow: When Track is waiting the restarting of the Loop to Mute/UnMute or Solo/UnSolo
    - Red: Flashes when Loop is restarting
- If a MIDI Capture Port is detected on Jack at boot, loads **FluidSynth**
  - The output L+R of FluidSynth is connected to Input port of Looper in order to be recorded on selected Track.
  - In the first change to FluidSynth Mode, loads the first (alphabetically) sf2 file on ./sf2 dir
  - Pressing MODEBUTTON changes to FluidSynth Mode and the Prev/Next Buttons changes the Preset Number of SoundFont.
  - Pressing again MODEBUTTON changes to Looper Mode.

Works with **Jack** which allows an easy and powerfull configuration
  - All the physical inputs of soundcard (Jack capture ports) are connected to Input port of Looper
  - The Output Port of the Looper is connected with all the physical outputs of soundcard (Jack Playback ports)

DEMOS: First sessions of Ephemeral Songs

https://audio.anartist.org/library/albums/5915

https://video.anartist.org/w/d7WA2y3ncZWzXvwGi6GirG

https://video.anartist.org/w/3QC7NDNaG3MpVhjX2YGmMk

![photo_2024-11-26_11-53-39](https://github.com/user-attachments/assets/a4f5ce32-0bb3-43d6-b565-174189d2d8bf)

![photo_2024-11-26_11-53-42](https://github.com/user-attachments/assets/7ead2b8a-ff21-42fd-8898-1221478dfb37)

![photo_2024-11-26_11-53-45](https://github.com/user-attachments/assets/f1575d83-0f9d-427f-a63f-fe5e53f3e4b6)

### How to run it?

- Just change to the main dir where files are stored.
- Make _./LooPyStation.sh_ executable: **chmod +x ./LooPyStation.sh**
- Adjust settings running: **python settings.py**
- Run the LooPyStation: **./LooPyStation.sh**

-----

ToDo:
- Design a web controller for using with an smartphone (or whatever)
- Document help, functions, switches, connections, wiring, ...
- Make a video to explain how it works

pd: Sorry for the code but I am newby like programmer (1st time using python). Any advice will be welcome :-D
Thank you for your understanding.
