import sys
f = open('./settings.prt', 'r')
parameters = f.readlines()
while (len(parameters) < 8):
    parameters.append('\n')
f.close()

parameters[0] = (input('Enter Sample Rate in Hz (44100, [48000], ...): ') or "48000") + '\n'
parameters[1] = (input('Enter Buffer Size (128, [256], 512, 1024, ...): ') or "256") + '\n'
parameters[2] = (input('Enter Latency Correction in milliseconds (16, [32], ...): ') or "32") + '\n'
print('-----------------------------------','\n')
with open('/proc/asound/cards', 'r') as file:
    content = file.read()
sys.stdout.write(content)
print('-----------------------------------','\n')
parameters[3] = (input('Enter Input Device Index ([0], 1, 2, ...): ') or "0") + '\n'
parameters[4] = (input('Enter Output Device Index ([0], 1, 2, ...): ') or "0") + '\n'
parameters[5] = (input('Enter Margin for Late Button Press in Milliseconds (Around [1200] seems to work well) : ') or "1200") + '\n'
parameters[6] = (input('Enter [0] to connect all Jack Capture Ports to RasPyLooper Input port, or\nEnter (n) to connect only Jack Capture Port n to RasPyLooper Input port: ') or "0") + '\n'

f = open('./settings.prt', 'w')
for i in range(8):
    f.write(parameters[i])
f.close()
