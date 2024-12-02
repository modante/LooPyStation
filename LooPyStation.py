import jack
import numpy as np
import time
import os, sys
from gpiozero import LED, Button, LEDCharDisplay
from time import sleep
from pydub import AudioSegment
import io
from datetime import datetime
sys.path.append('./pyfluidsynth')
import fluidsynth

print('\n', '--- Starting RaspiLoopStation... ---','\n')

# Get configuration (audio settings etc.) from file
settings_file = open('./settings.prt', 'r')
parameters = settings_file.readlines()
settings_file.close()

# Variables Initialization
RATE = int(parameters[0])  # Sample rate
CHUNK = int(parameters[1])  # Buffer size
latency_in_milliseconds = int(parameters[2])
LATENCY = round((latency_in_milliseconds/1000) * (RATE/CHUNK))  # Latency in buffers
INDEVICE = int(parameters[3])  # Index of input device
OUTDEVICE = int(parameters[4])  # Index of output device
overshoot_in_milliseconds = int(parameters[5])  # Allowance in milliseconds for pressing 'stop recording' late
OVERSHOOT = round((overshoot_in_milliseconds/1000) * (RATE/CHUNK))  # Allowance in buffers
MAXLENGTH = int(12582912 / CHUNK)  # 96mb of audio in total
LENGTH = 0  # Length of the first recording of or Master Track (0). All subsequent recordings quantized to a multiple of this.
number_of_tracks = 10
LoopNumber = 0  # Pointer to the selected Loop/Track
setup_is_recording = False  # Set to True when track 1 recording button is first pressed
setup_donerecording = False  # Set to true when first track 1 recording is done
Mode = 3
Preset = 0
Bank = 0
sfid = 0
OrigVolume = 7
DispData = ""
dispcount = 0
first_run = 0
first_synth = 0
ti_mer = int(RATE / CHUNK)
func_name = ""
rec_file = False

rec_was_held = False  # Flags for Buttons Held
play_was_held = False
clear_was_held = False
prev_was_held = False
next_was_held = False
mode_was_held = False

# Buttons, Leds and 8-Segments Display
debounce_length = 0.05  # Length in seconds of button debounce period
display = LEDCharDisplay(11, 25, 9, 10, 24, 22, 23, dp=27)
PLAYLEDR = (LED(26, active_high=False))
PLAYLEDG = (LED(20, active_high=False))
RECLEDR = (LED(0, active_high=False))
RECLEDG = (LED(1, active_high=False))
RECBUTTON = (Button(18, bounce_time=debounce_length))
RECBUTTON.hold_time=0.5
PLAYBUTTON = (Button(15, bounce_time=debounce_length))
PLAYBUTTON.hold_time = 0.5
CLEARBUTTON = (Button(17, bounce_time=debounce_length))
CLEARBUTTON.hold_time = 0.5
PREVBUTTON = (Button(5, bounce_time=debounce_length))
PREVBUTTON.hold_time = 0.5
NEXTBUTTON = (Button(12, bounce_time=debounce_length))
NEXTBUTTON.hold_time = 0.5
MODEBUTTON = (Button(6, bounce_time=debounce_length))
MODEBUTTON.hold_time = 2.5

play_buffer = np.zeros([CHUNK], dtype=np.int16)  #Buffer to hold mixed audio from all tracks
silence = np.zeros([CHUNK], dtype=np.int16)  #A buffer containing silence
current_rec_buffer = np.zeros([CHUNK], dtype=np.int16)  # Buffer to hold in_data
output_volume = np.float32(1.0)  # Mixed output (sum of audio from tracks) is multiplied by output_volume before being played. Not used by now
down_ramp = np.linspace(1, 0, CHUNK)  # Multiplying by up_ramp and down_ramp gives fade-in and fade-out
up_ramp = np.linspace(0, 1, CHUNK)

