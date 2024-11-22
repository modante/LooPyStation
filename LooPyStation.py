import jack
import numpy as np
import time
import os, sys
from gpiozero import LED, Button, LEDCharDisplay
from time import sleep

print('Starting RaspiLoopStation...','\n')

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
LoopNumber = 0  # Pointer to the selected Loop/Track
setup_is_recording = False  # Set to True when track 1 recording button is first pressed
setup_donerecording = False  # Set to true when first track 1 recording is done
Mode = 3
Preset = 0
Bank = 0
BankCounter = 1
First_Run = 0
OrigVolume = 7
DispData = ""
dispcount = 0

# Flags for Buttons
rec_was_held = False
play_was_held = False
clear_was_held = False
prev_was_held = False
next_was_held = False
mode_was_held = False

# Mixed output (sum of audio from tracks) is multiplied by output_volume before being played. Not used by now
output_volume = np.float32(1.0)
# Multiplying by up_ramp and down_ramp gives fade-in and fade-out
down_ramp = np.linspace(1, 0, CHUNK)
up_ramp = np.linspace(0, 1, CHUNK)

# Get a list of all files in the directory ./sf2
sf2_dir = "./sf2"
sf2_list = sorted([f for f in os.listdir(sf2_dir) if os.path.isfile(os.path.join(sf2_dir, f))])  # Put all the detected files alphabetically on an array
# ------- END of Variables and Flags ------

print('Rate: ' + str(RATE) + ' / CHUNK: ', str(CHUNK), '\n')
print('Latency correction (buffers): ', str(LATENCY), '\n')

# Buttons, Leds and 8-Segments Display
debounce_length = 0.05  # Length in seconds of button debounce period
display = LEDCharDisplay(11, 25, 9, 10, 24, 22, 23, dp=27)
PLAYLEDR = (LED(26, active_high=False))
PLAYLEDG = (LED(20, active_high=False))
RECLEDR = (LED(0, active_high=False))
RECLEDG = (LED(1, active_high=False))
RECBUTTON = (Button(18, bounce_time=debounce_length))
PLAYBUTTON = (Button(15, bounce_time=debounce_length))
CLEARBUTTON = (Button(17, bounce_time=debounce_length))
PREVBUTTON = (Button(5, bounce_time=debounce_length))
NEXTBUTTON = (Button(12, bounce_time=debounce_length))
MODEBUTTON = (Button(6, bounce_time=debounce_length))

RECBUTTON.hold_time=0.5
PLAYBUTTON.hold_time = 0.5
CLEARBUTTON.hold_time = 0.5
PREVBUTTON.hold_time = 0.5
NEXTBUTTON.hold_time = 0.5
MODEBUTTON.hold_time = 3

# Turns Off the Looper and exits
def TurningOff():
    os.system("sudo -H -u raspi killall fluidsynth")
    print("Closing FluidSynth")
    time.sleep(1)
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

# Behavior when MODEBUTTON is pressed
def Change_Mode():
    global Mode, mode_was_held
    if not mode_was_held:
        if Mode == 3:
            Mode = 0
        elif Mode == 0:
            Mode = 1
            PowerOffLeds()
            display.value=((str(Bank))[-1]+".")
            print('----- Bank: ', str(Bank), ' - ', str(sf2_list[Bank]),' / Preset: ',  ' - ', str(Preset), '\n')
        elif Mode == 1:
            Mode = 0
        print('----------= Changed to Mode=', str(Mode),'\n')
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
                LoopNumber = 9
            else:
                LoopNumber -= 1
            print('-= Prev Loop =---> ', LoopNumber,'\n')
        if Mode == 1:
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
            DispData = str(loops[LoopNumber].volume)
            debug()
    if Mode == 1:
        if Bank >= 1:
            Bank -= 1
            ChangeBank()
    prev_was_held = True

# Behavior when NEXTBUTTON is pressed
def Next_Button_Press():
    global LoopNumber, Preset, next_was_held
    if not next_was_held:
        if Mode == 0 and setup_donerecording:
            if LoopNumber == 9:
                LoopNumber = 0
            else:
                LoopNumber = LoopNumber+1
            print('-= Next Loop =---> ', LoopNumber,'\n')
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
            DispData = str(loops[LoopNumber].volume)
            debug()
    if Mode == 1:
        if Bank < len(sf2_list) - 1:
            Bank += 1
            ChangeBank()
    next_was_held = True

