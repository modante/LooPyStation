f = open('./settings.prt', 'r')
parameters = f.readlines()
while (len(parameters) < 6):
    parameters.append('\n')
f.close()

parameters[0] = input('Enter Sample Rate in Hz (Safe Choices 44100 and 48000): ') + '\n'
parameters[1] = input('Enter Buffer Size (Typical 256, 512, 1024): ') + '\n'
parameters[2] = input('Enter Latency Correction in milliseconds: ') + '\n'
cat /proc/asound/cards
parameters[3] = input('Enter Input Device Index: ') + '\n'
parameters[4] = input('Enter Output Device Index: ') + '\n'
parameters[5] = input('Enter Margin for Late Button Press in Milliseconds (Around 500 seems to work well) : ') + '\n'

f = open('./settings.prt', 'w')
for i in range(6):
    f.write(parameters[i])
f.close()
