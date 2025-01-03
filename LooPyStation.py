import jack
import numpy as np
import time
import os, sys, io
from gpiozero import LED, Button, LEDCharDisplay
from time import sleep, time
from pydub import AudioSegment
from datetime import datetime
sys.path.append('./pyfluidsynth')
import fluidsynth
from threading import Thread, Event

print('\n', '--- Starting LooPyStation... ---', '\n')

# Get configuration (audio settings, etc.) from file ./settings.prt
settings_file = open('./settings.prt', 'r')
parameters = settings_file.readlines()
settings_file.close()
RATE = int(parameters[0])  # Sample rate
CHUNK = int(parameters[1])  # Buffer size
latency_in_milliseconds = int(parameters[2])
LATENCY = round((latency_in_milliseconds/1000) * (RATE/CHUNK))  # Latency in buffers
INDEVICE = int(parameters[3])  # Index of input device
OUTDEVICE = int(parameters[4])  # Index of output device
overshoot_in_milliseconds = int(parameters[5])  # Allowance in milliseconds for pressing 'stop recording' late
OVERSHOOT = round((overshoot_in_milliseconds/1000) * (RATE/CHUNK))  # Allowance in buffers
MAXLENGTH = int(12582912 / CHUNK)  # 96mb of audio in total
JACK_CAPTURE_PORTS = int(parameters[6])

# Variables Initialization
LENGTH = 0  # Length of the first recording or Master Track (0). All subsequent recordings will be quantized to a multiple of this.
number_of_tracks = 16
selected_loop = 0  # Pointer to the selected Loop/Track
setup_is_recording = False  # Set to True when track 1 recording button is first pressed
setup_donerecording = False  # Set to true when first track 1 recording is done
Mode = 3  # Pointer to the Mode for UI
Preset = 0  # Pointer to the Selected Preset
Bank = 0  # Pointer to the Selected Bank
Session = 0  # Pointer to the Selected Session to Import
sfid = 0  # SoundFont id of the Loaded Bank
init_volume = 14  # Initial volume for each Track
max_volume = 20  # Max volume for each Track
display_data = ""  # Secondary info to show on Display
display_count = 0  # Timer to show secondary info on Display
pause_callback = int(0.5*RATE/CHUNK)  # Pauses 2 seconds approx. the loop callback
synth_initialized = False  # Flag
set_recording_file = False  # Flag to set Recording Audio Session waiting to starting of Master Track
rec_file = False  # Flag for the Recording Audio Session activity
sf2_dir = "./sf2/"  # Dir where SoudFonts are loaded from
sessions_dir = "./sessions/"  # Dir where Sessions will be exported / imported
recordings_dir = "./recordings/"  # Dir where Recording of Audio Sessions will be stored
sessions = []
max_amplitude = 32767
volume_up = True  # Flag to Increase/Decrease Volume of Tracks

# Buttons, Leds and 8-Segments Display
display = LEDCharDisplay(11, 25, 9, 10, 24, 22, 23, dp=27)
PLAYLEDR = (LED(26, active_high=False))
PLAYLEDG = (LED(20, active_high=False))
RECLEDR = (LED(0, active_high=False))
RECLEDG = (LED(1, active_high=False))

debounce_length = 0.05  # Length in seconds of button debounce period
RECBUTTON = (Button(18, bounce_time=debounce_length))
RECBUTTON.hold_time = 0.5
rec_was_held = False
PLAYBUTTON = (Button(15, bounce_time=debounce_length))
PLAYBUTTON.hold_time = 0.5
play_was_held = False
CLEARBUTTON = (Button(17, bounce_time=debounce_length))
CLEARBUTTON.hold_time = 0.5
clear_was_held = False
PREVBUTTON = (Button(5, bounce_time=debounce_length))
PREVBUTTON.hold_time = 0.5
prev_was_held = False
NEXTBUTTON = (Button(12, bounce_time=debounce_length))
NEXTBUTTON.hold_time = 0.5
next_was_held = False
MODEBUTTON = (Button(6, bounce_time=debounce_length))
MODEBUTTON.hold_time = 2.5
mode_was_held = False

