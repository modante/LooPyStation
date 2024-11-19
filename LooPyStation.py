import jack
import pyaudio
import numpy as np
import time
from gpiozero import LED, Button, LEDCharDisplay
from time import sleep
import os, sys

print('Starting RaspiLoopStation...','\n')

#get configuration (audio settings etc.) from file
settings_file=open('./settings.prt', 'r')
parameters=settings_file.readlines()
settings_file.close()

#Variables Initialization
RATE=int(parameters[0]) #sample rate
CHUNK=int(parameters[1]) #buffer size
FORMAT=pyaudio.paInt16 #specifies bit depth (16-bit)
CHANNELS=1 #mono audio
latency_in_milliseconds=int(parameters[2])
LATENCY=round((latency_in_milliseconds/1000) * (RATE/CHUNK)) #latency in buffers
INDEVICE=int(parameters[3]) #index (per pyaudio) of input device
OUTDEVICE=int(parameters[4]) #index of output device
overshoot_in_milliseconds=int(parameters[5]) #allowance in milliseconds for pressing 'stop recording' late
OVERSHOOT=round((overshoot_in_milliseconds/1000) * (RATE/CHUNK)) #allowance in buffers
MAXLENGTH=int(12582912 / CHUNK) #96mb of audio in total
SAMPLEMAX=0.9 * (2**15) #maximum possible value for an audio sample (little bit of margin)
LENGTH=0 #length of the first recording on track 1, all subsequent recordings quantized to a multiple of this.
LoopNumber=0 #Pointer to the selected loop
setup_is_recording=False #set to True when track 1 recording button is first pressed
setup_donerecording=False #set to true when first track 1 recording is done
play_was_held=False
undo_was_held=False
prev_was_held=False
next_was_held=False
mode_was_held=False
Mode=3
Preset=0
Bank=0
Counter=1
First_Run=0
OrigVolume=0.7
sf2_dir="./sf2" # Get a list of all files in the directory ./sf2
sf2_list=sorted([f for f in os.listdir(sf2_dir) if os.path.isfile(os.path.join(sf2_dir, f))])
print('Rate: ' + str(RATE) + ' / CHUNK: ' +  str(CHUNK),'\n')
print('Latency correction (buffers): ' + str(LATENCY),'\n')

#mixed output (sum of audio from tracks) is multiplied by output_volume before being played.
#This is updated dynamically as max peak in resultant audio changes
output_volume=np.float32(1.0)
#multiplying by up_ramp and down_ramp gives fade-in and fade-out
down_ramp=np.linspace(1, 0, CHUNK)
up_ramp=np.linspace(0, 1, CHUNK)

#Buttons, Leds and 8-Segments Display
debounce_length=0.05 #length in seconds of button debounce period
display=LEDCharDisplay(11, 25, 9, 10, 24, 22, 23, dp=27)
PLAYLEDR=(LED(26, active_high=False))
PLAYLEDG=(LED(20, active_high=False))
RECLEDR=(LED(0, active_high=False))
RECLEDG=(LED(1, active_high=False))
PLAYBUTTON=(Button(15, bounce_time=debounce_length))
RECBUTTON=(Button(18, bounce_time=debounce_length))
UNDOBUTTON=(Button(17, bounce_time=debounce_length))
PREVBUTTON=(Button(5, bounce_time=debounce_length))
NEXTBUTTON=(Button(12, bounce_time=debounce_length))
MODEBUTTON=(Button(6, bounce_time=debounce_length))
PLAYBUTTON.hold_time=0.5
RECBUTTON.hold_time=0.5
UNDOBUTTON.hold_time=0.5
PREVBUTTON.hold_time=0.5
NEXTBUTTON.hold_time=0.5
MODEBUTTON.hold_time=3

#Behavior when MODEBUTTON is held
def restart_program():
    display.value=" ."
    TurningOff()
    print("Reiniciando el programa...")
    python=sys.executable  # Obtiene el intérprete de Python actual
    os.execv(python, [python] + sys.argv)