# Get a list of all files in the directory ./sf2
sf2_dir = "./sf2"
sf2_list = sorted([f for f in os.listdir(sf2_dir) if os.path.isfile(os.path.join(sf2_dir, f))])  # Put all the detected files alphabetically on an array

# ------- END of Variables and Flags ------

print('Rate: ' + str(RATE) + ' / CHUNK: ', str(CHUNK), '\n')
print('Latency correction (buffers): ', str(LATENCY), '\n')

# ----------- USER INTERFACE --------------
# Behavior when MODEBUTTON is pressed
def Change_Mode():
    global Mode, mode_was_held, audio_buffer, rec_file
    if not mode_was_held:
        if Mode == 3:
            Mode = 0
        elif Mode == 0:
            Mode = 1
        elif Mode == 1:
            Mode = 2
        elif Mode == 2:
            Mode = 0
        print('----------= Changed to Mode=', str(Mode), '\n')
    mode_was_held = False

# Behavior when MODEBUTTON is held
def restart_program():
    display.value = " ."
    TurningOff()
    print("Restarting App...")
    python = sys.executable  # Gets the actual python interpreter
    os.execv(python, [python] + sys.argv)

# Behavior when PREVBUTTON is pressed
def Prev_Button_Press():
    global LoopNumber, Preset, prev_was_held
    if not prev_was_held:
        if Mode == 0 and setup_donerecording:
            if LoopNumber == 0:
                LoopNumber = number_of_tracks - 1
            else:
                LoopNumber -= 1
            print('-= Prev Loop =---> ', LoopNumber,'\n')
            debug()
        elif Mode == 1:
            if Preset >= 1:
                Preset -= 1
                ChangePreset()
    prev_was_held = False

# Behavior when PREVBUTTON is held
def Prev_Button_Held():
    global Bank, prev_was_held, DispData
    if Mode == 0 and setup_donerecording and loops[LoopNumber].initialized:
        if loops[LoopNumber].volume >= 1:
            loops[LoopNumber].volume -= 1
            print('Volume Decreased=', loops[LoopNumber].volume,'\n')
            DispData = str(loops[LoopNumber].volume)[-1]
            debug()
    elif Mode == 1:
        if Bank >= 1:
            Bank -= 1
            ChangeBank()
    prev_was_held = True

# Behavior when NEXTBUTTON is pressed
def Next_Button_Press():
    global LoopNumber, Preset, next_was_held
    if not next_was_held:
        if Mode == 0 and setup_donerecording:
            if LoopNumber == number_of_tracks - 1:
                LoopNumber = 0
            else:
                LoopNumber = LoopNumber+1
            print('-= Next Loop =---> ', LoopNumber,'\n')
            debug()
        if Mode == 1:
            if Preset < 125:
                Preset += 1
                ChangePreset()
    next_was_held = False

# Behavior when NEXTBUTTON is held
def Next_Button_Held():
    global Bank, next_was_held, DispData
    if Mode == 0 and setup_donerecording and loops[LoopNumber].initialized:
        if loops[LoopNumber].volume <= 9:
            loops[LoopNumber].volume += 1
            print('Volume Increased=', loops[LoopNumber].volume,'\n')
            DispData = str(loops[LoopNumber].volume)[-1]
            debug()
    elif Mode == 1:
        if Bank < len(sf2_list) - 1:
            Bank += 1
            ChangeBank()
    next_was_held = True

# Behavior when RECBUTTON is pressed
def Rec_Button_Pressed():
    if Mode == 0 or Mode == 1:
        loops[LoopNumber].set_recording()
    elif Mode == 2:
        global audio_buffer, rec_file
        if not rec_file:  # If Flag to record on disk is False
            audio_buffer = io.BytesIO()  # Creates Audio Buffer to be recorded on Disk
            rec_file = True  # Flag to Start Recording on disk by the loop_callback
            print("---= Recording to file =---")
        else:
            audio_buffer.seek(0)
            audio_segment = AudioSegment.from_raw(audio_buffer, sample_width=2, frame_rate=48000, channels=1)
            date_time_now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            output_file_name = f"./recordings/LooPyStation_output_{date_time_now}.mp3"
            audio_segment.export(output_file_name, format="mp3", bitrate="320k")  # Write file to disk
            print("---= MP3 File saved like: ", output_file_name)
            rec_file = False  # Flag to Stop Recording on disk by the loop_callback