play_buffer = np.zeros([CHUNK], dtype=np.int16)  # Buffer to hold mixed audio from all tracks
silence = np.zeros([CHUNK], dtype=np.int16)  # A buffer containing silence
current_rec_buffer = np.zeros([CHUNK], dtype=np.int16)  # Buffer to hold in_data
output_volume = np.float32(1.0)  # Mixed output (sum of audio from tracks) is multiplied by output_volume before being played. Not used by now
fade_in = np.linspace(0, 1, CHUNK)
fade_out = np.linspace(1, 0, CHUNK)

# ------- END of Variables and Flags ------

print('Rate: ' + str(RATE) + ' / CHUNK: ', str(CHUNK), '\n')
print('Latency correction (buffers): ', str(LATENCY), '\n')

# Get a list of all files in the directory ./sf2
sf2_list = sorted(
    [f for f in os.listdir(sf2_dir)
     if os.path.isfile(os.path.join(sf2_dir, f)) and f.lower().endswith('.sf2')])  # Put all the detected files alphabetically on an array
print(sf2_list, '\n')

# Get a list of all the Sessions Exported on directory ./sessions
def list_sessions():
    global selected_session, sessions
    sessions_list = sorted(
        [f for f in os.listdir(sessions_dir)
         if os.path.isfile(os.path.join(sessions_dir, f)) and f.lower().endswith('.wav')])  # Put all the detected files alphabetically on an array
    if len(sessions_list) > 0:
        # Group by first 27 characters
        grouped_sessions = {}
        for file in sessions_list:
            key = file[:27]
            if key not in grouped_sessions:
                grouped_sessions[key] = []
            grouped_sessions[key].append(file)
        sessions = sorted(grouped_sessions.keys(), reverse=True)
        selected_session = grouped_sessions[sessions[Session]]
        print(sessions)
    else:
        print("No Exported Sessions found on dir ", str(sessions_dir), '\n')

# ----------- USER INTERFACE --------------
# Behavior when MODEBUTTON is pressed
def Change_Mode():
    global Mode, mode_was_held, audio_buffer
    if not mode_was_held:
        Mode = (Mode + 1) % 3  # Change to the next Mode
        print('----------= Changed to Mode=', str(Mode), '\n')
    mode_was_held = False

# Behavior when MODEBUTTON is held
def restart_program():
    TurningOff()
    print("Restarting App...")
    python = sys.executable  # Gets the actual python interpreter
    os.execv(python, [python] + sys.argv)

# Behavior when PREVBUTTON is pressed
def Prev_Button_Press():
    global selected_loop, Preset, prev_was_held, Session, display_data
    if not prev_was_held:
        if Mode == 0 and setup_donerecording:
            selected_loop = (selected_loop - 1) % number_of_tracks
            print('-= Prev Loop =---> ', selected_loop, '\n')
            debug()
        elif Mode == 1:
            if Preset >= 1:
                Preset -= 1
                ChangePreset()
        elif Mode == 2:
            if Session >= 1:
                Session -= 1
                print("Selected Session = ", str(Session), " - ", str(sessions[Session]))
                display_data = str(Session)[-1]
    prev_was_held = False
    change_volume_event.clear()  # Detener la disminución acelerada

# Behavior when PREVBUTTON is held
def Prev_Button_Held():
    global Bank, prev_was_held, volume_up
    if Mode == 0 and setup_donerecording and loops[selected_loop].initialized >= 1:
        volume_up = False
        change_volume_event.set()  # Iniciar la disminución acelerada
    elif Mode == 1:
        if Bank >= 1:
            Bank -= 1
            ChangeBank()
    prev_was_held = True

# Behavior when NEXTBUTTON is pressed
def Next_Button_Press():
    global selected_loop, Preset, next_was_held, Session, display_data
    if not next_was_held:
        if Mode == 0 and setup_donerecording:
            selected_loop = (selected_loop + 1) % number_of_tracks
            print('-= Next Loop =---> ', selected_loop, '\n')
            debug()
        if Mode == 1:
            if Preset < 125:
                Preset += 1
                ChangePreset()
        elif Mode == 2:
            if Session < len(sessions) - 1:
                Session += 1
                print("Selected Session = ", str(Session), " - ", str(sessions[Session]))
                display_data = str(Session)[-1]
    next_was_held = False
    change_volume_event.clear()