def TurningOff():
    os.system ("sudo -H -u raspi killall fluidsynth")
    #fs.delete()
    print("Closing FluidSynth")
    time.sleep(1)
    client.deactivate()
    print("Desactivando cliente JACK.")
    PowerOffLeds()
    print('Done...')

#fade_in() applies fade-in to a buffer
def fade_in(buffer):
    np.multiply(buffer, up_ramp, out=buffer, casting='unsafe')

#fade_out() applies fade-out to a buffer
def fade_out(buffer):
    np.multiply(buffer, down_ramp, out=buffer, casting='unsafe')

#Converts pcm2float array
def pcm2float(sig, dtype='float32'):
    sig=np.asarray(sig)
    if sig.dtype.kind not in 'iu':
        raise TypeError("'sig' must be an array of integers")
    dtype=np.dtype(dtype)
    if dtype.kind != 'f':
        raise TypeError("'dtype' must be a floating point type")

    i=np.iinfo(sig.dtype)
    abs_max=2 ** (i.bits - 1)
    offset=i.min + abs_max
    return (sig.astype(dtype) - offset) / abs_max

#Converts float2pcm array
def float2pcm(sig, dtype='int16'):
    sig=np.asarray(sig)
    if sig.dtype.kind != 'f':
        raise TypeError("'sig' must be a float array")
    dtype=np.dtype(dtype)
    if dtype.kind not in 'iu':
        raise TypeError("'dtype' must be an integer type")

    i=np.iinfo(dtype)
    abs_max=2 ** (i.bits - 1)
    offset=i.min + abs_max
    return (sig * abs_max + offset).clip(i.min, i.max).astype(dtype)

#Turn-Off all the Leds
def PowerOffLeds():
    RECLEDR.off()
    RECLEDG.off()
    PLAYLEDR.off()
    PLAYLEDG.off()

#Change Mode
def Change_Mode():
    global LoopNumber, Bank, Mode, mode_was_held
    if not mode_was_held:
        if Mode == 3:
            Mode=0
        elif Mode == 0:
            Mode=1
            PowerOffLeds()
            display.value=((str(Bank))[-1]+".")
            print('----- Bank: ', str(Bank), ' - ', str(sf2_list[Bank]),' / Preset: ',  ' - ', str(Preset), '\n')
        elif Mode == 1:
            Mode=0
        print('----------= Changed to Mode=', str(Mode),'\n')
    mode_was_held=False

#Behavior when PREVBUTTON is pressed
def Prev_Button_Press():
    global LoopNumber, Preset, prev_was_held
    if not prev_was_held:
        if Mode == 0 and setup_donerecording:
            if LoopNumber == 0:
                LoopNumber=9
            else:
                LoopNumber=LoopNumber-1
            print('-= Prev Loop =---> ', LoopNumber,'\n')
        if Mode == 1:
            if Preset >= 1:
                Preset=Preset - 1
                ChangePreset()
    prev_was_held=False

#Behavior when PREVBUTTON is held
def Prev_Button_Held():
    global Bank, prev_was_held
    if Mode == 0 and setup_donerecording and loops[LoopNumber].initialized:
        if loops[LoopNumber].volume >= 0.1:
            loops[LoopNumber].volume=loops[LoopNumber].volume - 0.1
            print('Volume Decreased=', loops[LoopNumber].volume,'\n')
            display.value=((str(loops[LoopNumber].volume))[-1])
            debug()
    if Mode == 1:
        if Bank >= 1:
            Bank=Bank -1
            ChangeBank()
    prev_was_held=True

#Behavior when NEXTBUTTON is pressed
def Next_Button_Press():
    global LoopNumber, Preset, next_was_held
    if not next_was_held:
        if Mode == 0 and setup_donerecording:
            if LoopNumber == 9:
                LoopNumber=0
            else:
                LoopNumber=LoopNumber+1
            print('-= Next Loop =---> ', LoopNumber,'\n')
        if Mode == 1:
            if Preset < 125:
                Preset=Preset + 1
                ChangePreset()
    next_was_held=False