# Behavior when RECBUTTON is pressed
def Rec_Button_Pressed():
    loops[LoopNumber].set_recording()

# Behavior when MUTEBUTTON is pressed
def Mute_Button_Pressed():
    global play_was_held
    if setup_donerecording:
        if not play_was_held:
            loops[LoopNumber].toggle_mute()
        play_was_held = False

# Behavior when MUTEBUTTON is held
def Mute_Button_Held():
    global play_was_held
    if setup_donerecording:
        play_was_held = True
        loops[LoopNumber].toggle_solo()

# Behavior when CLEARBUTTON is pressed
def Clear_Button_Pressed():
    global clear_was_held
    if not clear_was_held:
        loops[LoopNumber].undo()
    clear_was_held = False

# Behavior when CLEARBUTTON is held
def Clear_Button_Held():
    global clear_was_held
    clear_was_held = True
    loops[LoopNumber].clear()

# Changes the FluidSynth Preset
def ChangePreset():
    txt = "echo 'prog 0 "+str(Preset)+"' > /dev/tcp/localhost/9988"
    write2cons(txt)
    time.sleep(0.1)
    print('----- Bank: ', str(Bank), ' - ', str(sf2_list[Bank]),' / Preset: ',  ' - ', str(Preset), '\n')

# Changes the FluidSynth Bank
def ChangeBank():
    global BankCounter, Preset, DispData
    DispData = str(Bank)[-1] + "."
    txt = "echo 'unload "+str(BankCounter)+"' > /dev/tcp/localhost/9988"
    write2cons(txt)
    time.sleep(0.1)
    txt = "echo 'load ./sf2/"+str(sf2_list[Bank])+"' > /dev/tcp/localhost/9988"
    write2cons(txt)
    BankCounter += 1
    Preset = 0
    ChangePreset()
    print('----- Bank: ', str(Bank), ' - ', str(sf2_list[Bank]),' / Preset: ',  ' - ', str(Preset), '\n')

# Sends msgs to FluidSynth Console
def write2cons(txt):
    f = open("./preset.sh", "w")
    f.write(txt)
    f.close()
    os.system("sudo -H -u raspi bash ./preset.sh")

# Assign all the Capture ports to Looper Input
def all_captures_to_input():
    capture = client.get_ports(is_audio=True, is_physical=True, is_output=True)
    print(capture, '\n')
    if not capture:
        raise RuntimeError("No physical capture ports")
    for src in capture:
        client.connect(src, input_port)

#Assign the Looper Output to all the Playback ports
def output_to_all_playbacks():
    playback = client.get_ports(is_audio=True, is_physical=True, is_input=True)
    print(playback, '\n')
    if not playback:
        raise RuntimeError("No physical playback ports")
    for dest in playback:
        client.connect(output_port, dest)

#Assign all the Capture ports to Looper Input
def connect_fluidsynth_to_input():
    client.connect('fluidsynth-midi:left', 'RaspiLoopStation:input_1')
    client.connect('fluidsynth-midi:right', 'RaspiLoopStation:input_1')

def is_jack_server_running():
    try:
        # Try to create a Cliente without activating
        client = jack.Client("CheckJackServer", no_start_server=True)
        client.close()  # Close cliente inmediately
        return True
    except jack.JackError: # If JackError happens, ther server is NOT active
        return False

#Defining functions of all the buttons during jam session...
PREVBUTTON.when_released = Prev_Button_Press
PREVBUTTON.when_held = Prev_Button_Held
NEXTBUTTON.when_released = Next_Button_Press
NEXTBUTTON.when_held = Next_Button_Held
MODEBUTTON.when_released = Change_Mode
MODEBUTTON.when_held = restart_program
RECBUTTON.when_pressed = Rec_Button_Pressed
#RECBUTTON.when_held =
CLEARBUTTON.when_released = Clear_Button_Pressed
CLEARBUTTON.when_held = Clear_Button_Held
PLAYBUTTON.when_released = Mute_Button_Pressed
PLAYBUTTON.when_held = Mute_Button_Held

print("Detecting SoundCard Number:",str(INDEVICE))
display.value = " ."
while Mode == 3:
    try:
        with open("/proc/asound/cards", "r") as f:
            content = f.read().strip()
        # Check if " INDEVICE [" is in the list of sound cards
        if (" "+str(INDEVICE)+" [") in content:
            Mode = 0
            print("Sound card number:",str(INDEVICE)," detected\n")
        else:
            print("Sound card number:",str(INDEVICE)," NOT detected", end='\r')
            time.sleep(1)
    except FileNotFoundError:
        print("This system does not have /proc/asound/cards. Not a Linux system?")