# Behavior when NEXTBUTTON is held
def Next_Button_Held():
    global Bank, next_was_held, volume_up
    if Mode == 0 and setup_donerecording and loops[selected_loop].initialized >= 1:
        volume_up = True
        change_volume_event.set()
    elif Mode == 1:
        if len(sf2_list) > 0:
            if Bank < len(sf2_list) - 1:
                Bank += 1
                ChangeBank()
    next_was_held = True

# Behavior when RECBUTTON is pressed
def Rec_Button_Pressed():
    if Mode == 0 or Mode == 1:
        loops[selected_loop].set_recording()
    elif Mode == 2:
        rec_audio_session()

# Behavior when MUTEBUTTON is pressed
def Mute_Button_Pressed():
    if Mode == 0 or Mode == 1:
        global play_was_held
        if setup_donerecording:
            if not play_was_held:
                loops[selected_loop].toggle_mute()
            play_was_held = False

# Behavior when MUTEBUTTON is held
def Mute_Button_Held():
    if Mode == 0 or Mode == 1:
        global play_was_held
        if setup_donerecording:
            play_was_held = True
            loops[selected_loop].toggle_solo()
    elif Mode == 2:
        if setup_donerecording:
            export_session()
        else:
            print("Nothing to Export")

# Behavior when CLEARBUTTON is pressed
def Clear_Button_Pressed():
    if Mode == 0 or Mode == 1:
        global clear_was_held
        if not clear_was_held:
            loops[selected_loop].undo()
        clear_was_held = False

# Behavior when CLEARBUTTON is held
def Clear_Button_Held():
    if Mode == 0 or Mode == 1:
        global clear_was_held
        clear_was_held = True
        loops[selected_loop].clear()
    elif Mode == 2:
        import_session()

#------------------------------------------------------------------------------------------------

# Turns Off the Looper and exits
def TurningOff():
    if synth_initialized:
        fs.delete()
        print("Closing FluidSynth")
    client.deactivate()
    print("Deactivating JACK Client")
    PowerOffLeds()
    print('Done...')

def rec_audio_session():
    global audio_buffer, set_recording_file
    if not rec_file:  # If Flag to record on disk is False
        audio_buffer = io.BytesIO()  # Creates Audio Buffer to be recorded on Disk
        set_recording_file = True  # Flag to Start Recording on disk by the loop_callback
        print("---= Recording to file =---")
    else:
        audio_buffer.seek(0)
        audio_segment = AudioSegment.from_raw(audio_buffer, sample_width=2, frame_rate=48000, channels=1)
        date_time_now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_file_name = f"{recordings_dir}LooPyStation_output_{date_time_now}.mp3"
        audio_segment.export(output_file_name, format="mp3", bitrate="320k")  # Write file to disk
        print("---= MP3 File saved like: ", output_file_name)
        set_recording_file = False  # Flag to Stop Recording on disk by the loop_callback

def export_session():  # In Mode 2, holding Mute Button, exports all the initialized tracks to wav
    date_time_now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    print(f"-----= Exporting Session {date_time_now}")
    for i in range(number_of_tracks):
        if loops[i].initialized >= 1:
            if loops[i].undo_mode == 0:
                audio_buffer = (loops[i].main_audio[:loops[i].length]*(init_volume/max_volume)**2+
                                loops[i].dub_audio[:loops[i].length]*(init_volume/max_volume)**2)
                audio_buffer = audio_buffer.tobytes()
            elif loops[i].undo_mode == 1:
                audio_buffer = loops[i].main_audio[:loops[i].length].tobytes()
            elif loops[i].undo_mode == 2:
                audio_buffer = loops[i].dub_audio[:loops[i].length].tobytes()
            audio_buffer=io.BytesIO(audio_buffer)
            audio_segment = AudioSegment.from_raw(audio_buffer, sample_width=2, frame_rate=48000, channels=1)
            output_file_name = sessions_dir + "session_" + str(date_time_now) + "-track_" + str(i).zfill(2) + "-" + str(loops[i].volume).zfill(2) + ".wav"
            audio_segment.export(output_file_name, format="wav")  # Write file to disk
            print("   * Session Track - file saved: ", output_file_name)
    list_sessions()
    print("Session 'session_" + str(date_time_now) + "' SAVED Successfully")