#Behavior when NEXTBUTTON is held
def Next_Button_Held():
    global Bank, next_was_held
    if Mode == 0 and setup_donerecording and loops[LoopNumber].initialized:
        if loops[LoopNumber].volume <= 1.4:
            loops[LoopNumber].volume=loops[LoopNumber].volume + 0.1
            print('Volume Increased=', loops[LoopNumber].volume,'\n')
            display.value=((str(loops[LoopNumber].volume))[-1])
            debug()
    if Mode == 1:
        if Bank < len(sf2_list)-1:
            Bank=Bank + 1
            ChangeBank()
    next_was_held=True

#Behavior when RECBUTTON is pressed
def Rec_Button_Pressed():
    loops[LoopNumber].set_recording()

#Behavior when MUTEBUTTON is pressed
def Mute_Button_Pressed():
    global play_was_held
    if setup_donerecording:
        if not play_was_held:
            loops[LoopNumber].toggle_mute()
        play_was_held=False

#Behavior when MUTEBUTTON is held
def Mute_Button_Held():
    global play_was_held
    if setup_donerecording:
        play_was_held=True
        loops[LoopNumber].toggle_solo()

#Behavior when UNDOBUTTON is pressed
def Undo_Button_Pressed():
    global undo_was_held
    if not undo_was_held:
        if setup_donerecording:
            loops[LoopNumber].undo()
        else:
            loops[LoopNumber].is_recording=False
            loops[LoopNumber].clear()
    undo_was_held=False

#Behavior when UNDOBUTTON is held
def Undo_Button_Held():
    global undo_was_held
    undo_was_held=True
    loops[LoopNumber].clear()

# Change the Preset
def ChangePreset():
    display.value=((str(Preset))[-1]+".")
    txt="echo 'prog 0 "+str(Preset)+"' > /dev/tcp/localhost/9988"
    write2cons(txt)
    time.sleep(0.1)
    print('----- Bank: ', str(Bank), ' - ', str(sf2_list[Bank]),' / Preset: ',  ' - ', str(Preset), '\n')

# Change the Bank
def ChangeBank():
    global Counter, Preset
    display.value=((str(Bank))[-1]+".")
    txt="echo 'unload "+str(Counter)+"' > /dev/tcp/localhost/9988"
    write2cons(txt)
    time.sleep(0.1)
    txt="echo 'load ./sf2/"+str(sf2_list[Bank])+"' > /dev/tcp/localhost/9988"
    write2cons(txt)
    Counter=Counter + 1
    Preset=0
    ChangePreset()
    print('----- Bank: ', str(Bank), ' - ', str(sf2_list[Bank]),' / Preset: ',  ' - ', str(Preset), '\n')

def write2cons(txt):
    f=open("./preset.sh", "w")
    f.write(txt)
    f.close()
    os.system("sudo -H -u raspi bash ./preset.sh")

#Assign all the Capture ports to Looper Input
def all_captures_to_input():
    capture=client.get_ports(is_audio=True, is_physical=True, is_output=True)
    print(capture, '\n')
    if not capture:
        raise RuntimeError("No physical capture ports")
    for src in capture:
        client.connect(src, input_port)

#Assign the Looper Output to all the Playback ports
def output_to_all_playbacks():
    playback=client.get_ports(is_audio=True, is_physical=True, is_input=True)
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
        client=jack.Client("CheckJackServer", no_start_server=True)
        client.close()  # Close cliente inmediately
        return True
    except jack.JackError:
        # Si ocurre un JackError, significa que el servidor no está activo
        return False