# Behavior when MUTEBUTTON is pressed
def Mute_Button_Pressed():
    if Mode == 0 or Mode == 1:
        global play_was_held
        if setup_donerecording:
            if not play_was_held:
                loops[LoopNumber].toggle_mute()
            play_was_held = False

# Behavior when MUTEBUTTON is held
def Mute_Button_Held():
    if Mode == 0 or Mode == 1:
        global play_was_held
        if setup_donerecording:
            play_was_held = True
            loops[LoopNumber].toggle_solo()

# Behavior when CLEARBUTTON is pressed
def Clear_Button_Pressed():
    if Mode == 0 or Mode == 1:
        global clear_was_held
        if not clear_was_held:
            loops[LoopNumber].undo()
        clear_was_held = False

# Behavior when CLEARBUTTON is held
def Clear_Button_Held():
    if Mode == 0 or Mode == 1:
        global clear_was_held
        clear_was_held = True
        loops[LoopNumber].clear()

#------------------------------------------------------------------------------------------------

# Turns Off the Looper and exits
def TurningOff():
    if first_synth == 1:
        fs.delete()
        print("Closing FluidSynth")
    client.deactivate()
    print("Deactivating JACK Client")
    PowerOffLeds()
    print('Done...')

# Fade_in() applies fade-in to a buffer
def fade_in(buffer):
    np.multiply(buffer, up_ramp, out=buffer, casting='unsafe')

# Fade_out() applies fade-out to a buffer
def fade_out(buffer):
    np.multiply(buffer, down_ramp, out=buffer, casting='unsafe')

# Converts pcm2float array
def pcm2float(sig, dtype='float32'):
    sig = np.asarray(sig)
    if sig.dtype.kind not in 'iu':
        raise TypeError("'sig' must be an array of integers")
    dtype = np.dtype(dtype)
    if dtype.kind != 'f':
        raise TypeError("'dtype' must be a floating point type")

    i = np.iinfo(sig.dtype)
    abs_max = 2 ** (i.bits - 1)
    offset = i.min + abs_max
    return (sig.astype(dtype) - offset) / abs_max

# Converts float2pcm array
def float2pcm(sig, dtype='int16'):
    sig = np.asarray(sig)
    if sig.dtype.kind != 'f':
        raise TypeError("'sig' must be a float array")
    dtype = np.dtype(dtype)
    if dtype.kind not in 'iu':
        raise TypeError("'dtype' must be an integer type")

    i = np.iinfo(dtype)
    abs_max = 2 ** (i.bits - 1)
    offset = i.min + abs_max
    return (sig * abs_max + offset).clip(i.min, i.max).astype(dtype)

# Turn-Off all the Leds
def PowerOffLeds():
    RECLEDR.off()
    RECLEDG.off()
    PLAYLEDR.off()
    PLAYLEDG.off()

# Debug prints info on stdout
def debug():
    print('   |init |rec  |wait |play |waiP |waiM |Solo |Vol\t|ReaP\t|WriP\t|Leng')
    for i in range(9):
        print(i, ' |',
              int(loops[i].initialized), '  |',
              int(loops[i].is_recording), '  |',
              int(loops[i].is_waiting_rec), '  |',
              int(loops[i].is_playing), '  |',
              int(loops[i].is_waiting_play), '  |',
              int(loops[i].is_waiting_mute), '  |',
              int(loops[i].is_solo), '  |',
              int(loops[i].volume), '\t|',
              int(loops[i].readp), '\t|',
              int(loops[i].writep), '\t|',
              int(loops[i].length))
    print('setup_donerecording=', setup_donerecording, ' setup_is_recording=', setup_is_recording)
    print('length=', loops[LoopNumber].length, 'LENGTH=', LENGTH, 'length_factor=', loops[LoopNumber].length_factor,'\n')
    print('|', ' '*7,'|',' '*7,'|', ' '*7,'|',' '*7,'|')