def import_session():  # In Mode 2, holding Undo Button, imports the selected (with Prev and Next Buttons) session from the ones recorded at ./recordings
    list_sessions()
    if len(sessions) > 0:
        global setup_donerecording, setup_is_recording, selected_loop, pause_callback
        print(f"-----= Importing Session {selected_session}")
        pause_callback = 300  # "Pauses" the loop callback
        for loop in loops:
            loop.__init__()  # Initialize ALL
        for file in selected_session:
            if len(file) >= 39:  # Make sure the file is at least 36 characters long
                session_track_number = int(file[34:36])  # Extract the chars 35 and 36 that are the Track Number
                session_track_volume = int(file[37:39])  # Extract the chars 38 and 39 that are the Track Volume
                print(f"File: {file} ---> Track: {session_track_number}")
                session_file_path = sessions_dir + file
                load_wav_to_main_audio(session_file_path, session_track_number, session_track_volume)
            else:
                print(f"The file '{file}' has not enough chars in the name.")
        setup_donerecording = True
        setup_is_recording = False
        selected_loop = 0
        print("---= Session Imported Succesfully :-D =---", '\n')
        debug()

def load_wav_to_main_audio(session_file_path, session_track_number, session_track_volume):
    global LENGTH
    try:
        audio_segment = AudioSegment.from_file(session_file_path, format="wav")  # Loads wav file
        audio_data = np.array(audio_segment.get_array_of_samples(), dtype=np.int16)  # Convert to NumPy
        num_blocks = len(audio_data) // CHUNK  # Length in Chunks

        # Copy the data to main_audio and restore initializations, lengths, length_factors and writep
        loops[session_track_number].initialized = 1
        loops[session_track_number].main_audio[:num_blocks] = audio_data[:num_blocks * CHUNK].reshape(num_blocks, CHUNK)
        if session_track_number == 0:
            LENGTH = num_blocks
        loops[session_track_number].length = num_blocks
        loops[session_track_number].volume = session_track_volume
        loops[session_track_number].writep = num_blocks - 1
        loops[session_track_number].length_factor = loops[session_track_number].length / loops[0].length
        loops[session_track_number].is_playing = True
        print(f"Track: {session_track_number} - Archivo cargado: {session_file_path} | Longitud: {num_blocks} bloques.")
    except Exception as e:
        print(f"Error al cargar {session_file_path}: {e}")

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
    print('    |init |rec  |wait |play |waiP |waiM |Solo |Vol\t|MaxP\t|WriP\t|IsUn\t|Leng')
    for i in range(number_of_tracks):
        print(str(i).zfill(2), ' |',
              int(loops[i].initialized), '  |',
              int(loops[i].is_recording), '  |',
              int(loops[i].is_waiting_rec), '  |',
              int(loops[i].is_playing), '  |',
              int(loops[i].is_waiting_play), '  |',
              int(loops[i].is_waiting_mute), '  |',
              int(loops[i].is_solo), '  |',
              int(loops[i].volume), '\t|',
              int(loops[i].maxpeak), '\t|',
              int(loops[i].writep), '\t|',
              int(loops[i].undo_mode), '\t|',
              int(loops[i].length))
    print('setup_donerecording=', setup_donerecording, ' setup_is_recording=', setup_is_recording, 'output_volume=', str(output_volume)[0:4])
    print('length=', loops[selected_loop].length, 'LENGTH=', LENGTH, 'length_factor=', loops[selected_loop].length_factor)
    print('|', ' '*9,'|',' '*9,'|', ' '*9,'|',' '*9,'|')