#Defining functions of all the buttons during jam session...
PREVBUTTON.when_released=Prev_Button_Press
PREVBUTTON.when_held=Prev_Button_Held
NEXTBUTTON.when_released=Next_Button_Press
NEXTBUTTON.when_held=Next_Button_Held
MODEBUTTON.when_released=Change_Mode
MODEBUTTON.when_held=restart_program
RECBUTTON.when_pressed=Rec_Button_Pressed
#RECBUTTON.when_held =
UNDOBUTTON.when_released=Undo_Button_Pressed
UNDOBUTTON.when_held=Undo_Button_Held
PLAYBUTTON.when_released=Mute_Button_Pressed
PLAYBUTTON.when_held=Mute_Button_Held

print("Detecting SoundCard Number:",str(INDEVICE))
display.value=" ."
while Mode == 3:
    try:
        with open("/proc/asound/cards", "r") as f:
            content=f.read().strip()
        # Check if "H5" is in the list of sound cards
        if (" "+str(INDEVICE)+" [") in content:
            Mode=0
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
            display.value=" "
        else:
            display.value=" ."
        time.sleep(0.5)
    print("----- Jack Server is running",'\n')

# Initializing JACK Client
client=jack.Client("RaspiLoopStation")
print('----- Jack Client RaspiLoopStation Initialized','\n')

