#! /usr/bin/python3
# -*- coding: utf-8 -*-

guitarix_pgm = "guitarix -N -p 7000"

import socket, json, os, time, signal
from subprocess import check_output

class RpcNotification:

    def __init__(self, method, params):
        self.method = method
        self.params = params

class RpcResult:

    def __init__(self, id, result):
        self.id = id
        self.result = result

class RpcSocket:

    def __init__(self, address=("localhost",7000)):
        self.s = socket.socket()
        self.s.connect(address)
        self.buf = ""
        self.banks = []
        self.presets = []

    def send(self, method, id=None, params=[]):
        d = dict(jsonrpc="2.0", method=method, params=params)
        if id is not None:
            d["id"] ="1"
        self.s.send((json.dumps(d)+"\n").encode())

    def call(self, method, params=[]):
        self.send(method=method, id="1", params=params)

    def notify(self, method, params=[]):
        self.send(method=method, params=params)

    def receive(self):
        if type(self.buf) is str:
            l = [self.buf.encode()]
        else:
            l = [self.buf]
        while True:
            p = l[-1]
            if  b"\n" in p:
                ln, sep, tail = p.partition(b'\n')
                l[-1] = ln
                st = "".join(s.decode('utf8') for s in l)
                self.buf = tail
                break;
            l.append(self.s.recv(10000))
        try:
            d = json.loads(st)
        except ValueError as e:
            print (e)
            print (st)
            return None
        if "params" in d:
            # guitarix quit
            if not d["params"]:
                return None
            # filter out output port messages
            elif  ".v" in (d["params"][0]):
                return False
            else:
                return RpcNotification(d["method"], d["params"])
        elif "result" in d:
            return RpcResult(d["id"], d["result"])
        else:
            raise ValueError("rpc error: %s" % d)

    def print_current_preset(self):
        time.sleep(0.1)
        # print out current bank and preset
        self.call("get", ["system.current_bank"])
        bank = self.receive().result["system.current_bank"]
        self.call("get", ["system.current_preset"])
        preset = self.receive().result["system.current_preset"]
        print(bank +" "+ preset)

    def get_banks(self):
        self.call("banks",[])
        r = self.receive().result
        for  d in r:
            self.banks.append(d['name'])
            self.presets.append(d['presets'])

class Guitarix():
    def open_socket(self):
        try:
            self.sock = RpcSocket()
        except socket.error as e:
            if e.errno != 111:
                raise
            return False
        return True

    def __init__(self):
        self.current_params = {}
        if not self.open_socket():
            
            os.system(guitarix_pgm+"&")
            for i in range(10):
                time.sleep(1)
                if self.open_socket():
                    break
            else:
                raise RuntimeError("Can't connect to Guitarix")
            self

def main():
    global next_bank, sock, pid
    #start guitarix with rpc port at 7000
    gx = Guitarix()
    print ("--- Starting Guitarix ---")
    # open a socket at 7000
    sock = RpcSocket()
    # get pid of guitarix instance
    pid = int(check_output(["pidof","-s","guitarix"]))
    # get available banks
    sock.get_banks()
    next_bank = 0
    # load first available bank/preset
    sock.notify("setpreset", [sock.banks[next_bank], sock.presets[next_bank][0]])
    next_bank = next_bank + 1
    # print current bank/preset
    sock.print_current_preset()

def change_guitarix():
    global next_bank
    if x == '\x1b[B':
        # load next preset from current bank
        sock.notify("set", ['engine.next_preset',1])
        sock.print_current_preset()
    elif x == '\x1b[A':
        # load previus preset from current bank
        sock.notify("set", ['engine.previus_preset',1])
        sock.print_current_preset()
    elif x == '\x1b[C':
        # load next bank with first preset
        if next_bank > len(sock.banks)-1:
            next_bank = 0
        sock.notify("setpreset", [sock.banks[next_bank], sock.presets[next_bank][0]])
        next_bank = next_bank + 1
        if next_bank > len(sock.banks)-1:
            next_bank = 0
        sock.print_current_preset()
    elif x == '\x1b[D':
        # load previus bank with first preset
        next_bank = next_bank - 2
        if next_bank < 0:
            next_bank = len(sock.banks)-1
        sock.notify("setpreset", [sock.banks[next_bank], sock.presets[next_bank][0]])
        next_bank = next_bank + 1
        if next_bank > len(sock.banks):
            next_bank = 0
        sock.print_current_preset()
    elif x == 'q' or x == '\x03':
        try:
            # quit guitarix
            os.kill(pid, signal.SIGINT)
            time.sleep(1)
        except OSError:
            print("guitarix didn't run anymore")
        raise SystemExit

if __name__=="__main__":
    main()