# Checks which loops are recording/playing/waiting and lights up LEDs and Display accordingly
def show_status():
    global display_data, display_count
    # If Prev / Next Buttons are Pressed, 8-seg. Display shows selected selected_loop / Preset (depends of Mode)
    if display_data == "":
        if Mode == 0:
            display.value = str(selected_loop)[-1]
        elif Mode == 1:
            display.value = str(Preset)[-1] + "."
        elif Mode == 2:
            display.value = " ."
    else:  # Else, if Prev / Next Buttons are Held, display shows Volume / Bank (depends of Mode)
        if display_count <= 4:
            display.value = display_data
            display_count += 1
        else:
            display_count = 0
            display_data = ""

    # Leds Status for Rec Button ---------------------------
    if Mode == 0 or Mode == 1:
        if loops[selected_loop].is_recording:
            RECLEDR.on()
            RECLEDG.off()
        elif loops[selected_loop].is_waiting_rec:
            RECLEDR.on()
            RECLEDG.on()
        elif setup_donerecording or not loops[selected_loop].is_recording:
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
    if loops[selected_loop].is_waiting_play or loops[selected_loop].is_waiting_mute:
        PLAYLEDR.on()
        PLAYLEDG.on()
    elif loops[selected_loop].is_playing:
        PLAYLEDR.off()
        PLAYLEDG.on()
    else:
        PLAYLEDR.off()
        PLAYLEDG.off()

# Event to control the volume change
change_volume_event = Event()

def change_volume_with_acceleration():
    global selected_loop, display_data
    base_interval = 0.5  # Base interval in seconds
    acceleration_factor = 0.7  # Acceleration Factor
    min_interval = 0.1  # Min. Interval between volume changes in seconds
    while True:  # Infinite Loop to keep the thread running
        if change_volume_event.is_set():  # Test if event is active
            interval = base_interval
            while change_volume_event.is_set():  # While Button is pressed
                if volume_up == False:
                    if loops[selected_loop].volume >= 1:
                        loops[selected_loop].volume -= 1
                        print('Volume Decreased=', loops[selected_loop].volume, '\n')
                else:
                    if loops[selected_loop].volume <= max_volume - 1:
                        loops[selected_loop].volume += 1
                        print('Volume Increased=', loops[selected_loop].volume, '\n')
                display_data = str(int(loops[selected_loop].volume/2))[-1]
                debug()
                # Reducir el intervalo para acelerar
                interval = max(min_interval, interval * acceleration_factor)
                sleep(interval)
        else:
            sleep(0.1)  # Avoids the high CPU load when the event is not active

# Start the thread to change volume with acceleration
volume_thread = Thread(target=change_volume_with_acceleration, daemon=True)
volume_thread.start()

# Changes the FluidSynth Preset
def ChangePreset():
    if len(sf2_list) > 0:
        fs.program_select(0, sfid, 0, Preset)
        print('----- Bank: ', str(Bank), ' - ', str(sf2_list[Bank]),' / Preset: ',  ' - ', str(Preset), '\n')

# Changes the FluidSynth Bank
def ChangeBank():
    if len(sf2_list) > 0:
        global display_data, sfid, Preset
        display_data = str(Bank)[-1] + "."
        fs.sfunload(sfid)
        sfid = fs.sfload("./sf2/" + str(sf2_list[Bank]))
        fs.program_select(0, sfid, 0, 0)
        Preset = 0
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
            print("Sound card number:", str(INDEVICE)," detected\n")
        else:
            print("Sound card number:", str(INDEVICE)," NOT detected", end='\r')
            sleep(0.5)
    except FileNotFoundError:
        print("This system does not have /proc/asound/cards. Not a Linux system?")

list_sessions()  # Reads all the exported sessions

# Test if jack server is running and if not, run it
if is_jack_server_running():
    Mode = 0
    print("----- Jack Server is already running ------",'\n')