class audioloop:
    def __init__(self):
        self.initialized=False
        self.length_factor=1
        self.length=0
        #self.main_audio and self.dub_audio contain audio data in arrays of CHUNKs.
        self.main_audio=np.zeros([MAXLENGTH, CHUNK], dtype=np.int16)
        #self.dub_audio contains the latest recorded dub. Clearing this achieves undo.
        self.dub_audio=np.zeros([MAXLENGTH, CHUNK], dtype=np.int16)
        self.readp=0
        self.writep=0
        self.is_recording=False
        self.is_playing=False
        self.is_waiting_play=False
        self.is_waiting_mute=False
        self.is_solo=False
        self.is_waiting=False
        self.volume=OrigVolume
        self.pointer_last_buffer_recorded=0 #index of last buffer added
        self.preceding_buffer=np.zeros([CHUNK], dtype=np.int16)
        self.dub_ratio=1.0

    #increment_pointers() increments pointers and, when restarting while recording, advances dub ratio
    def increment_pointers(self):
        if self.readp == self.length - 1:
            self.readp=0
            print(' '*60, end='\r')
            if self.is_recording:
                self.dub_ratio=self.dub_ratio * 0.9
                #print('Self dub ratio=',self.dub_ratio,'\n')
        else:
            self.readp=self.readp + 1
        progress=(loops[0].readp / (loops[0].length + 1))*41
        self.writep=(self.writep + 1) % self.length
        print('#'*int(progress), end='\r')

    #initialize() raises self.length to closest integer multiple of LENGTH and initializes read and write pointers
    def initialize(self): #It initializes when recording of loop stops. It de-initializes after Clearing.
        if self.initialized:
            print('     Redundant initialization.','\n')
            return
        self.writep=self.length - 1
        self.pointer_last_buffer_recorded=self.writep
        self.length_factor=(int((self.length - OVERSHOOT) / LENGTH) + 1)
        self.length=self.length_factor * LENGTH
        print('     length ' + str(self.length))
        print('     last buffer recorded ' + str(self.pointer_last_buffer_recorded))
        #crossfade
        fade_out(self.main_audio[self.pointer_last_buffer_recorded]) #fade out the last recorded buffer
        preceding_buffer_copy=np.copy(self.preceding_buffer)
        fade_in(preceding_buffer_copy)
        self.main_audio[self.length - 1, :] += preceding_buffer_copy[:]
        #audio should be written ahead of where it is being read from, to compensate for input+output latency
        self.readp=(self.writep + LATENCY) % self.length
        self.initialized=True
        self.is_playing=True
        self.increment_pointers()
        debug()

    #add_buffer() appends a new buffer unless loop is filled to MAXLENGTH
    #expected to only be called before initialization
    def add_buffer(self, data):
        if self.length >= (MAXLENGTH - 1):
            self.length=0
            print('loop full')
            return
        self.main_audio[self.length, :]=np.copy(data) #Add to main_audio the buffer entering through Jack
        self.length=self.length + 1 #Increase the length of the loop

    def toggle_mute(self):
        print('-=Toggle Mute=-','\n')
        if self.initialized:
            if self.is_playing:
                if not self.is_waiting_mute:
                    self.is_waiting_mute=True
                else:
                    self.is_waiting_mute=False
            else:
                if not self.is_waiting_play:
                    self.is_waiting_play=True
                else:
                    self.is_waiting_play=False
                self.is_solo=False
            debug()

    def toggle_solo(self):
        print('-=Toggle Solo=-','\n')
        if self.initialized:
            if not self.is_solo:
                print('-------------Solo')
                for i in range(10):
                    if i != LoopNumber and loops[i].initialized and not loops[i].is_solo and loops[i].is_playing:
                        loops[i].is_waiting_mute=True
                self.is_solo=True
            else:
                print('-------------UnSolo')
                for i in range (10):
                    if i != LoopNumber and loops[i].initialized:
                        loops[i].is_waiting_play=True
                        loops[i].is_solo=False
                self.is_solo=False
            debug()

    #Restarting is True only when readp==0 and the loop is initialized, and is only checked after recording the Master Loop (0)
    def is_restarting(self):
        #print('-= Is Restarting =-')
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
        if not self.initialized:
            return(silence)

        if self.is_waiting_play and loops[0].readp == 0:
            self.is_waiting_play=False
            self.is_playing=True

        if self.is_waiting_mute and loops[0].readp == 0:
            self.is_waiting_mute=False
            self.is_playing=False


        if not self.is_playing or self.is_waiting_play:
            self.increment_pointers()
            return(silence)

        tmp=self.readp
        self.increment_pointers()

        if loops[0].readp == 0:
            PLAYLEDR.on()
            PLAYLEDG.off()

        #return(self.main_audio[tmp, :] + self.dub_audio[tmp, :])
        return(self.main_audio[tmp, :])

    #dub() overdubs an incoming buffer of audio to the loop at writep
    #   at writep:
    #   first, the buffer from dub_audio is mixed into main_audio
    #   next, the buffer in dub_audio is overwritten with the incoming buffer
    def dub(self, data, fade_in=False, fade_out=False):
        if not self.initialized:
            return
        datadump=np.copy(data)
        #self.main_audio[self.writep, :]=self.main_audio[self.writep, :] * 0.9 + self.dub_audio[self.writep, :] * self.dub_ratio
        #self.dub_audio[self.writep, :]=datadump[:]
        self.dub_audio[self.writep, :]=self.main_audio[self.writep, :]
        self.main_audio[self.writep, :]=datadump[:]
        debug()

    #clear() clears the loop so that a new loop of the same or a different length can be recorded on the track
    def clear(self):
        global setup_donerecording
        global setup_is_recording
        global LENGTH
        if self.initialized:
            self.main_audio=np.zeros([MAXLENGTH, CHUNK], dtype=np.int16)
            self.dub_audio=np.zeros([MAXLENGTH, CHUNK], dtype=np.int16)
            self.initialized=False
            self.is_playing=False
            self.is_recording=False
            self.is_waiting=False
            self.length_factor=1
            self.length=0
            self.volume=OrigVolume
            self.readp=0
            self.writep=0
            self.pointer_last_buffer_recorded=0
            self.preceding_buffer=np.zeros([CHUNK], dtype=np.int16)
        if LoopNumber == 0:
            for loop in loops:
                loop.initialized=False
                loop.is_playing=False
                loop.is_recording=False
                loop.is_waiting=False
                loop.length_factor=1
                loop.length=0
                loop.volume=OrigVolume
                loop.main_audio=np.zeros([MAXLENGTH, CHUNK], dtype=np.int16)
                loop.dub_audio=np.zeros([MAXLENGTH, CHUNK], dtype=np.int16)
            setup_donerecording=False
            setup_is_recording=False
            LENGTH=0
            print('-=Cleared ALL=-','\n')
        else:
            print('-=Clear=-','\n')
        debug()

    #undo() resets dub_audio to silence
    def undo(self):
        if self.initialized:
            if not self.is_recording:
                self.dub_audio, self.main_audio=self.main_audio, self.dub_audio
                self.is_recording=False
                self.is_waiting=False
                print('-=Undo=-','\n')
        else:
            self.is_recording=False
            self.is_playing=False
            self.is_recording=False
            self.is_waiting=False
            self.length_factor=1
            self.length=0
            self.main_audio=np.zeros([MAXLENGTH, CHUNK], dtype=np.int16)
            debug()

    #start recording
    def start_recording(self, previous_buffer):
        print('-=Start Recording Track ', LoopNumber,'\n')
        self.is_recording=True
        self.is_waiting=False
        self.preceding_buffer=np.copy(previous_buffer)

    #set_recording() either starts or stops recording
    #   if initialized and recording, stop recording (dubbing)
    #   if uninitialized and recording, stop recording (appending) and initialize
    #   if initialized and not recording, set as "waiting to record"
    def set_recording(self):
        global setup_is_recording
        global setup_donerecording
        print('----- set_recording called for Track', LoopNumber,'\n')
        already_recording=False

        #if chosen track is currently recording, flag it
        if self.is_recording:
            already_recording=True
            #turn off recording
            if not self.initialized:
                self.initialize()
                if LoopNumber == 0:
                    setup_is_recording=False
                    setup_donerecording=True
                    print('---Master Track Recorded---','\n')
        self.is_recording=False

        self.is_waiting=False
        #unless flagged, schedule recording. If chosen track was recording, then stop recording
        #like a toggle but with delayed enabling and instant disabling
        if not already_recording:
            if LoopNumber == 0:
                self.is_recording=True
                setup_is_recording=True
            else:
                self.is_waiting=True
        debug()