# Checks which loops are recording/playing/waiting and lights up LEDs and Display accordingly
def show_status():
    global DispData, dispcount
    # If Prev / Next Buttons are Pressed, 8-seg. Display shows selected LoopNumber / Preset (depends of Mode)
    if DispData == "":
        if Mode == 0:
            display.value = str(LoopNumber)[-1]
        elif Mode == 1:
            display.value = str(Preset)[-1] + "."
        elif Mode == 2:
            display.value = " ."
    else:  # Else, if Prev / Next Buttons are Held, display shows Volume / Bank (depends of Mode)
        if dispcount <= 4:
            display.value = DispData
            dispcount += 1
        else:
            dispcount = 0
            DispData = ""

    # Leds Status for Rec Button ---------------------------
    if Mode == 0 or Mode == 1:
        if loops[LoopNumber].is_recording:
            RECLEDR.on()
            RECLEDG.off()
        elif loops[LoopNumber].is_waiting_rec:
            RECLEDR.on()
            RECLEDG.on()
        elif setup_donerecording or not loops[LoopNumber].is_recording:
            RECLEDR.off()
            RECLEDG.off()
    elif Mode == 2:
        if rec_file:
            RECLEDR.on()
            RECLEDG.off()
        else:
            RECLEDR.off()
            RECLEDG.off()

    # Leds Status for Play Button ---------------------------
    if loops[LoopNumber].is_waiting_play or loops[LoopNumber].is_waiting_mute:
        PLAYLEDR.on()
        PLAYLEDG.on()
    elif loops[LoopNumber].is_playing:
        PLAYLEDR.off()
        PLAYLEDG.on()
    else:
        PLAYLEDR.off()
        PLAYLEDG.off()

# Changes the FluidSynth Preset
def ChangePreset():
    fs.program_select(0, sfid, 0, Preset)
    print('----- Bank: ', str(Bank), ' - ', str(sf2_list[Bank]),' / Preset: ',  ' - ', str(Preset), '\n')

# Changes the FluidSynth Bank
def ChangeBank():
    global DispData, sfid
    DispData = str(Bank)[-1] + "."
    fs.sfunload(sfid)
    sfid = fs.sfload("./sf2/" + str(sf2_list[Bank]))
    fs.program_select(0, sfid, 0, 0)
    print('----- Bank: ', str(Bank), ' - ', str(sf2_list[Bank]),' / Preset: ',  ' - ', str(Preset), '\n')

# Assign all the Capture ports to Looper Input
def all_captures_to_input():
    capture = client.get_ports(is_audio=True, is_physical=True, is_output=True)
    print(capture, '\n')
    if not capture:
        raise RuntimeError("No physical capture ports")
    for src in capture:
        client.connect(src, input_port)

# Assign the Looper Output to all the Playback ports
def output_to_all_playbacks():
    playback = client.get_ports(is_audio=True, is_physical=True, is_input=True)
    print(playback, '\n')
    if not playback:
        raise RuntimeError("No physical playback ports")
    for dest in playback:
        client.connect(output_port, dest)

# Assign all the Capture ports to Looper Input
def connect_fluidsynth():
    client.connect('system:midi_capture_1', 'fluidsynth:midi_00')
    client.connect('fluidsynth:left', 'RaspiLoopStation:input_1')
    client.connect('fluidsynth:right', 'RaspiLoopStation:input_1')