# Test if jack server is running and if not, run it
if is_jack_server_running():
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
        #self.main_audio contain audio data in arrays of CHUNKs.
        self.main_audio = np.zeros([MAXLENGTH, CHUNK], dtype=np.int16)
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

    #increment_pointers() increments pointers and, when restarting while recording
    def increment_pointers(self):
        if self.readp == self.length - 1:
            self.readp = 0
            print(' '*60, end='\r')
        else:
            self.readp += 1

        progress = (loops[0].readp / (loops[0].length + 1))*41
        self.writep = (self.writep + 1) % self.length
        print('#'*int(progress), end='\r')

    #initialize() raises self.length to closest integer multiple of LENGTH and initializes read and write pointers
    def initialize(self): #It initializes when recording of loop stops. It de-initializes after Clearing.
        if self.initialized:
            print('     Redundant initialization.','\n')
            return
        self.writep = self.length - 1
        self.pointer_last_buffer_recorded = self.writep
        self.length_factor = (int((self.length - OVERSHOOT) / LENGTH) + 1)
        self.length = self.length_factor * LENGTH
        print('     length ' + str(self.length))
        print('     last buffer recorded ' + str(self.pointer_last_buffer_recorded))
        #crossfade
        fade_out(self.main_audio[self.pointer_last_buffer_recorded]) #fade out the last recorded buffer
        preceding_buffer_copy = np.copy(self.preceding_buffer)
        fade_in(preceding_buffer_copy)
        self.main_audio[self.length - 1, :] += preceding_buffer_copy[:]
        #audio should be written ahead of where it is being read from, to compensate for input+output latency
        self.readp = (self.writep + LATENCY) % self.length
        self.initialized = True
        self.is_playing = True
        #self.increment_pointers()
        debug()

    #add_buffer() appends a new buffer unless loop is filled to MAXLENGTH
    #expected to only be called before initialization
    def add_buffer(self, data):
        global LENGTH
        if self.length >= (MAXLENGTH - 1):
            self.length = 0
            print('loop full')
            return
        self.main_audio[self.length, :] = np.copy(data) #Add to main_audio the buffer entering through Jack
        self.length = self.length + 1 #Increase the length of the loop
        if not setup_donerecording:
            LENGTH += 1

    def toggle_mute(self):
        print('-=Toggle Mute=-','\n')
        if self.initialized:
            if self.is_playing:
                if not self.is_waiting_mute:
                    self.is_waiting_mute = True
                else:
                    self.is_waiting_mute = False
            else:
                if not self.is_waiting_play:
                    self.is_waiting_play = True
                else:
                    self.is_waiting_play = False
                self.is_solo = False
            debug()

    def toggle_solo(self):
        print('-=Toggle Solo=-','\n')
        if self.initialized:
            if not self.is_solo:
                print('-------------Solo')
                for i in range(10):
                    if i != LoopNumber and loops[i].initialized and not loops[i].is_solo and loops[i].is_playing:
                        loops[i].is_waiting_mute = True
                self.is_solo = True
            else:
                print('-------------UnSolo')
                for i in range (10):
                    if i !=  LoopNumber and loops[i].initialized:
                        loops[i].is_waiting_play = True
                        loops[i].is_solo = False
                self.is_solo = False
            debug()

    #Restarting is True only when readp==0 and the loop is initialized, and is only checked after recording the Master Loop (0)
    def is_restarting(self):
        if not self.initialized:
            return False
        if self.readp == 0:
            return True
        return False

    #read() reads and returns a buffer of audio from the loop
    #   if not initialized: Do nothing
    #   initialized but muted: Just increment pointers
    #   initialized and playing: Read audio from the loop and increment pointers
    def read(self):
        if loops[0].is_restarting():  # Turns On the Red Led of PLAYBUTTON to mark the starting of Master Loop
            PLAYLEDR.on()
            PLAYLEDG.off()
            if self.is_waiting_rec:  # If a Track is_waiting_rec marks Track to Rec and erases waiting state
                self.is_recording = True
                self.is_waiting_rec = False
                print('-=Start Recording Track ', LoopNumber, '\n')

        if not self.initialized:
            return(silence)

        if self.is_waiting_play and loops[0].readp == 0:
            self.is_waiting_play = False
            self.is_playing = True

        if self.is_waiting_mute and loops[0].readp == 0:
            self.is_waiting_mute = False
            self.is_playing = False

        if not self.is_playing or self.is_waiting_play:
            self.increment_pointers()
            return(silence)

        tmp = self.readp
        self.increment_pointers()

        return(self.main_audio[tmp, :])

    def undo(self):
        if self.is_recording:
            self.clear_track()
            print('-=Undo=-','\n')
        debug()

    #clear() clears the loop so that a new loop of the same or a different length can be recorded on the track
    def clear(self):
        global setup_donerecording, setup_is_recording, LENGTH
        if LoopNumber == 0:
            for loop in loops:
                loop.initialized = False
                loop.is_waiting_rec = False
                loop.is_waiting_play = False
                loop.is_waiting_mute = False
                loop.is_playing = False
                loop.is_recording = False
                loop.length_factor = 1
                loop.length = 0
                loop.volume = OrigVolume
                loop.readp  =  0
                loop.writep = 0
                loop.pointer_last_buffer_recorded = 0
                loop.main_audio = np.zeros([MAXLENGTH, CHUNK], dtype=np.int16)
                loop.preceding_buffer = np.zeros([CHUNK], dtype=np.int16)
            setup_donerecording = False
            setup_is_recording = False
            LENGTH = 0
            print('-=Cleared ALL=-','\n')
        else:
            self.clear_track()
        debug()

    def clear_track(self):
        self.initialized = False
        self.is_waiting_rec = False
        self.is_waiting_play = False
        self.is_waiting_mute = False
        self.is_playing = False
        self.is_recording = False
        self.length_factor = 1
        self.length = 0
        self.volume = OrigVolume
        self.readp = 0
        self.writep = 0
        self.pointer_last_buffer_recorded = 0
        self.main_audio = np.zeros([MAXLENGTH, CHUNK], dtype=np.int16)
        self.preceding_buffer = np.zeros([CHUNK], dtype=np.int16)
        print('-=Clear Track=-', '\n')

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
            #turn off recording
            if not self.initialized:
                self.initialize()
                if LoopNumber == 0:
                    setup_is_recording = False
                    setup_donerecording = True
                    print('---Master Track Recorded---','\n')
            self.is_recording = False
            self.is_waiting_rec = False

        #unless flagged, schedule recording. If chosen track was recording, then stop recording
        if not already_recording:
            if LoopNumber == 0:
                self.is_recording = True
                setup_is_recording = True
            else:
                self.is_waiting_rec = True
        debug()