#defining ten audio loops. loops[0] is the master loop.
loops=[audioloop() for _ in range(10)]

def debug():
    print('  |init\t|isrec\t|iswait\t|isplay\t|iswaiP\t|iswaiM\t|Solo\t|Vol')
    for i in range(9):
        print(i, ' |', int(loops[i].initialized), '\t|', int(loops[i].is_recording), '\t|', int(loops[i].is_waiting), '\t|', int(loops[i].is_playing), '\t|', int(loops[i].is_waiting_play), '\t|', int(loops[i].is_waiting_mute), '\t|', int(loops[i].is_solo), '\t|', loops[i].volume)
    print('setup_donerecording=', setup_donerecording, ' setup_is_recording=', setup_is_recording)
    print('length=', loops[LoopNumber].length, 'LENGTH=', LENGTH, 'length_factor=', loops[LoopNumber].length_factor,'\n')
    print('|', ' '*7,'|',' '*7,'|', ' '*7,'|',' '*7,'|')

#update output volume to prevent mixing distortion due to sample overflow
#slow to run, so should be called on a different thread (e.g. a button callback function)
def update_volume(): #Not used
    print('---= Update Volume =---','\n')
    global output_volume
    peak=np.max(
        np.abs(
            loops[0].main_audio.astype(np.int32)[:][:]
            + loops[1].main_audio.astype(np.int32)[:][:]
            + loops[2].main_audio.astype(np.int32)[:][:]
            + loops[3].main_audio.astype(np.int32)[:][:]
            + loops[4].main_audio.astype(np.int32)[:][:]
            + loops[5].main_audio.astype(np.int32)[:][:]
            + loops[6].main_audio.astype(np.int32)[:][:]
            + loops[7].main_audio.astype(np.int32)[:][:]
            + loops[8].main_audio.astype(np.int32)[:][:]
            + loops[9].main_audio.astype(np.int32)[:][:]
            + loops[0].dub_audio.astype(np.int32)[:][:]
            + loops[1].dub_audio.astype(np.int32)[:][:]
            + loops[2].dub_audio.astype(np.int32)[:][:]
            + loops[3].dub_audio.astype(np.int32)[:][:]
            + loops[4].dub_audio.astype(np.int32)[:][:]
            + loops[5].dub_audio.astype(np.int32)[:][:]
            + loops[6].dub_audio.astype(np.int32)[:][:]
            + loops[7].dub_audio.astype(np.int32)[:][:]
            + loops[8].dub_audio.astype(np.int32)[:][:]
            + loops[9].dub_audio.astype(np.int32)[:][:]
        )
    )
    print('     peak=' + str(peak))
    if peak > SAMPLEMAX:
        output_volume=SAMPLEMAX / peak
    else:
        output_volume=1
    print(' --- output_volume=' + str(output_volume))