# If Jack Server is already running, returns True, else returns False
def is_jack_server_running():
    try:
        # Try to create a Cliente without activating
        client = jack.Client("CheckJackServer", no_start_server=True)
        client.close()  # Close cliente inmediately
        return True
    except jack.JackError: # If JackError happens, ther server is NOT active
        return False

# Defining functions of all the buttons during jam session...
PREVBUTTON.when_released = Prev_Button_Press
PREVBUTTON.when_held = Prev_Button_Held
NEXTBUTTON.when_released = Next_Button_Press
NEXTBUTTON.when_held = Next_Button_Held
MODEBUTTON.when_released = Change_Mode
MODEBUTTON.when_held = restart_program
RECBUTTON.when_pressed = Rec_Button_Pressed
CLEARBUTTON.when_released = Clear_Button_Pressed
CLEARBUTTON.when_held = Clear_Button_Held
PLAYBUTTON.when_released = Mute_Button_Pressed
PLAYBUTTON.when_held = Mute_Button_Held

# Detects if the SoundCard defined on settings is connected
print("Detecting SoundCard Number:",str(INDEVICE))
display.value = " ."  # Shows a decimal point on 8-seg Display
while Mode == 3:  # Waits in an infinite loop till SoundCard is connected
    try:
        with open("/proc/asound/cards", "r") as f:
            content = f.read().strip()
        # Check if " INDEVICE [" is in the list of sound cards
        if (" "+str(INDEVICE)+" [") in content:
            Mode = 0
            print("Sound card number:",str(INDEVICE)," detected\n")
        else:
            print("Sound card number:",str(INDEVICE)," NOT detected", end='\r')
            time.sleep(0.5)
    except FileNotFoundError:
        print("This system does not have /proc/asound/cards. Not a Linux system?")

# Test if jack server is running and if not, run it
if is_jack_server_running():
    Mode = 0
    print("----- Jack Server is already running",'\n')
else:
    os.system ("sudo -H -u raspi dbus-launch jackd -dalsa -r"+str(RATE)+" -p"+str(CHUNK)+" -n2 -Xraw -D -Chw:"+str(INDEVICE)+" -Phw:"+str(OUTDEVICE)+" &")
    print("----- Jack Server is NOT running. Starting it!",'\n')
    for i in range(2):
        if i % 2 == 0:
            display.value = " "
        else:
            display.value = " ."
        time.sleep(0.5)
    print("----- Jack Server is running",'\n')

# Initializing JACK Client
client = jack.Client("RaspiLoopStation")
print('----- Jack Client RaspiLoopStation Initialized','\n')