else:
    os.system ("sudo -H -u raspi env JACK_NO_AUDIO_RESERVATION=1 jackd -dalsa -r"+str(RATE)+" -p"+str(CHUNK)+" -n2 -Xraw -D -Chw:"+str(INDEVICE)+" -Phw:"+str(OUTDEVICE)+" &")
    print("----- Jack Server is NOT running. Starting it!",'\n')
    for i in range(2):
        if i % 2 == 0:
            display.value = " "
        else:
            display.value = " ."
        sleep(0.5)
    print("----- Jack Server is running",'\n')

# Initializing JACK Client
client = jack.Client("RaspiLoopStation")
print('----- Jack Client RaspiLoopStation Initialized','\n')

class audioloop:
    def __init__(self):
        self.initialized = 0
        self.length_factor = 1
        self.length = 0
        self.maxpeak = 0
        self.readp = 0
        self.writep = 0
        self.is_recording = False
        self.is_playing = False
        self.is_waiting_rec = False
        self.is_waiting_play = False
        self.is_waiting_mute = False
        self.undo_mode = 0
        self.is_solo = False
        self.volume = init_volume
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
        progress = (loops[0].readp / (loops[0].length + 1))*50
        self.writep = (self.writep + 1) % self.length
        print('#'*int(progress), end='\r')

    # read_buffer() reads and returns a buffer of audio from the loop
    def read_buffer(self):
        # Turns On 0,1s the Red Led of PLAYBUTTON to mark the starting of Master Loop
        global rec_file
        if setup_donerecording and loops[0].readp == 0:
            PLAYLEDR.on()
            PLAYLEDG.off()
            if set_recording_file:
                rec_file = True
            else:
                rec_file = False

        # If a Track is_waiting_rec, put it to Rec when reaches the end of length of track 0 (not initialized) or at end of selected track (if initialized)
        if self.is_waiting_rec:
            if ((self.initialized >= 1 and self.writep == self.length - 1) or
                (self.initialized == 0 and loops[0].writep == loops[0].length - 1)):
                self.is_recording = True
                self.is_waiting_rec = False
                print('---= Start Recording Track ', selected_loop, '\n')

        # If a Track is not initialized, exit and returns silence
        if self.initialized == 0:
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

        if self.undo_mode == 1:
            return(self.main_audio[tmp, :])  # If Undo was pressed, plays only main_audio
        elif self.undo_mode == 2:
            return(self.dub_audio[tmp, :])  # If Undo was pressed, plays only dub_audio
        elif self.undo_mode == 0:
            return(self.main_audio[tmp, :]*(init_volume/max_volume)**2 +
                   self.dub_audio[tmp, :]*(init_volume/max_volume)**2)  # If Undo was not pressed, plays sum of main and dub audio

    # write_buffer() appends a new buffer on main_audio if not initialized or on dub_audio if initialized
    def write_buffers(self, data):
        global LENGTH
        self.maxpeak = max(np.max(np.abs(data))/max_amplitude*100, self.maxpeak)
        if self.initialized >= 1:
            if self.writep < self.length - 1:
                if self.undo_mode == 0:  # If Undo was not pressed, writes on main_audio the sum of main and dub audio
                    if self.initialized == 1:
                        self.main_audio[self.writep, :] = self.dub_audio[self.writep, :]
                    else:
                        self.main_audio[self.writep, :] = (self.dub_audio[self.writep, :]*(init_volume/max_volume)**2 +
                                                           self.main_audio[self.writep, :]*(init_volume/max_volume)**2)
                    self.dub_audio[self.writep, :] = np.copy(data)  # Add to dub_audio the buffer entering through Jack
                elif self.undo_mode == 1:
                    self.dub_audio[self.writep, :] = np.copy(data)  # Add to dub_audio the buffer entering through Jack
                elif self.undo_mode == 2:
                    self.main_audio[self.writep, :] = np.copy(data)  # Add to main_audio the buffer entering through Jack
            elif self.writep == self.length - 1:
                self.is_recording = False
                self.initialize()
                self.is_waiting_rec = False
                self.is_playing = True
                self.undo_mode = 0
        else:
            if self.length >= (MAXLENGTH - 1):
                self.length = 0
                print('Loop Full')
                return
            self.dub_audio[self.length, :] = np.copy(data)  # Add to main_audio the buffer entering through Jack
            self.length += 1  # Increase the length of the loop
            if not setup_donerecording:
                LENGTH += 1

    #set_recording() either starts or stops recording
    #   if uninitialized and recording, stop recording (appending) and initialize
    #   if initialized and not recording, set as "waiting to record"
    def set_recording(self):
        global setup_is_recording, setup_donerecording
        print('---= set_recording Called for Track ', selected_loop, ' =-', '\n')
        #already_recording = False

        #if chosen track is currently recording, flag it
        if self.is_recording:  # turn off recording
            self.initialize()
            self.is_playing = True
            self.is_recording = False
            self.is_waiting_rec = False
            print('-------------= Stop Rec =---', '\n')
            if selected_loop == 0 and not setup_donerecording:
                setup_is_recording = False
                setup_donerecording = True
                print('-------------= Master Track Recorded =---', '\n')
            debug()
            return
        else:
            #unless flagged, schedule recording. If chosen track was recording, then stop recording
            #if not already_recording:
            if self.is_waiting_rec and setup_donerecording:
                self.is_waiting_rec = False
                return
            if selected_loop == 0 and not setup_donerecording:
                self.is_recording = True
                setup_is_recording = True
            else:
                self.is_waiting_rec = True
            debug()

    #initialize() raises self.length to closest integer multiple of LENGTH and initializes read and write pointers
    def initialize(self): #It initializes when recording of loop stops. It de-initializes after Clearing.
        if self.initialized == 0:
            self.writep = self.length - 1
            self.length_factor = (int((self.length - OVERSHOOT) / LENGTH) + 1)
            self.length = self.length_factor * LENGTH
            self.readp = (self.writep + LATENCY) % self.length  #audio should be written ahead of where it is being read from, to compensate for input+output latency
        self.initialized += 1
        print('     length ' + str(self.length),' /  last buffer recorded ' + str(self.writep),'\n')
        print('-------------= Initialized = ', str(self.initialized), '\n')

        # Apply Fades to dub_audio recently recorded
        np.multiply(self.dub_audio[0], fade_in, out = self.dub_audio[0], casting = 'unsafe')  # Fade In to the first buffer
        np.multiply(self.dub_audio[self.length-1], fade_out, out=self.dub_audio[self.length-1], casting='unsafe')  # Fade Out to the last buffer
        debug()

    def toggle_mute(self):
        print('-=Toggle Mute=-','\n')
        if self.initialized >= 1:
            if self.is_playing:
                if not self.is_waiting_mute:
                    self.is_waiting_mute = True
                else:
                    self.is_waiting_mute = False
                print('-------------= Mute =-', '\n')

            else:
                if not self.is_waiting_play:
                    self.is_waiting_play = True
                else:
                    self.is_waiting_play = False
                self.is_solo = False
                print('-------------= UnMute =-', '\n')
            debug()

    def toggle_solo(self):
        print('-=Toggle Solo=-','\n')
        if self.initialized >= 1:
            if not self.is_solo:
                for i in range(number_of_tracks):
                    if i != selected_loop and loops[i].initialized >= 1 and not loops[i].is_solo and loops[i].is_playing:
                        loops[i].is_waiting_mute = True
                self.is_solo = True
                print('-------------= Solo =-', '\n')
            else:
                for i in range (number_of_tracks):
                    if i != selected_loop and loops[i].initialized >= 1:
                        loops[i].is_waiting_play = True
                        loops[i].is_solo = False
                self.is_solo = False
                print('-------------= UnSolo =-', '\n')
            debug()

    def undo(self):
        global LENGTH
        if self.is_recording:
            if self.initialized == 0:
                self.clear_track()
                if selected_loop == 0:
                    LENGTH = 0
                return
        if self.is_playing:
            if self.undo_mode <= 1:
                self.undo_mode += 1
            else:
                self.undo_mode = 0

        print('-=Undo=-', '\n')
        debug()

    # Clears all the Tracks of the looper
    def clear(self):
        global setup_donerecording, setup_is_recording, LENGTH
        if selected_loop == 0:
            for loop in loops:
                loop.__init__()
            setup_donerecording = False
            setup_is_recording = False
            LENGTH = 0
            print('-=Cleared ALL=-','\n')
        else:
            self.clear_track()
        debug()

    # Clears the track so that a new loop of the same or a different length can be recorded on the track
    def clear_track(self):
        self.__init__()
        print('-=Clear Track=-', '\n')