#show_status() checks which loops are recording/playing and lights up LEDs accordingly
def show_status():
    if Mode == 0:
        display.value=str(LoopNumber)

    if loops[LoopNumber].is_recording:
        RECLEDR.on()
        RECLEDG.off()
    elif loops[LoopNumber].is_waiting:
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

play_buffer=np.zeros([CHUNK], dtype=np.int16) #Buffer to hold mixed audio from all tracks
silence=np.zeros([CHUNK], dtype=np.int16) #A buffer containing silence
current_rec_buffer=np.zeros([CHUNK], dtype=np.int16) #Buffer to hold in_data
prev_rec_buffer=np.zeros([CHUNK], dtype=np.int16) #While looping, prev_rec_buffer keeps track of the audio buffer recorded before the current one

# Callback de procesamiento de audio
@client.set_process_callback
def looping_callback(frames):
    global play_buffer, current_rec_buffer, prev_rec_buffer
    global setup_donerecording, setup_is_recording
    global LENGTH, First_Run

    # Wait 5 seconds aprox. only the First_Run to allow all the jack configuration be finished
    if First_Run < (25000/RATE*CHUNK):
        First_Run=First_Run +1
        print(First_Run, end='\r')
        return

    # Read input buffer from JACK
    current_rec_buffer=np.right_shift(float2pcm(input_port.get_array()),0) #some input attenuation for overdub headroom purposes

    # Setup: First Recording
    if not setup_donerecording: #if setup is not done i.e. if the master loop hasn't been recorded to yet
        loops[0].is_waiting=1

        if setup_is_recording: #if setup is currently recording, that recording action happens in the following lines
            if LENGTH >= MAXLENGTH: #if the max allowed loop length is exceeded, stop recording and start looping
                print('Overflow')
                setup_donerecording=True
                setup_is_recording=False
                return
            loops[0].add_buffer(current_rec_buffer) #otherwise append incoming audio to master loop, increment LENGTH and continue
            LENGTH += 1
            return
        else: #if setup not done and not currently happening then just wait
            return #execution ony reaches here if setup (first loop record and set LENGTH) finished.

    #when master loop restarts, start recording on any other tracks that are waiting
    if loops[0].is_restarting():
        #update_volume()
        for loop in loops:
            if loop.is_waiting:
                loop.start_recording(prev_rec_buffer)
                print('---=Recording Track number:', LoopNumber, '=---','\n')

     #if master loop is waiting just start recording without checking restart
    if loops[0].is_waiting and not loops[0].initialized:
        loops[0].start_recording(prev_rec_buffer)
        print('????? if master loop is waiting just start recording without checking restart')

    #if a loop is recording, check initialization and accordingly append or overdub
    for loop in loops:
        if loop.is_recording:
            if loop.initialized:
                print('-=OverDub=-', end='\r')
                loop.dub(current_rec_buffer)
            else:
                print('-=Append=-', end='\r')
                loop.add_buffer(current_rec_buffer)

    #add to play_buffer only one-fourth of each audio signal times the output_volume
    play_buffer[:]=np.multiply((
        loops[0].read().astype(np.int32)*loops[0].volume+
        loops[1].read().astype(np.int32)*loops[1].volume+
        loops[2].read().astype(np.int32)*loops[2].volume+
        loops[3].read().astype(np.int32)*loops[3].volume+
        loops[4].read().astype(np.int32)*loops[4].volume+
        loops[5].read().astype(np.int32)*loops[5].volume+
        loops[6].read().astype(np.int32)*loops[6].volume+
        loops[7].read().astype(np.int32)*loops[7].volume+
        loops[8].read().astype(np.int32)*loops[8].volume+
        loops[9].read().astype(np.int32)*loops[9].volume
    ), output_volume, out=None, casting='unsafe').astype(np.int16)

    #current buffer will serve as previous in next iteration
    prev_rec_buffer=np.copy(current_rec_buffer)

    #play mixed audio and move on to next iteration
    output_port.get_array()[:]=pcm2float(play_buffer[:])