class audioloop:
    def __init__(self):
        self.initialized = False
        self.length_factor = 1
        self.length = 0
        self.readp = 0
        self.writep = 0
        self.is_recording = False
        self.is_playing = False
        self.is_waiting_rec = False
        self.is_waiting_play = False
        self.is_waiting_mute = False
        self.is_solo = False
        self.volume = OrigVolume
        self.pointer_last_buffer_recorded = 0 #index of last buffer added
        self.preceding_buffer = np.zeros([CHUNK], dtype=np.int16)
        self.main_audio = np.zeros([MAXLENGTH, CHUNK], dtype=np.int16)  # self.main_audio contain main audio data in arrays of CHUNKs.
        self.dub_audio = np.zeros([MAXLENGTH, CHUNK], dtype=np.int16)

    # increment_pointers() increments pointers and, when restarting while recording
    def increment_pointers(self):
        if self.readp == self.length - 1:
            self.readp = 0
            print(' '*60, end='\r')
        else:
            self.readp += 1
        progress = (loops[0].readp / (loops[0].length + 1))*41
        self.writep = (self.writep + 1) % self.length
        print('#'*int(progress), end='\r')

    # read_buffer() reads and returns a buffer of audio from the loop
    def read_buffer(self):
        # Turns On 0,1s the Red Led of PLAYBUTTON to mark the starting of Master Loop
        if loops[0].is_restarting():
            PLAYLEDR.on()
            PLAYLEDG.off()

        # If a Track is is_waiting_rec, put it to Rec when reaches the end of length
        if self.is_waiting_rec:
            if self.initialized:
                if self.writep == self.length - 1:
                    self.is_recording = True
                    self.is_waiting_rec = False
                    self.is_waiting_mute = True
                    print('-=Start Recording Track ', LoopNumber, '\n')
            elif loops[0].writep == loops[0].length - 1:
                self.is_recording = True
                self.is_waiting_rec = False
                print('-=Start Recording Track ', LoopNumber, '\n')

        # If a Track is not initialized, exit and returns silence
        if not self.initialized:
            return(silence)

        # If the Track is initialized:
        # Control of UnMute
        if self.is_waiting_play and loops[0].writep == loops[0].length - 1:
            self.is_waiting_play = False
            self.is_playing = True

        # Control of Mute
        if self.is_waiting_mute and loops[0].writep == loops[0].length - 1:
            self.is_waiting_mute = False
            self.is_playing = False

        # If a Track is Muted or waiting_play, increment_pointers and exit with silence
        if not self.is_playing or self.is_waiting_play:
            self.increment_pointers()
            return(silence)

        # If not any of the cases, increment_pointers and return the buffer addressed by readp
        tmp = self.readp
        self.increment_pointers()
        return(self.main_audio[tmp, :])

    # write_buffer() appends a new buffer unless loop is filled to MAXLENGTH
    # expected to be called only before initialization
    def write_buffers(self, data):
        global LENGTH
        if self.initialized:
            if self.writep < self.length - 1:
                self.dub_audio[self.writep, :] = self.main_audio[self.writep, :]
                self.main_audio[self.writep, :] = np.copy(data)  # Add to main_audio the buffer entering through Jack
            elif self.writep == self.length - 1:
                self.is_recording = False
                self.is_waiting_rec = False
                self.is_playing = True
        else:
            if self.length >= (MAXLENGTH - 1):
                self.length = 0
                print('Loop Full')
                return
            self.main_audio[self.length, :] = np.copy(data)  # Add to main_audio the buffer entering through Jack
            self.length = self.length + 1  # Increase the length of the loop
            if not setup_donerecording:
                LENGTH += 1

    #set_recording() either starts or stops recording
    #   if uninitialized and recording, stop recording (appending) and initialize
    #   if initialized and not recording, set as "waiting to record"
    def set_recording(self):
        global setup_is_recording, setup_donerecording
        print('----- set_recording called for Track', LoopNumber,'\n')
        already_recording = False

        #if chosen track is currently recording, flag it
        if self.is_recording:
            already_recording = True
            # turn off recording
            if not self.initialized:
                self.initialize()
                self.is_playing = True
                self.is_recording = False
                self.is_waiting_rec = False
                if LoopNumber == 0 and not setup_donerecording:
                    setup_is_recording = False
                    setup_donerecording = True
                    print('---Master Track Recorded---','\n')

        #unless flagged, schedule recording. If chosen track was recording, then stop recording
        if not already_recording:
            if self.is_waiting_rec and setup_donerecording:
                self.is_waiting_rec = False
                return
            if LoopNumber == 0 and not setup_donerecording:
                self.is_recording = True
                setup_is_recording = True
            else:
                self.is_waiting_rec = True
        debug()

    #Restarting is True only when readp==0 and the loop is initialized, and is only checked after recording the Master Loop (0)
    def is_restarting(self):
        if not self.initialized:
            return False
        if self.readp == 0:
            return True
        return False

    #initialize() raises self.length to closest integer multiple of LENGTH and initializes read and write pointers
    def initialize(self): #It initializes when recording of loop stops. It de-initializes after Clearing.
        if not self.initialized:
            self.writep = self.length - 1
            self.length_factor = (int((self.length - OVERSHOOT) / LENGTH) + 1)
            self.length = self.length_factor * LENGTH
            '''
            #crossfade
            self.pointer_last_buffer_recorded = self.writep
            fade_out(self.main_audio[self.pointer_last_buffer_recorded]) #fade out the last recorded buffer
            preceding_buffer_copy = np.copy(self.preceding_buffer)
            fade_in(preceding_buffer_copy)
            self.main_audio[self.length - 1, :] += preceding_buffer_copy[:]
            '''
            #audio should be written ahead of where it is being read from, to compensate for input+output latency
            self.readp = (self.writep + LATENCY) % self.length
            self.initialized = True
            self.is_playing = True
            print('     length ' + str(self.length),'\n')
            print('     last buffer recorded ' + str(self.pointer_last_buffer_recorded),'\n')
            print('-----= Initialized =-----','\n')
        debug()

    def toggle_mute(self):
        print('-=Toggle Mute=-','\n')
        if self.initialized:
            if self.is_playing:
                if not self.is_waiting_mute:
                    self.is_waiting_mute = True
                else:
                    self.is_waiting_mute = False
                print('-------------Mute=-', '\n')
            else:
                if not self.is_waiting_play:
                    self.is_waiting_play = True
                else:
                    self.is_waiting_play = False
                self.is_solo = False
                print('-------------UnMute=-', '\n')
            debug()

    def toggle_solo(self):
        print('-=Toggle Solo=-','\n')
        if self.initialized:
            if not self.is_solo:
                for i in range(number_of_tracks):
                    if i != LoopNumber and loops[i].initialized and not loops[i].is_solo and loops[i].is_playing:
                        loops[i].is_waiting_mute = True
                self.is_solo = True
                print('-------------Solo')
            else:
                for i in range (number_of_tracks):
                    if i != LoopNumber and loops[i].initialized:
                        loops[i].is_waiting_play = True
                        loops[i].is_solo = False
                self.is_solo = False
                print('-------------UnSolo')
            debug()

    def undo(self):
        global LENGTH
        if self.is_recording:
            if not self.initialized:
                self.clear_track()
                if LoopNumber == 0:
                    LENGTH = 0
                return
        else:
            if self.is_playing:
                self.dub_audio, self.main_audio = self.main_audio, self.dub_audio
                print('-=Undo=-','\n')
        debug()

    #clear() clears the loop so that a new loop of the same or a different length can be recorded on the track
    def clear(self):
        global setup_donerecording, setup_is_recording, LENGTH
        if LoopNumber == 0:
            for loop in loops:
                loop.__init__()
            setup_donerecording = False
            setup_is_recording = False
            LENGTH = 0
            print('-=Cleared ALL=-','\n')
        else:
            self.clear_track()
        debug()

    def clear_track(self):
        self.__init__()
        print('-=Clear Track=-', '\n')