#defining ten audio loops. loops[0] is the master loop.
loops = [audioloop() for _ in range(10)]

def debug():
    print('   |init|isrec\t|iswait\t|isplay\t|iswaiP\t|iswaiM\t|Solo\t|Vol')
    for i in range(9):
        print(i, ' |',
              int(loops[i].initialized), '\t|',
              int(loops[i].is_recording), '\t|',
              int(loops[i].is_waiting_rec), '\t|',
              int(loops[i].is_playing), '\t|',
              int(loops[i].is_waiting_play), '\t|',
              int(loops[i].is_waiting_mute), '\t|',
              int(loops[i].is_solo), '\t|',
              round(loops[i].volume,1))
    print('setup_donerecording=', setup_donerecording, ' setup_is_recording=', setup_is_recording)
    print('length=', loops[LoopNumber].length, 'LENGTH=', LENGTH, 'length_factor=', loops[LoopNumber].length_factor,'\n')
    print('|', ' '*7,'|',' '*7,'|', ' '*7,'|',' '*7,'|')

#show_status() checks which loops are recording/playing and lights up LEDs accordingly
def show_status():
    global DispData, dispcount
    # If Prev / Next Buttons are Pressed shows selected LoopNumber / Preset (depends of Mode)
    if DispData == "":
        if Mode == 0:
            display.value = str(LoopNumber)
        elif Mode == 1:
            display.value = str(Preset)[-1] + "."
    else:  # Else, if Prev / Next Buttons are Held, display shows Volume / Bank (depends of Mode)
        if dispcount <= 4:
            display.value = DispData
            dispcount += 1
        else:
            dispcount = 0
            DispData = ""

    if loops[LoopNumber].is_recording:
        RECLEDR.on()
        RECLEDG.off()
    elif loops[LoopNumber].is_waiting_rec:
        RECLEDR.on()
        RECLEDG.on()
    elif setup_donerecording:
        RECLEDR.off()
        RECLEDG.off()

    if loops[LoopNumber].is_waiting_play or loops[LoopNumber].is_waiting_mute:
        PLAYLEDR.on()
        PLAYLEDG.on()
    elif loops[LoopNumber].is_playing:
        PLAYLEDR.off()
        PLAYLEDG.on()
    else:
        PLAYLEDR.off()
        PLAYLEDG.off()