@client.set_shutdown_callback
def shutdown(status, reason):
    print("JACK shutdown:", reason, status)

with client:
    try:
        # Getting Jack buffer size
        buffer_size=client.blocksize
        print("Tamaño del buffer JACK (entrada y salida):", buffer_size, '\n')

        # Registering Ins/Outs Ports
        input_port=client.inports.register("input_1")
        print('----- Jack Client In Port Registered-----\n', str(input_port), '\n')
        time.sleep(0.5)
        output_port=client.outports.register("output_1")
        print('----- Jack Client Out Port Registered-----\n', str(output_port),'\n')
        time.sleep(0.5)

        #time.sleep(2)
        all_captures_to_input()
        time.sleep(0.5)
        output_to_all_playbacks()
        time.sleep(0.5)

        # Get MIDI Capture Ports
        outMIDIports=client.get_ports(is_midi=True, is_output=True)
        print("MIDI Capture Ports:",'\n')
        print(outMIDIports,'\n')

        # Get MIDI Playback Ports
        inMIDIports=client.get_ports(is_midi=True, is_input=True)
        print("MIDI Playback Ports:",'\n')
        print(inMIDIports,'\n')

        #then we turn on Green and Red lights of REC Button to indicate that looper is ready to start looping
        print("Jack Client Active. Press Ctrl+C to Stop.",'\n')
        show_status()
        debug()
        #once all LEDs are on, we wait for the master loop record button to be pressed
        print('---Waiting for Record Button---','\n')

        # If a MIDI Capture Port exists, start FluidSynth
        target_port='system:midi_capture_1'
        if any(port.name == target_port for port in outMIDIports):
            if len(sf2_list) > 0:
                soundfont=" ./sf2/"+str(sf2_list[0])
            else:
                soundfont=""
            os.system ("sudo -H -u raspi fluidsynth -isj -a jack -r 48000 -g 0.9 -o 'midi.driver=jack' -o 'audio.jack.autoconnect=True' -o 'shell.port=9988'  "+soundfont+" &")
            print('---FluidSynth Jack Starting---','\n')
            time.sleep(3)
            connect_fluidsynth_to_input()

            # Inicializa el sintetizador con las configuraciones
            #fs=fluidsynth.Synth()
            #fs.setting("audio.driver", 'jack')
            #fs.setting("midi.driver", 'jack')
            #fs.setting("audio.jack.autoconnect", True)
            #fs.setting("shell.port", 9988)
            #fs.setting("synth.sample-rate", 48000.000)
            #fs.delete()
            #fs=fluidsynth.Synth()
            #cmd="./sf2/"+str(sf2_list[Preset])
            #print(cmd)
            #sfid=fs.sfload(cmd)
            #time.sleep(3)
            #fs.program_select(0, sfid, 0, 0)
            #print('---FluidSynth load sf2---','\n')

        while True:
            show_status()
            time.sleep(0.1)
            pass  # Keep Client executing

    except KeyboardInterrupt:
        TurningOff()