#defining ten audio loops. loops[0] is the master loop.
loops = [audioloop() for _ in range(number_of_tracks)]

# Setup: First Recording
if not setup_donerecording:  # If setup is not done i.e. if the master loop hasn't been recorded to yet
    loops[0].is_waiting_rec = 1

# Callback de procesamiento de audio
@client.set_process_callback
def looping_callback(frames):
    global play_buffer, current_rec_buffer
    global LENGTH, ti_mer, first_run

    if first_run < 0.5 * RATE / CHUNK:  # Little pause before starting the loopback
        first_run += 1
        print(first_run, end='\r')
        return

    # Read input buffer from JACK
    current_rec_buffer = float2pcm(input_port.get_array())  # Capture current input jack buffer after converting Float2PCM

    # If a loop is recording, check initialization and accordingly append
    for loop in loops:
        if loop.is_recording:
            print('--------------------------------------------------=Recording=-', end='\r')
            loop.write_buffers(current_rec_buffer)

    # Add to play_buffer the sum of each audio signal times the each own volume
    play_buffer[:] = np.multiply((
        loops[0].read_buffer().astype(np.int32)*(loops[0].volume/10)**2+
        loops[1].read_buffer().astype(np.int32)*(loops[1].volume/10)**2+
        loops[2].read_buffer().astype(np.int32)*(loops[2].volume/10)**2+
        loops[3].read_buffer().astype(np.int32)*(loops[3].volume/10)**2+
        loops[4].read_buffer().astype(np.int32)*(loops[4].volume/10)**2+
        loops[5].read_buffer().astype(np.int32)*(loops[5].volume/10)**2+
        loops[6].read_buffer().astype(np.int32)*(loops[6].volume/10)**2+
        loops[7].read_buffer().astype(np.int32)*(loops[7].volume/10)**2+
        loops[8].read_buffer().astype(np.int32)*(loops[8].volume/10)**2+
        loops[9].read_buffer().astype(np.int32)*(loops[9].volume/10)**2
    ), output_volume, out=None, casting='unsafe').astype(np.int16)

    if rec_file:
        audio_buffer.write(play_buffer[:].tobytes())

    # Play mixed audio and move on to next iteration
    output_port.get_array()[:] = pcm2float(play_buffer[:])