# Defining number_of_tracks of audio loops. loops[0] is the master loop.
loops = [audioloop() for _ in range(number_of_tracks)]

# Audio Processing Callback
@client.set_process_callback
def looping_callback(frames):
    global play_buffer, current_rec_buffer, pause_callback, output_volume, previous_scaling_factor

    if pause_callback > 1:  # Little "pause" for the the loopback
        play_buffer[:] = silence
        pause_callback -= 1
        print(pause_callback, "   ", end='\r')
        return

    # Setup: First Recording
    if not setup_donerecording:  # If setup is not done i.e. if the master loop hasn't been recorded to yet
        loops[0].is_waiting_rec = 1

    # Read input buffer from JACK
    current_rec_buffer = float2pcm(input_port.get_array())  # Capture current input jack buffer after converting Float2PCM

    # If a loop is recording, check initialization and accordingly append
    for loop in loops:
        if loop.is_recording:
            print('--------------------------------------------------=Recording=-', end='\r')
            loop.write_buffers(current_rec_buffer)

    # Converts the volumes and buffers into NumPy arrays for vectorized operations
    buffers = np.array([loop.read_buffer().astype(np.int32) for loop in loops])
    volumes = np.array([(loop.volume / max_volume) ** 2 for loop in loops], dtype=np.float32)
    # Multiply each buffer by the own volume and sum them all
    mixed_buffer = np.sum(buffers * volumes[:, None], axis=0)

    '''
    mixed_buffer = np.multiply(mixed_buffer, output_volume, out=None, casting='unsafe')
    # Limiter: Ensure no values exceed the range of int16
    peak = np.max(np.abs(mixed_buffer))  # Find the peak amplitude
    if peak > max_amplitude:
        # Calculate the scaling factor to limit the signal
        target_scaling_factor = max_amplitude / peak
        # Apply smoothing to the scaling factor (exponential smoothing)
        smoothing_factor = 0.1  # 0.1 is the smoothing factor (you can adjust this)
        scaling_factor = previous_scaling_factor * (1 - smoothing_factor) + target_scaling_factor * smoothing_factor
        # Update the previous scaling factor for the next callback
        previous_scaling_factor = scaling_factor
        # Apply the scaling factor to the mixed buffer
        print(f"Limiter applied. Scaling factor: {scaling_factor:.4f}", '\n')
        mixed_buffer = mixed_buffer * scaling_factor
    else:
        # If no limiting is required, keep the previous scaling factor
        previous_scaling_factor = 0.9
        '''

    # Add to play_buffer the sum of each audio signal times the each own volume
    play_buffer[:] = np.multiply(mixed_buffer, output_volume, out=None, casting='unsafe').astype(np.int16)

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
        if any(port.name == target_port for port in outMIDIports) and len(sf2_list) > 0:
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
            synth_initialized = True
            connect_fluidsynth()
            sleep(0.5)
            # Loads the first soundfont of the list
            sfid = fs.sfload("./sf2/" + sf2_list[0])
            fs.program_select(0, sfid, 0, 0)
            print('----- Bank: ', str(Bank), ' - ', str(sf2_list[Bank]),' / Preset: ',  ' - ', str(Preset), '\n')

        #then we turn on Green and Red lights of REC Button to indicate that looper is ready to start looping
        print("Jack Client Active. Press Ctrl+C to Stop.",'\n')
        #once all LEDs are on, we wait for the master loop record button to be pressed
        print('---Waiting for Record Button---','\n')
        debug()

        while True:
            show_status()
            sleep(0.1)
            pass  # Keep Client executing

    except KeyboardInterrupt:
        TurningOff()