play_buffer = np.zeros([CHUNK], dtype=np.int16) #Buffer to hold mixed audio from all tracks
silence = np.zeros([CHUNK], dtype=np.int16) #A buffer containing silence
current_rec_buffer = np.zeros([CHUNK], dtype=np.int16) #Buffer to hold in_data

# Callback de procesamiento de audio
@client.set_process_callback
def looping_callback(frames):
    global play_buffer, current_rec_buffer
    global LENGTH, First_Run

    # Waits 3 seconds aprox. only the First_Run to allow all the jack connections be finished
    if First_Run < (18000/RATE*CHUNK):
        First_Run += 1
        print(First_Run, end='\r')
        return

    # Read input buffer from JACK
    current_rec_buffer = float2pcm(input_port.get_array()) # Capture current input jack buffer after converting Float2PCM

    # Setup: First Recording
    if not setup_donerecording: #if setup is not done i.e. if the master loop hasn't been recorded to yet
        loops[0].is_waiting_rec = 1

    #if a loop is recording, check initialization and accordingly append
    for loop in loops:
        if loop.is_recording:
            print('--------------------------------------------------=Recording=-', end='\r')
            loop.add_buffer(current_rec_buffer)

    #add to play_buffer only one-fourth of each audio signal times the output_volume
    play_buffer[:] = np.multiply((
        loops[0].read().astype(np.int32)*loops[0].volume/10+
        loops[1].read().astype(np.int32)*loops[1].volume/10+
        loops[2].read().astype(np.int32)*loops[2].volume/10+
        loops[3].read().astype(np.int32)*loops[3].volume/10+
        loops[4].read().astype(np.int32)*loops[4].volume/10+
        loops[5].read().astype(np.int32)*loops[5].volume/10+
        loops[6].read().astype(np.int32)*loops[6].volume/10+
        loops[7].read().astype(np.int32)*loops[7].volume/10+
        loops[8].read().astype(np.int32)*loops[8].volume/10+
        loops[9].read().astype(np.int32)*loops[9].volume/10
    ), output_volume, out=None, casting='unsafe').astype(np.int16)

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
        time.sleep(0.2)
        output_port = client.outports.register("output_1")
        print('----- Jack Client Out Port Registered-----\n', str(output_port),'\n')
        time.sleep(0.2)

        #time.sleep(2)
        all_captures_to_input()
        time.sleep(0.2)
        output_to_all_playbacks()
        time.sleep(0.2)

        # Get MIDI Capture Ports
        outMIDIports = client.get_ports(is_midi=True, is_output=True)
        print("MIDI Capture Ports:",'\n')
        print(outMIDIports,'\n')

        # Get MIDI Playback Ports
        inMIDIports = client.get_ports(is_midi=True, is_input=True)
        print("MIDI Playback Ports:",'\n')
        print(inMIDIports,'\n')

        #then we turn on Green and Red lights of REC Button to indicate that looper is ready to start looping
        print("Jack Client Active. Press Ctrl+C to Stop.",'\n')
        show_status()
        debug()
        #once all LEDs are on, we wait for the master loop record button to be pressed
        print('---Waiting for Record Button---','\n')

        # If a MIDI Capture Port exists, start FluidSynth
        target_port = 'system:midi_capture_1'
        if any(port.name == target_port for port in outMIDIports):
            if len(sf2_list) > 0:
                soundfont = " ./sf2/"+str(sf2_list[0])
            else:
                soundfont = ""
            os.system ("sudo -H -u raspi fluidsynth -isj -a jack -r 48000 -g 0.9 -o 'midi.driver=jack' -o 'audio.jack.autoconnect=True' -o 'shell.port=9988'  "+soundfont+" &")
            print('---FluidSynth Jack Starting---','\n')
            time.sleep(3)
            connect_fluidsynth_to_input()

        while True:
            show_status()
            time.sleep(0.1)
            pass  # Keep Client executing

    except KeyboardInterrupt:
        TurningOff()