@client.set_shutdown_callback
def shutdown(status, reason):
    print("JACK shutdown:", reason, status)

with client:
    try:
        # Getting Jack buffer size
        buffer_size = client.blocksize
        print("Tamaño del buffer JACK (entrada y salida):", buffer_size, '\n')

        # Registering Ins/Outs Ports
        input_port = client.inports.register("input_1")
        print('----- Jack Client In Port Registered-----\n', str(input_port), '\n')

        output_port = client.outports.register("output_1")
        print('----- Jack Client Out Port Registered-----\n', str(output_port),'\n')

        all_captures_to_input()
        output_to_all_playbacks()

        # Get MIDI Capture Ports
        outMIDIports = client.get_ports(is_midi=True, is_output=True)
        print("MIDI Capture Ports:",'\n')
        print(outMIDIports,'\n')

        # Get MIDI Playback Ports
        inMIDIports = client.get_ports(is_midi=True, is_input=True)
        print("MIDI Playback Ports:",'\n')
        print(inMIDIports,'\n')

        # If a MIDI Capture Port exists, Load FluidSynth
        target_port = 'system:midi_capture_1'
        if True:  # any(port.name == target_port for port in outMIDIports):
            fs = fluidsynth.Synth()  # Loads FluidSynth but remains inactive
            fs.setting("audio.driver", 'jack')
            fs.setting("midi.driver", 'jack')
            fs.setting("synth.sample-rate", float(RATE))
            fs.setting("audio.jack.autoconnect", True)
            fs.setting("midi.autoconnect", False)
            fs.setting("synth.gain", 0.9)
            fs.setting("synth.cpu-cores", 4)
            print('---FluidSynth Jack Loading---', '\n')
            # Start FluidSynth
            fs.start()
            connect_fluidsynth()
            time.sleep(0.5)
            # Loads the first soundfont of the list
            if len(sf2_list) > 0:
                sfid = fs.sfload("./sf2/" + sf2_list[0])
                fs.program_select(0, sfid, 0, 0)
            print('----- Bank: ', str(Bank), ' - ', str(sf2_list[Bank]),' / Preset: ',  ' - ', str(Preset), '\n')

        #then we turn on Green and Red lights of REC Button to indicate that looper is ready to start looping
        print("Jack Client Active. Press Ctrl+C to Stop.",'\n')
        debug()
        #once all LEDs are on, we wait for the master loop record button to be pressed
        print('---Waiting for Record Button---','\n')

        while True:
            show_status()
            time.sleep(0.1)
            pass  # Keep Client executing

    except KeyboardInterrupt:
        TurningOff()
