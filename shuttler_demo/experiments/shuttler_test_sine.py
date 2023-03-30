from artiq.experiment import *

from artiq.coredevice.spi2 import *
import numpy as np
from numpy import int32


N_SAMPLES = 1024
Fs = 125e6


def generate_sin(amplitude, frequency):
    time = np.linspace(0, N_SAMPLES-1, N_SAMPLES)
    return amplitude*np.cos(2 * np.pi * frequency * time / Fs)

def voltage_to_mu(value):
    data = int32(round((0x2000/1.)*value)) + int32(0x2000)
    if data < 0:
        data = 0
    if data > 0x3fff:
        data = 0x3FFF
    return data


class SquareGeneratorMaxFreq(EnvExperiment):

    def build(self):
        self.setattr_device("core")
        self.setattr_device("shuttler")
        self.setattr_device("shuttler_awg_reset")

    @kernel
    def run_kernel(self):
        print("Running...")
        self.core.reset()
        self.shuttler.init()
        delay(1*s)
        print("DAC timing status:")
        for i in range(8):
            print("DAC", i, ":", self.shuttler.get_dac_timing_status(i))
            delay(10*ms)
        self.shuttler.write_samples(self.values)
        delay(1*s)
        self.shuttler_awg_reset.on()
        delay(100*ns)
        self.shuttler_awg_reset.off()

    
    def run(self):
        N_SAMPLES = 1024
        Fs = 125e6
        Ts = 1/Fs

        n = np.linspace(0, N_SAMPLES-1, N_SAMPLES)
        time = n*Ts

        base_T = N_SAMPLES*Ts
        base_f = round(1/base_T, 4)

        freqs = [
            base_f,
            base_f*2,
            base_f*4,
            base_f*6,
            base_f*8,
            base_f*10,
            base_f*11,
            base_f*12,
            base_f*14,
            base_f*16,
            base_f*24,
            base_f*32,
            base_f*48,
            base_f*64,
            base_f*128,
            base_f*256,
            base_f*512,
        ]
        
        for freq in freqs:
            base_freq = freq
            self.signal = generate_sin(1, 1*base_freq)
            self.signal = self.signal.tolist()
            self.values = [int32(0) for i in range(len(self.signal))]
            for i in range(len(self.signal)):
                self.values[i] = voltage_to_mu(self.signal[i])
            self.run_kernel()
            input(f"Current frequency: {base_freq} MHz [ENTER]")

